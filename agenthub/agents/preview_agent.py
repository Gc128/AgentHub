from agenthub.core.errors import AgentExecutionError
from agenthub.schemas.agent import AgentRunInput, AgentRunResult


class PreviewAgent:
    id = "preview-agent"
    name = "Preview Agent"
    capabilities = ["manual-preview", "trusted-preview-link"]

    async def run(self, input_data: AgentRunInput) -> AgentRunResult:
        del input_data
        raise AgentExecutionError(
            "Manual preview links must be produced by AgentService from trusted workspace IDs."
        )


PREVIEW_AGENT_SYSTEM_PROMPT = (
    "Preview Agent does not call an LLM or run browser checks. AgentService provides the link."
)
