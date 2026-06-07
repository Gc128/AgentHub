import hashlib
import re
from pathlib import Path

from agenthub.agents.base import AgentAdapter
from agenthub.core.errors import AgentExecutionError
from agenthub.schemas.agent import AgentRunInput, AgentRunResult
from agenthub.schemas.artifact import Artifact
from agenthub.workspace.diff import create_unified_diff
from agenthub.workspace.manager import WorkspacePathError, resolve_workspace_path


class CodeAgent:
    id = "code-agent"
    name = "Code Agent"
    capabilities = ["code", "diff", "file-generation"]

    def __init__(self, llm: AgentAdapter, workspace_root: Path | None = None) -> None:
        self._llm = llm
        self._workspace_root = workspace_root or Path("./workspaces")

    async def run(self, input_data: AgentRunInput) -> AgentRunResult:
        result = await self._llm.run(
            input_data.model_copy(
                update={
                    "context": {
                        **input_data.context,
                        "agent_id": self.id,
                        "agent_role": "code",
                    }
                }
            )
        )
        result = result.model_copy(update={"agent_id": self.id})
        artifact_types = {artifact.type for artifact in result.artifacts}
        if not artifact_types and not _looks_like_code_task(input_data.user_message):
            return result
        result = _ensure_content_includes_code_artifacts(result)
        if "code" in artifact_types:
            diff_artifacts = _build_missing_diff_artifacts(
                result.artifacts,
                workspace_id=input_data.workspace_id,
                workspace_root=self._workspace_root,
            )
            if diff_artifacts:
                result = result.model_copy(
                    update={"artifacts": [*result.artifacts, *diff_artifacts]}
                )
                artifact_types = {artifact.type for artifact in result.artifacts}
        result = result.model_copy(
            update={"artifacts": _normalize_diff_artifact_ids(result.artifacts)}
        )
        artifact_types = {artifact.type for artifact in result.artifacts}
        if not {"code", "diff"}.issubset(artifact_types):
            raise AgentExecutionError("Code Agent must return code and diff artifacts.")
        return result


def _looks_like_code_task(user_message: str) -> bool:
    normalized = user_message.lower()
    normalized = normalized.replace("@codeagent", "")
    code_keywords = {
        "code",
        "component",
        "page",
        "html",
        "css",
        "javascript",
        "typescript",
        "react",
        "todo",
        "app",
        "写",
        "实现",
        "生成",
        "页面",
        "组件",
        "代码",
        "开发",
        "功能",
        "修复",
    }
    return any(keyword in normalized for keyword in code_keywords)


def _ensure_content_includes_code_artifacts(result: AgentRunResult) -> AgentRunResult:
    content = result.content
    additions: list[str] = []
    for artifact in result.artifacts:
        if artifact.type != "code":
            continue
        filename_value = artifact.data.get("filename")
        content_value = artifact.data.get("content")
        if not isinstance(filename_value, str) or not filename_value:
            continue
        if not isinstance(content_value, str) or not content_value:
            continue
        if content_value in content:
            continue
        language = _code_fence_language(artifact)
        additions.append(
            f'```{language} filename="{filename_value}"\n{content_value.rstrip()}\n```'
        )

    if not additions:
        return result
    next_content = content.rstrip() + "\n\n" + "\n\n".join(additions)
    return result.model_copy(update={"content": next_content})


def _build_missing_diff_artifacts(
    artifacts: list[Artifact],
    *,
    workspace_id: str,
    workspace_root: Path,
) -> list[Artifact]:
    existing_diff_filenames = {
        filename
        for artifact in artifacts
        if artifact.type == "diff" and (filename := _diff_artifact_filename(artifact))
    }
    diff_artifacts: list[Artifact] = []
    for code_artifact in artifacts:
        if code_artifact.type != "code":
            continue
        filename_value = code_artifact.data.get("filename")
        content_value = code_artifact.data.get("content")
        filename = (
            filename_value if isinstance(filename_value, str) and filename_value else "index.html"
        )
        if filename in existing_diff_filenames:
            continue
        if not isinstance(content_value, str) or not content_value:
            continue
        old_content = _read_existing_workspace_content(workspace_root, workspace_id, filename)
        if old_content is None:
            continue
        diff_artifacts.append(
            Artifact(
                id=f"{code_artifact.id}-diff",
                type="diff",
                title=f"{filename} diff",
                data={
                    "filename": filename,
                    "source_artifact_id": code_artifact.id,
                    "diff": create_unified_diff(
                        old_content,
                        _normalize_generated_file_content(content_value),
                        filename,
                    ),
                },
            )
        )
        existing_diff_filenames.add(filename)
    return diff_artifacts


def _normalize_diff_artifact_ids(artifacts: list[Artifact]) -> list[Artifact]:
    normalized_artifacts: list[Artifact] = []
    for artifact in artifacts:
        if artifact.type != "diff":
            normalized_artifacts.append(artifact)
            continue

        diff_value = artifact.data.get("diff")
        if not isinstance(diff_value, str) or not diff_value:
            normalized_artifacts.append(artifact)
            continue

        filename = _diff_artifact_filename(artifact) or "diff"
        next_id = _content_addressed_diff_artifact_id(filename, diff_value)
        next_data = {**artifact.data, "filename": filename}
        if artifact.id != next_id and "source_artifact_id" not in next_data:
            next_data["source_artifact_id"] = artifact.id

        normalized_artifacts.append(artifact.model_copy(update={"id": next_id, "data": next_data}))

    return normalized_artifacts


def _content_addressed_diff_artifact_id(filename: str, diff: str) -> str:
    slug = _slugify_artifact_filename(filename)
    digest = hashlib.sha256(f"{filename}\0{diff}".encode()).hexdigest()[:12]
    return f"artifact-code-agent-diff-{slug}-{digest}"


def _slugify_artifact_filename(filename: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", filename.lower()).strip("-")
    return slug or "file"


def _diff_artifact_filename(artifact: Artifact) -> str | None:
    filename_value = artifact.data.get("filename")
    if isinstance(filename_value, str) and filename_value:
        return filename_value

    diff_value = artifact.data.get("diff")
    if not isinstance(diff_value, str):
        return None
    for line in diff_value.splitlines():
        if line.startswith("+++ "):
            target = line[4:].strip()
            if target.startswith("b/"):
                return target[2:]
            return target
    return None


def _read_existing_workspace_content(
    workspace_root: Path,
    workspace_id: str,
    filename: str,
) -> str | None:
    try:
        workspace_dir = resolve_workspace_path(workspace_root, workspace_id)
        target_file = resolve_workspace_path(workspace_dir, filename)
    except WorkspacePathError:
        return None
    if not target_file.exists():
        return ""
    return target_file.read_text(encoding="utf-8")


def _code_fence_language(artifact: Artifact) -> str:
    language_value = artifact.data.get("language")
    if not isinstance(language_value, str) or not language_value.strip():
        return "text"
    return language_value.strip().split()[0].lower()


def _normalize_generated_file_content(content: str) -> str:
    return content.rstrip("\n") + "\n"


CODE_AGENT_SYSTEM_PROMPT = """
You are AgentHub Code Agent.
Return one JSON object matching AgentRunResult exactly:
{"agent_id":"code-agent","content":"Markdown summary","artifacts":[],"next_actions":[]}

Rules:
- Generate runnable, concrete code for the user's requested UI or feature.
- Put the full user-facing answer in content as Markdown.
- Include generated code in content as fenced code blocks.
- Add filename metadata to each code fence, e.g. ```tsx filename="src/App.tsx".
- When the user asks for separate HTML, CSS, and JS files, output each file as
  its own fenced code block or code artifact with its own filename.
- You may also include code artifacts with data.filename, data.language, data.content.
- If you omit artifacts, AgentHub will extract code artifacts from Markdown fences.
- Diff paths must stay inside the workspace and use a/ and b/ headers.
- Do not include secrets or local absolute paths.
""".strip()
