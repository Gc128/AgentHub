from agenthub.schemas.agent import AgentRunInput, AgentRunResult
from agenthub.schemas.artifact import Artifact


class MockAgent:
    def __init__(self, agent_id: str = "mock-agent") -> None:
        self.id = agent_id
        self.name = agent_id.replace("-", " ").title()
        self.capabilities = ["demo", "offline", "artifact"]

    async def run(self, input_data: AgentRunInput) -> AgentRunResult:
        artifact = Artifact(
            id=f"artifact-{self.id}",
            type="code",
            title="Mock response",
            data={
                "filename": "README.md",
                "language": "markdown",
                "content": f"# Response for {input_data.user_message}",
            },
        )
        return AgentRunResult(
            agent_id=self.id,
            content=f"{self.name} received: {input_data.user_message}",
            artifacts=[artifact],
            next_actions=["review", "preview"],
        )
