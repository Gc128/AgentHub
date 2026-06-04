from datetime import UTC, datetime

from agenthub.agents.base import AgentAdapter
from agenthub.schemas.agent import AgentRunInput, AgentRunResult
from agenthub.schemas.artifact import Artifact


class PreviewAgent:
    id = "preview-agent"
    name = "Preview Agent"
    capabilities = ["preview", "artifact", "workspace-status"]

    def __init__(self, llm: AgentAdapter) -> None:
        self._llm = llm

    async def run(self, input_data: AgentRunInput) -> AgentRunResult:
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
        result = result.model_copy(update={"agent_id": self.id})
        if any(artifact.type == "preview" for artifact in result.artifacts):
            return result
        return result.model_copy(
            update={
                "artifacts": [
                    *result.artifacts,
                    Artifact(
                        id=f"artifact-preview-{input_data.workspace_id}",
                        type="preview",
                        title="Workspace preview",
                        data={
                            "workspace_id": input_data.workspace_id,
                            "status": str(input_data.context.get("preview_status", "not_started")),
                            "preview_url": input_data.context.get("preview_url"),
                            "checked_at": datetime.now(UTC).isoformat(),
                        },
                    ),
                ]
            }
        )


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
