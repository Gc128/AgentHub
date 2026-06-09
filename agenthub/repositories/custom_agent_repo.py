from __future__ import annotations

import builtins

from agenthub.core.errors import NotFoundError
from agenthub.schemas.custom_agent import CustomAgent


class CustomAgentRepository:
    def __init__(self) -> None:
        self._agents: dict[str, CustomAgent] = {}

    async def list(self) -> builtins.list[CustomAgent]:
        return sorted(self._agents.values(), key=lambda item: item.updated_at, reverse=True)

    async def list_enabled(self) -> builtins.list[CustomAgent]:
        return [agent for agent in await self.list() if agent.is_enabled]

    async def get(self, agent_id: str) -> CustomAgent:
        agent = self._agents.get(agent_id)
        if agent is None:
            raise NotFoundError("custom_agent_not_found", "Custom Agent does not exist.")
        return agent

    async def save(self, agent: CustomAgent) -> CustomAgent:
        self._agents[agent.id] = agent
        return agent

    async def delete(self, agent_id: str) -> None:
        await self.get(agent_id)
        del self._agents[agent_id]
