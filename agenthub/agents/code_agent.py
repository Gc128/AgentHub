from agenthub.agents.mock_agent import MockAgent


class CodeAgent(MockAgent):
    def __init__(self) -> None:
        super().__init__(agent_id="code-agent")
        self.capabilities = ["code", "diff", "file-generation"]
