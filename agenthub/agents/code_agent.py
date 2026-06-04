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
        if "code" in artifact_types and "diff" not in artifact_types:
            diff_artifact = _build_diff_artifact(
                result.artifacts,
                workspace_id=input_data.workspace_id,
                workspace_root=self._workspace_root,
            )
            if diff_artifact is not None:
                result = result.model_copy(update={"artifacts": [*result.artifacts, diff_artifact]})
                artifact_types.add("diff")
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


def _build_diff_artifact(
    artifacts: list[Artifact],
    *,
    workspace_id: str,
    workspace_root: Path,
) -> Artifact | None:
    code_artifact = next((artifact for artifact in artifacts if artifact.type == "code"), None)
    if code_artifact is None:
        return None

    filename_value = code_artifact.data.get("filename")
    content_value = code_artifact.data.get("content")
    filename = (
        filename_value if isinstance(filename_value, str) and filename_value else "index.html"
    )
    if not isinstance(content_value, str) or not content_value:
        return None
    old_content = _read_existing_workspace_content(workspace_root, workspace_id, filename)
    if old_content is None:
        return None

    return Artifact(
        id=f"{code_artifact.id}-diff",
        type="diff",
        title=f"{filename} diff",
        data={
            "filename": filename,
            "diff": create_unified_diff(old_content, content_value, filename),
        },
    )


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


CODE_AGENT_SYSTEM_PROMPT = """
You are AgentHub Code Agent.
Return one JSON object matching AgentRunResult exactly:
{"agent_id":"code-agent","content":"Markdown summary","artifacts":[],"next_actions":[]}

Rules:
- Generate runnable, concrete code for the user's requested UI or feature.
- Put the full user-facing answer in content as Markdown.
- Include generated code in content as fenced code blocks.
- Add filename metadata to each code fence, e.g. ```tsx filename="src/App.tsx".
- You may also include code artifacts with data.filename, data.language, data.content.
- If you omit artifacts, AgentHub will extract code artifacts from Markdown fences.
- Diff paths must stay inside the workspace and use a/ and b/ headers.
- Do not include secrets or local absolute paths.
""".strip()
