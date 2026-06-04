import json
from collections.abc import AsyncIterator
from typing import Literal

from agenthub.agents.registry import AgentRegistry
from agenthub.core.errors import AgentExecutionError, NotFoundError
from agenthub.orchestrator.executor import OrchestratorExecutor
from agenthub.orchestrator.router import route_agent
from agenthub.schemas.agent import Agent, AgentRunInput, AgentRunResult

AgentRole = Literal["orchestrator", "code", "review", "preview", "custom"]


class AgentService:
    def __init__(self, registry: AgentRegistry) -> None:
        self._registry = registry

    def list_agents(self) -> list[Agent]:
        return [
            Agent(
                id=adapter.id,
                name=adapter.name,
                role=self._infer_role(adapter.id),
                description=f"{adapter.name} adapter",
                capabilities=adapter.capabilities,
                adapter_type="mock",
            )
            for adapter in self._registry.list()
        ]

    async def run(self, input_data: AgentRunInput) -> AgentRunResult:
        agent_id = str(input_data.context.get("agent_id") or route_agent(input_data.user_message))
        if agent_id == "orchestrator":
            return await OrchestratorExecutor(registry=self._registry).run(input_data)
        try:
            agent = self._registry.get(agent_id)
            return await agent.run(input_data)
        except NotFoundError:
            raise
        except AgentExecutionError:
            raise
        except Exception as exc:
            fallback = self._registry.get("mock-agent")
            fallback_result = await fallback.run(input_data)
            return fallback_result.model_copy(
                update={
                    "content": f"Agent {agent_id} failed, fallback used: {exc}",
                    "agent_id": fallback.id,
                }
            )

    async def run_for_message(self, input_data: AgentRunInput) -> list[AgentRunResult]:
        agent_id = route_agent(input_data.user_message)
        if agent_id == "orchestrator":
            orchestrated = await OrchestratorExecutor(registry=self._registry).run(input_data)
            return [orchestrated]
        return [await self.run(input_data.model_copy(update={"context": {"agent_id": agent_id}}))]

    async def stream(self, input_data: AgentRunInput) -> AsyncIterator[str]:
        for event, data in [
            ("status", {"message": "Orchestrator 正在拆解任务"}),
            ("status", {"message": "Code Agent 正在生成代码"}),
            ("status", {"message": "Review Agent 正在检查"}),
            ("status", {"message": "Preview Agent 正在准备"}),
        ]:
            yield self._format_sse(event, data)

        result = await self.run(input_data)
        yield self._format_sse("done", result.model_dump(mode="json"))

    def _format_sse(self, event: str, data: object) -> str:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    def _infer_role(self, agent_id: str) -> AgentRole:
        roles: dict[str, AgentRole] = {
            "orchestrator": "orchestrator",
            "code-agent": "code",
            "review-agent": "review",
            "preview-agent": "preview",
        }
        return roles.get(agent_id, "custom")
