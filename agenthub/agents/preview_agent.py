from datetime import UTC, datetime

from agenthub.agents.base import AgentAdapter
from agenthub.agents.real_agent import RealAgentSchemaError
from agenthub.schemas.agent import AgentRunInput, AgentRunResult
from agenthub.schemas.artifact import Artifact


class PreviewAgent:
    id = "preview-agent"
    name = "Preview Agent"
    capabilities = ["preview", "artifact", "workspace-status"]

    def __init__(self, llm: AgentAdapter, *, allow_fallbacks: bool = False) -> None:
        self._llm = llm
        self._allow_fallbacks = allow_fallbacks

    async def run(self, input_data: AgentRunInput) -> AgentRunResult:
        try:
            result = await self._llm.run(
                input_data.model_copy(
                    update={
                        "context": {
                            **input_data.context,
                            "agent_id": self.id,
                            "agent_role": "preview",
                        }
                    }
                )
            )
        except RealAgentSchemaError:
            result = AgentRunResult(
                agent_id=self.id,
                content="Preview Agent 已完成 workspace preview 状态检查。",
                artifacts=[],
                next_actions=[],
            )
        result = result.model_copy(update={"agent_id": self.id})
        preview_status = str(input_data.context.get("preview_status", "not_started"))
        preview_url = input_data.context.get("preview_url")
        prior_artifacts = input_data.context.get("prior_artifacts", [])
        has_diff = isinstance(prior_artifacts, list) and any(
            isinstance(artifact, dict) and artifact.get("type") == "diff"
            for artifact in prior_artifacts
        )
        preview_artifact = next(
            (artifact for artifact in result.artifacts if artifact.type == "preview"),
            None,
        )
        if preview_artifact is not None:
            artifact_status = preview_artifact.data.get("status")
            artifact_url = preview_artifact.data.get("preview_url")
            if isinstance(artifact_status, str) and artifact_status:
                preview_status = artifact_status
            if isinstance(artifact_url, str) and artifact_url:
                preview_url = artifact_url

        verification = _preview_verification_summary(
            status=preview_status,
            preview_url=preview_url if isinstance(preview_url, str) else None,
            has_pending_diff=has_diff,
        )
        if preview_artifact is not None:
            return result.model_copy(
                update={"content": _append_preview_verification(result.content, verification)}
            )
        return result.model_copy(
            update={
                "content": _append_preview_verification(result.content, verification),
                "artifacts": [
                    *result.artifacts,
                    Artifact(
                        id=f"artifact-preview-{input_data.workspace_id}",
                        type="preview",
                        title="Workspace preview",
                        data={
                            "workspace_id": input_data.workspace_id,
                            "status": preview_status,
                            "preview_url": preview_url,
                            "checked_at": datetime.now(UTC).isoformat(),
                            "verification": verification,
                        },
                    ),
                ],
            }
        )

    def _fallbacks_allowed(self, input_data: AgentRunInput) -> bool:
        return self._allow_fallbacks or input_data.context.get("allow_agent_fallbacks") is True


def _preview_verification_summary(
    *,
    status: str,
    preview_url: str | None,
    has_pending_diff: bool,
) -> str:
    if status == "ready" and preview_url:
        return "Preview 状态为 ready，已发现可打开的 preview_url。"
    if has_pending_diff:
        return "已发现待应用的 diff；用户点击 Apply Diff 后，workspace preview 才会刷新。"
    if not preview_url:
        return "当前没有 preview_url；需要先生成或应用 workspace 入口文件后再预览。"
    return f"Preview 当前状态为 {status}，尚不能确认页面已经可用。"


def _append_preview_verification(content: str, verification: str) -> str:
    if verification in content:
        return content
    return content.rstrip() + "\n\n" + verification


PREVIEW_AGENT_SYSTEM_PROMPT = """
You are AgentHub Preview Agent.
Return one JSON object matching AgentRunResult exactly:
{"agent_id":"preview-agent","content":"Markdown preview status","artifacts":[],"next_actions":[]}

Rules:
- Summarize whether the workspace can be previewed.
- Include one preview artifact with data.workspace_id, data.status, and optional data.preview_url.
- Use only workspace_id, preview_status, and preview_url from context.
- Do not claim files were applied unless the context says so.
""".strip()
