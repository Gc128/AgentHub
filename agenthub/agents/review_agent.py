from agenthub.agents.base import AgentAdapter
from agenthub.core.errors import AgentExecutionError
from agenthub.schemas.agent import AgentRunInput, AgentRunResult


class ReviewAgent:
    id = "review-agent"
    name = "Review Agent"
    capabilities = ["review", "quality", "risk"]

    def __init__(self, llm: AgentAdapter) -> None:
        self._llm = llm

    async def run(self, input_data: AgentRunInput) -> AgentRunResult:
        result = await self._llm.run(
            input_data.model_copy(
                update={
                    "context": {
                        **input_data.context,
                        "agent_id": self.id,
                        "agent_role": "review",
                    }
                }
            )
        )
        result = result.model_copy(update={"agent_id": self.id})
        if not any(artifact.type == "file" for artifact in result.artifacts):
            raise AgentExecutionError("Review Agent must return a file artifact with findings.")
        return result


REVIEW_AGENT_SYSTEM_PROMPT = """
You are AgentHub Review Agent.
Return one JSON object matching AgentRunResult exactly:
{"agent_id":"review-agent","content":"Markdown review","artifacts":[],"next_actions":[]}

Rules:
- Review the current request, history, and prior artifacts.
- Focus on correctness, demo stability, workspace safety, UI risks, and missing tests.
- Include one file artifact. Its data should include findings as a string array and risk_level.
- Do not invent applied changes; review only what is in context.
""".strip()
