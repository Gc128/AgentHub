import json
from collections.abc import AsyncIterator
from typing import Literal

from agenthub.agents.registry import AgentRegistry
from agenthub.core.errors import AgentExecutionError, NotFoundError
from agenthub.orchestrator.planner import create_plan
from agenthub.orchestrator.router import route_agent
from agenthub.schemas.agent import Agent, AgentRunInput, AgentRunResult
from agenthub.schemas.artifact import Artifact
from agenthub.schemas.message import Message

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
                adapter_type="mock" if adapter.__class__.__name__ == "MockAgent" else "custom",
            )
            for adapter in self._registry.list()
        ]

    async def run(self, input_data: AgentRunInput) -> AgentRunResult:
        agent_id = str(
            input_data.context.get("agent_id")
            or route_agent(input_data.user_message)
            or "orchestrator"
        )
        if agent_id == "orchestrator":
            return self._build_orchestrator_plan_result(input_data)
        try:
            agent = self._registry.get(agent_id)
            return await agent.run(input_data)
        except NotFoundError:
            raise
        except AgentExecutionError:
            raise
        except Exception as exc:
            try:
                fallback = self._registry.get("mock-agent")
            except NotFoundError as fallback_missing:
                raise AgentExecutionError(str(exc)) from fallback_missing
            fallback_result = await fallback.run(input_data)
            return fallback_result.model_copy(
                update={
                    "content": f"Agent {agent_id} failed, fallback used: {exc}",
                    "agent_id": fallback.id,
                }
            )

    async def run_for_message(self, input_data: AgentRunInput) -> list[AgentRunResult]:
        agent_id = route_agent(input_data.user_message)
        if agent_id is None:
            return []
        if agent_id == "orchestrator":
            return await self._run_orchestrator_pipeline(input_data)
        try:
            return [
                await self.run(input_data.model_copy(update={"context": {"agent_id": agent_id}}))
            ]
        except AgentExecutionError as exc:
            return [self._build_agent_error_result(agent_id, exc)]

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

    def _build_orchestrator_plan_result(self, input_data: AgentRunInput) -> AgentRunResult:
        plan = create_plan(input_data.user_message)
        lines = [
            f"{index}. {task.agent_id}: {task.instruction}"
            for index, task in enumerate(plan.tasks, start=1)
        ]
        return AgentRunResult(
            agent_id="orchestrator",
            content="## 任务拆解\n\n" + "\n".join(lines),
            artifacts=[
                Artifact(
                    id="artifact-orchestrator-plan",
                    type="file",
                    title="Orchestrator task plan",
                    data={
                        **plan.model_dump(mode="json"),
                        "agent_ids": plan.agent_ids,
                    },
                )
            ],
            next_actions=plan.agent_ids,
        )

    async def _run_orchestrator_pipeline(self, input_data: AgentRunInput) -> list[AgentRunResult]:
        plan = create_plan(input_data.user_message)
        plan_result = self._build_orchestrator_plan_result(input_data)
        results = [plan_result]
        history = [
            *input_data.history,
            Message(
                id="history-orchestrator-plan",
                conversation_id=input_data.conversation_id,
                role="agent",
                sender_id="orchestrator",
                content=plan_result.content,
                artifacts=plan_result.artifacts,
            ),
        ]
        prior_artifacts = [artifact.model_dump(mode="json") for artifact in plan_result.artifacts]

        for task in plan.tasks:
            if task.agent_id == "orchestrator":
                continue
            task_input = input_data.model_copy(
                update={
                    "history": history,
                    "context": {
                        **input_data.context,
                        "agent_id": task.agent_id,
                        "task_id": task.task_id,
                        "instruction": task.instruction,
                        "prior_artifacts": prior_artifacts,
                    },
                }
            )
            try:
                result = await self.run(task_input)
            except AgentExecutionError as exc:
                result = self._build_agent_error_result(task.agent_id, exc)
                results.append(result)
                history.append(
                    Message(
                        id=f"history-{task.task_id}",
                        conversation_id=input_data.conversation_id,
                        role="agent",
                        sender_id=result.agent_id,
                        content=result.content,
                        artifacts=result.artifacts,
                    )
                )
                break
            results.append(result)
            prior_artifacts.extend(
                artifact.model_dump(mode="json") for artifact in result.artifacts
            )
            history.append(
                Message(
                    id=f"history-{task.task_id}",
                    conversation_id=input_data.conversation_id,
                    role="agent",
                    sender_id=result.agent_id,
                    content=result.content,
                    artifacts=result.artifacts,
                )
            )
        return results

    def _build_agent_error_result(self, agent_id: str, exc: Exception) -> AgentRunResult:
        return AgentRunResult(
            agent_id=agent_id,
            content=(
                f"Agent {agent_id} failed: {exc}\n\n"
                "请检查 `.env` 中的 OPENAI_API_KEY、AGENT_BASE_URL、AGENT_MODEL，"
                "以及本机是否能访问该 OpenAI-compatible 服务。"
            ),
            artifacts=[],
            next_actions=[],
        )
