from agenthub.agents.mock_agent import MockAgent


class PreviewAgent(MockAgent):
    def __init__(self) -> None:
        super().__init__(agent_id="preview-agent")
        self.capabilities = ["preview", "artifact"]
