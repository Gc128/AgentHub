from agenthub.agents.base import AgentAdapter
from agenthub.agents.code_agent import CodeAgent
from agenthub.agents.mock_agent import MockAgent
from agenthub.agents.preview_agent import PreviewAgent
from agenthub.agents.review_agent import ReviewAgent
from agenthub.core.errors import NotFoundError


class AgentRegistry:
    def __init__(self, adapters: list[AgentAdapter]) -> None:
        self._adapters = {adapter.id: adapter for adapter in adapters}

    def get(self, agent_id: str) -> AgentAdapter:
        adapter = self._adapters.get(agent_id)
        if adapter is None:
            raise NotFoundError("agent_not_found", f"Agent '{agent_id}' does not exist.")
        return adapter

    def list(self) -> list[AgentAdapter]:
        return list(self._adapters.values())


def create_default_registry() -> AgentRegistry:
    return AgentRegistry(
        adapters=[
            MockAgent(),
            MockAgent(agent_id="orchestrator"),
            CodeAgent(),
            ReviewAgent(),
            PreviewAgent(),
        ]
    )
