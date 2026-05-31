from agenthub.agents.mock_agent import MockAgent


class ReviewAgent(MockAgent):
    def __init__(self) -> None:
        super().__init__(agent_id="review-agent")
        self.capabilities = ["review", "quality", "risk"]
