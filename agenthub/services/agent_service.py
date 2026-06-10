import asyncio
import json
import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import ValidationError

from agenthub.agents.backends import (
    CLAUDE_CODE_CLI_BACKEND_ID,
    CODEX_CLI_BACKEND_ID,
    OPENAI_COMPATIBLE_BACKEND_ID,
    backend_exists,
    list_agent_backends,
)
from agenthub.agents.custom_agent import CustomAgentAdapter
from agenthub.agents.real_agent import (
    RealAgentConfigurationError,
    RealAgentSchemaError,
    RealAgentTransportError,
    RealAgentUnavailableError,
)
from agenthub.agents.registry import AGENT_CLAUDE_CODE, AGENT_CODEX, AgentRegistry
from agenthub.config import Settings
from agenthub.core.errors import AgentExecutionError, BadRequestError, NotFoundError
from agenthub.orchestrator.harness import ExecutionReport, StepRun, VerificationResult
from agenthub.orchestrator.planner import (
    AGENT_CODE,
    AGENT_ORCHESTRATOR,
    AGENT_PREVIEW,
    AGENT_REVIEW,
    AgentTask,
    OrchestratorDecision,
    OrchestratorPlan,
    create_plan,
)
from agenthub.orchestrator.router import route_agent
from agenthub.repositories.custom_agent_repo import CustomAgentRepository
from agenthub.schemas.agent import Agent, AgentAdapter, AgentBackend, AgentRunInput, AgentRunResult
from agenthub.schemas.custom_agent import CustomAgent, CustomAgentCreate, CustomAgentUpdate
from agenthub.schemas.message import Message
from agenthub.utils.ids import new_id

AgentRole = Literal["orchestrator", "code", "review", "preview", "custom"]
AgentStreamEvent = tuple[str, dict[str, Any]]

_MAX_STEP_ATTEMPTS = 2
_CHAT_RE = re.compile(r"^(你好|您好|hello|hi|hey|嗨|在吗|谢谢|thanks)[!！。\\s]*$", re.I)
_DEV_RE = re.compile(
    r"写|实现|生成|创建|开发|构建|编写|制作|页面|网页|组件|功能|代码|"
    r"待办|清单|bug|修复|优化|预览|检查|"
    r"todo|list|app|review|code|implement|create|build|fix|preview",
    re.I,
)

_RESERVED_AGENT_IDS = {
    AGENT_ORCHESTRATOR,
    AGENT_CODE,
    AGENT_REVIEW,
    AGENT_PREVIEW,
}


class AgentService:
    def __init__(
        self,
        registry: AgentRegistry,
        custom_agent_repository: CustomAgentRepository | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._registry = registry
        self._custom_agent_repository = custom_agent_repository
        self._settings = settings

    async def list_agents(self) -> list[Agent]:
        built_in_agents = [
            Agent(
                id=adapter.id,
                name=adapter.name,
                role=self._infer_role(adapter.id),
                description=f"{adapter.name} adapter",
                capabilities=adapter.capabilities,
                adapter_type=self._adapter_type_for_builtin_agent(adapter),
            )
            for adapter in self._registry.list()
        ]
        return [*built_in_agents, *await self._list_enabled_custom_agent_summaries()]

    async def list_custom_agents(self) -> list[CustomAgent]:
        if self._custom_agent_repository is None:
            return []
        return await self._custom_agent_repository.list()

    async def list_agent_backends(self) -> list[AgentBackend]:
        if self._settings is None:
            return []
        return list_agent_backends(self._settings)

    async def create_custom_agent(self, request: CustomAgentCreate) -> CustomAgent:
        if self._custom_agent_repository is None:
            raise AgentExecutionError("Custom Agent repository is not configured.")
        await self._ensure_custom_agent_name_is_allowed(request.name)
        backend_id = self._normalize_backend_id(request.backend_id)
        now = _utc_now()
        agent = CustomAgent(
            id=new_id("custom-agent"),
            name=request.name.strip(),
            description=request.description.strip(),
            system_prompt=request.system_prompt.strip(),
            backend_id=backend_id,
            capabilities=_normalize_capabilities(request.capabilities),
            is_enabled=request.is_enabled,
            created_at=now,
            updated_at=now,
        )
        return await self._custom_agent_repository.save(agent)

    async def update_custom_agent(
        self,
        agent_id: str,
        request: CustomAgentUpdate,
    ) -> CustomAgent:
        if self._custom_agent_repository is None:
            raise NotFoundError("custom_agent_not_found", "Custom Agent does not exist.")
        agent = await self._custom_agent_repository.get(agent_id)
        next_name = request.name.strip() if request.name is not None else agent.name
        if next_name != agent.name:
            await self._ensure_custom_agent_name_is_allowed(next_name, exclude_agent_id=agent.id)
        updated = agent.model_copy(
            update={
                "name": next_name,
                "description": request.description.strip()
                if request.description is not None
                else agent.description,
                "system_prompt": request.system_prompt.strip()
                if request.system_prompt is not None
                else agent.system_prompt,
                "backend_id": self._normalize_backend_id(request.backend_id)
                if request.backend_id is not None
                else agent.backend_id,
                "capabilities": _normalize_capabilities(request.capabilities)
                if request.capabilities is not None
                else agent.capabilities,
                "is_enabled": request.is_enabled
                if request.is_enabled is not None
                else agent.is_enabled,
                "updated_at": _utc_now(),
            }
        )
        return await self._custom_agent_repository.save(updated)

    async def delete_custom_agent(self, agent_id: str) -> None:
        if self._custom_agent_repository is None:
            raise NotFoundError("custom_agent_not_found", "Custom Agent does not exist.")
        await self._custom_agent_repository.delete(agent_id)

    async def test_custom_agent(self, agent_id: str, message: str) -> AgentRunResult:
        adapter = await self._custom_agent_adapter(agent_id)
        return await adapter.run(
            AgentRunInput(
                conversation_id="custom_agent_test",
                workspace_id="custom_agent_test",
                user_message=message,
                history=[],
                context={"agent_id": agent_id},
            )
        )

    async def run(self, input_data: AgentRunInput) -> AgentRunResult:
        agent_id = await self._resolve_agent_id(input_data)
        if agent_id == AGENT_ORCHESTRATOR:
            try:
                decision = await self._decide_orchestrator(input_data)
            except AgentExecutionError as exc:
                return self._build_agent_error_result(AGENT_ORCHESTRATOR, exc)
            return self._result_from_orchestrator_decision(decision)
        try:
            agent = await self._get_agent_adapter(agent_id)
            return await agent.run(input_data)
        except NotFoundError:
            raise
        except AgentExecutionError:
            raise
        except RealAgentUnavailableError as exc:
            raise AgentExecutionError(str(exc)) from exc
        except Exception as exc:
            raise AgentExecutionError(str(exc)) from exc

    async def run_for_message(self, input_data: AgentRunInput) -> list[AgentRunResult]:
        agent_id = await self._route_message_agent(input_data.user_message)
        if agent_id is None or agent_id == AGENT_ORCHESTRATOR:
            try:
                decision = await self._decide_orchestrator(input_data)
            except AgentExecutionError as exc:
                return [self._build_agent_error_result(AGENT_ORCHESTRATOR, exc)]
            if decision.mode == "plan" and decision.plan is not None:
                return await self._run_orchestrator_pipeline(
                    input_data,
                    plan=decision.plan,
                    plan_content=decision.content,
                )
            return [self._result_from_orchestrator_decision(decision)]
        try:
            return [
                await self.run(
                    input_data.model_copy(
                        update={
                            "context": {
                                **input_data.context,
                                "agent_id": agent_id,
                                "user_request": input_data.user_message,
                            }
                        }
                    )
                )
            ]
        except AgentExecutionError as exc:
            return [self._build_agent_error_result(agent_id, exc)]

    async def stream_for_message(
        self, input_data: AgentRunInput
    ) -> AsyncIterator[AgentStreamEvent]:
        agent_id = await self._route_message_agent(input_data.user_message)
        if agent_id is None:
            async for event in self._stream_orchestrator_entry(input_data):
                yield event
            return
        if agent_id == AGENT_ORCHESTRATOR:
            async for event in self._stream_orchestrator_entry(input_data):
                yield event
            return

        agent_name = await self._agent_display_name(agent_id)
        yield (
            "harness_step",
            {
                "status": "started",
                "agent_id": agent_id,
                "message": f"{agent_name} 正在生成回复",
            },
        )
        try:
            result = await self.run(
                input_data.model_copy(
                    update={
                        "context": {
                            **input_data.context,
                            "agent_id": agent_id,
                            "user_request": input_data.user_message,
                        }
                    }
                )
            )
        except AgentExecutionError as exc:
            result = self._build_agent_error_result(agent_id, exc)
        async for event in self._stream_result(result):
            yield event

    async def stream(self, input_data: AgentRunInput) -> AsyncIterator[str]:
        async for event, data in self.stream_for_message(input_data):
            yield self._format_sse(event, data)
        yield self._format_sse("done", {})

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

    def _adapter_type_for_builtin_agent(
        self,
        adapter: AgentAdapter,
    ) -> Literal["mock", "codex", "claude", "custom"]:
        if adapter.__class__.__name__ == "MockAgent":
            return "mock"
        if adapter.id == AGENT_CODEX:
            return "codex"
        if adapter.id == AGENT_CLAUDE_CODE:
            return "claude"
        if adapter.id == AGENT_CODE and self._settings is not None:
            if self._settings.code_agent_backend_id == CODEX_CLI_BACKEND_ID:
                return "codex"
            if self._settings.code_agent_backend_id == CLAUDE_CODE_CLI_BACKEND_ID:
                return "claude"
        return "custom"

    async def _resolve_agent_id(self, input_data: AgentRunInput) -> str:
        explicit_agent_id = input_data.context.get("agent_id")
        if isinstance(explicit_agent_id, str) and explicit_agent_id:
            return explicit_agent_id
        routed_agent_id = await self._route_message_agent(input_data.user_message)
        return routed_agent_id or AGENT_ORCHESTRATOR

    async def _route_message_agent(self, message: str) -> str | None:
        built_in_agent_id = route_agent(message)
        if built_in_agent_id is not None:
            return built_in_agent_id
        return await self._route_custom_agent(message)

    async def _get_agent_adapter(self, agent_id: str) -> AgentAdapter:
        try:
            return self._registry.get(agent_id)
        except NotFoundError as exc:
            try:
                return await self._custom_agent_adapter(agent_id)
            except NotFoundError as custom_exc:
                raise NotFoundError(
                    "agent_not_found",
                    f"Agent '{agent_id}' does not exist.",
                ) from (custom_exc if agent_id.startswith("custom-agent") else exc)

    async def _agent_display_name(self, agent_id: str) -> str:
        try:
            return (await self._get_agent_adapter(agent_id)).name
        except NotFoundError:
            return agent_id

    async def _custom_agent_adapter(self, agent_id: str) -> CustomAgentAdapter:
        if self._custom_agent_repository is None:
            raise NotFoundError("custom_agent_not_found", "Custom Agent does not exist.")
        agent = await self._custom_agent_repository.get(agent_id)
        if not agent.is_enabled:
            raise NotFoundError("agent_not_found", f"Agent '{agent_id}' does not exist.")
        return CustomAgentAdapter(agent, settings=self._settings)

    async def _list_enabled_custom_agent_summaries(self) -> list[Agent]:
        if self._custom_agent_repository is None:
            return []
        return [
            Agent(
                id=agent.id,
                name=agent.name,
                role="custom",
                description=agent.description,
                capabilities=agent.capabilities,
                adapter_type=self._adapter_type_for_custom_agent(agent),
            )
            for agent in await self._custom_agent_repository.list_enabled()
        ]

    async def _route_custom_agent(self, message: str) -> str | None:
        if self._custom_agent_repository is None:
            return None
        normalized_message = _normalize_mention_text(message)
        for agent in await self._custom_agent_repository.list_enabled():
            labels = {
                _normalize_mention_text(f"@{agent.name}"),
                _normalize_mention_text(f"@{agent.id}"),
            }
            if any(label and label in normalized_message for label in labels):
                return agent.id
        return None

    async def _ensure_custom_agent_name_is_allowed(
        self,
        name: str,
        exclude_agent_id: str | None = None,
    ) -> None:
        normalized_name = _normalize_mention_text(name)
        if not normalized_name:
            raise BadRequestError("invalid_custom_agent_name", "Custom Agent name is required.")
        reserved_names = {
            _normalize_mention_text("Orchestrator"),
            _normalize_mention_text("CodeAgent"),
            _normalize_mention_text("ReviewAgent"),
            _normalize_mention_text("PreviewAgent"),
            *(_normalize_mention_text(agent_id) for agent_id in _RESERVED_AGENT_IDS),
        }
        if normalized_name in reserved_names:
            raise BadRequestError(
                "reserved_custom_agent_name",
                "Custom Agent name conflicts with a built-in Agent.",
            )
        if self._custom_agent_repository is None:
            return
        for agent in await self._custom_agent_repository.list():
            if (
                agent.id != exclude_agent_id
                and _normalize_mention_text(agent.name) == normalized_name
            ):
                raise BadRequestError(
                    "duplicate_custom_agent_name",
                    "Custom Agent name already exists.",
                )

    def _normalize_backend_id(self, backend_id: str) -> str:
        normalized = backend_id.strip() or OPENAI_COMPATIBLE_BACKEND_ID
        if not backend_exists(normalized):
            raise BadRequestError(
                "unsupported_agent_backend",
                f"Agent backend '{backend_id}' is not supported.",
            )
        return normalized

    def _adapter_type_for_custom_agent(
        self,
        agent: CustomAgent,
    ) -> Literal["mock", "codex", "claude", "custom"]:
        if self._settings is not None and self._settings.use_mock_agents:
            return "mock"
        if agent.backend_id == CODEX_CLI_BACKEND_ID:
            return "codex"
        if agent.backend_id == CLAUDE_CODE_CLI_BACKEND_ID:
            return "claude"
        return "custom"

    async def _decide_orchestrator(self, input_data: AgentRunInput) -> OrchestratorDecision:
        adapter = self._registry.get(AGENT_ORCHESTRATOR)
        decide = getattr(adapter, "decide", None)
        if callable(decide):
            try:
                decision = await decide(
                    input_data.model_copy(
                        update={
                            "context": {
                                **input_data.context,
                                "agent_id": AGENT_ORCHESTRATOR,
                                "user_request": input_data.user_message,
                            }
                        }
                    )
                )
                return _ensure_required_harness_tasks(OrchestratorDecision.model_validate(decision))
            except (RealAgentSchemaError, ValidationError):
                return self._fallback_orchestrator_decision(input_data)
            except RealAgentUnavailableError as exc:
                raise AgentExecutionError(str(exc)) from exc
        plan = create_plan(input_data.user_message)
        if _has_child_agent_tasks(plan):
            return OrchestratorDecision(
                mode="plan",
                content=self._build_orchestrator_plan_result(input_data, plan).content,
                plan=plan,
            )
        return OrchestratorDecision(
            mode="chat",
            content=self._build_chat_result(input_data).content,
        )

    def _fallback_orchestrator_decision(
        self,
        input_data: AgentRunInput,
    ) -> OrchestratorDecision:
        if _looks_like_development_request(input_data.user_message):
            plan = create_plan(input_data.user_message)
            if _has_child_agent_tasks(plan):
                return OrchestratorDecision(
                    mode="plan",
                    content=_build_orchestrator_safe_fallback_content(plan),
                    plan=plan,
                )
        return OrchestratorDecision(
            mode="chat",
            content=self._build_chat_result(input_data).content,
        )

    def _result_from_orchestrator_decision(
        self,
        decision: OrchestratorDecision,
    ) -> AgentRunResult:
        return AgentRunResult(
            agent_id=AGENT_ORCHESTRATOR,
            content=decision.content,
            artifacts=[],
            next_actions=decision.plan.agent_ids if decision.plan else [],
        )

    def _build_orchestrator_plan_result(
        self,
        input_data: AgentRunInput,
        plan: OrchestratorPlan | None = None,
        plan_content: str | None = None,
    ) -> AgentRunResult:
        plan = plan or create_plan(input_data.user_message)
        lines = [
            f"{index}. **{task.agent_id}** - {task.instruction}"
            for index, task in enumerate(plan.tasks, start=1)
            if task.agent_id != AGENT_ORCHESTRATOR
        ]
        content = plan_content or "## 任务拆解\n\n" + "\n".join(lines)
        if not lines:
            content = self._build_chat_result(input_data).content
        return AgentRunResult(
            agent_id=AGENT_ORCHESTRATOR,
            content=content,
            artifacts=[],
            next_actions=plan.agent_ids,
        )

    def _build_chat_result(self, input_data: AgentRunInput) -> AgentRunResult:
        message = input_data.user_message.strip()
        if _CHAT_RE.match(message):
            content = (
                "你好，我是 AgentHub Orchestrator。你可以直接描述需求，也可以 "
                "@CodeAgent、@ReviewAgent 或 @PreviewAgent 指定协作对象。"
            )
        else:
            content = (
                "我已收到。你可以继续补充目标、约束或期望效果；如果这是开发任务，"
                "我会为 Code、Review 和 Preview Agent 拆解执行步骤。"
            )
        return AgentRunResult(
            agent_id=AGENT_ORCHESTRATOR,
            content=content,
            artifacts=[],
            next_actions=[],
        )

    async def _run_orchestrator_pipeline(
        self,
        input_data: AgentRunInput,
        *,
        plan: OrchestratorPlan | None = None,
        plan_content: str | None = None,
    ) -> list[AgentRunResult]:
        plan = plan or create_plan(input_data.user_message)
        results = [self._build_orchestrator_plan_result(input_data, plan, plan_content)]
        history = _history_with_results(input_data.history, input_data.conversation_id, results)
        prior_artifacts = _artifact_payloads(results)
        report = ExecutionReport(plan_summary=plan.summary)

        for task in _child_tasks(plan):
            task_result = await self._run_harness_step(
                task=task,
                input_data=input_data,
                history=history,
                prior_artifacts=prior_artifacts,
                report=report,
            )
            results.append(task_result)
            history.append(
                Message(
                    id=f"history-{task.task_id}",
                    conversation_id=input_data.conversation_id,
                    role="agent",
                    sender_id=task_result.agent_id,
                    content=task_result.content,
                    artifacts=task_result.artifacts,
                )
            )
            prior_artifacts.extend(
                artifact.model_dump(mode="json") for artifact in task_result.artifacts
            )
            if task_result.agent_id == task.agent_id and task_result.content.startswith("Agent "):
                report.succeeded = False
                break

        return results

    async def _stream_orchestrator_entry(
        self,
        input_data: AgentRunInput,
    ) -> AsyncIterator[AgentStreamEvent]:
        yield ("harness_step", {"status": "started", "message": "Orchestrator 正在理解需求"})
        try:
            decision = await self._decide_orchestrator(input_data)
        except AgentExecutionError as exc:
            async for event in self._stream_result(
                self._build_agent_error_result(AGENT_ORCHESTRATOR, exc)
            ):
                yield event
            return
        if decision.mode != "plan" or decision.plan is None:
            result = self._result_from_orchestrator_decision(decision)
            async for event in self._stream_result(result):
                yield event
            return
        async for event in self._stream_orchestrator_pipeline(
            input_data,
            plan=decision.plan,
            plan_content=decision.content,
        ):
            yield event

    async def _stream_orchestrator_pipeline(
        self,
        input_data: AgentRunInput,
        *,
        plan: OrchestratorPlan,
        plan_content: str | None = None,
    ) -> AsyncIterator[AgentStreamEvent]:
        plan_result = self._build_orchestrator_plan_result(input_data, plan, plan_content)
        yield ("harness_step", {"status": "started", "message": "Orchestrator 已生成执行计划"})
        async for event in self._stream_result(plan_result):
            yield event

        results = [plan_result]
        history = _history_with_results(input_data.history, input_data.conversation_id, results)
        prior_artifacts = _artifact_payloads(results)
        report = ExecutionReport(plan_summary=plan.summary)

        for task in _child_tasks(plan):
            yield (
                "harness_step",
                {
                    "status": "started",
                    "task_id": task.task_id,
                    "agent_id": task.agent_id,
                    "message": f"{task.agent_id} 开始执行",
                },
            )
            task_result = await self._run_harness_step(
                task=task,
                input_data=input_data,
                history=history,
                prior_artifacts=prior_artifacts,
                report=report,
            )
            async for event in self._stream_result(task_result):
                yield event
            verification = report.steps[-1].verification if report.steps else None
            yield (
                "harness_step",
                {
                    "status": "succeeded" if verification and verification.ok else "failed",
                    "task_id": task.task_id,
                    "agent_id": task.agent_id,
                    "message": verification.message if verification else "步骤完成",
                    "issues": verification.issues if verification else [],
                },
            )
            results.append(task_result)
            history.append(
                Message(
                    id=f"history-{task.task_id}",
                    conversation_id=input_data.conversation_id,
                    role="agent",
                    sender_id=task_result.agent_id,
                    content=task_result.content,
                    artifacts=task_result.artifacts,
                )
            )
            prior_artifacts.extend(
                artifact.model_dump(mode="json") for artifact in task_result.artifacts
            )
            if verification and not verification.ok:
                report.succeeded = False
                break

    async def _run_harness_step(
        self,
        *,
        task: AgentTask,
        input_data: AgentRunInput,
        history: list[Message],
        prior_artifacts: list[dict[str, Any]],
        report: ExecutionReport,
    ) -> AgentRunResult:
        last_result: AgentRunResult | None = None
        for attempt in range(1, _MAX_STEP_ATTEMPTS + 1):
            task_input = input_data.model_copy(
                update={
                    "history": history,
                    "context": {
                        **input_data.context,
                        "agent_id": task.agent_id,
                        "task_id": task.task_id,
                        "instruction": task.instruction,
                        "user_request": input_data.user_message,
                        "prior_artifacts": prior_artifacts,
                    },
                    "user_message": _task_user_message(task, input_data.user_message),
                }
            )
            try:
                result = await self.run(task_input)
            except AgentExecutionError as exc:
                verification = VerificationResult(
                    ok=False,
                    message=f"{task.agent_id} 执行失败",
                    issues=[str(exc)],
                )
                report.steps.append(
                    StepRun(
                        task_id=task.task_id,
                        agent_id=task.agent_id,
                        attempt=attempt,
                        status="failed",
                        verification=verification,
                        error=str(exc),
                    )
                )
                if attempt == _MAX_STEP_ATTEMPTS:
                    return self._build_agent_error_result(task.agent_id, exc)
                continue

            verification = _verify_agent_result(task.agent_id, result)
            report.steps.append(
                StepRun(
                    task_id=task.task_id,
                    agent_id=task.agent_id,
                    attempt=attempt,
                    status="succeeded" if verification.ok else "failed",
                    verification=verification,
                )
            )
            last_result = result
            if verification.ok:
                return result

        report.succeeded = False
        if last_result is None:
            return self._build_agent_error_result(
                task.agent_id, AgentExecutionError("Agent failed.")
            )
        issues = report.steps[-1].verification.issues if report.steps[-1].verification else []
        return last_result.model_copy(
            update={
                "content": last_result.content
                + "\n\n"
                + "Harness 校验未通过："
                + ("；".join(issues) if issues else "产物不满足当前步骤要求。")
            }
        )

    async def _stream_result(self, result: AgentRunResult) -> AsyncIterator[AgentStreamEvent]:
        yield ("agent_started", {"agent_id": result.agent_id})
        for chunk in _content_chunks(result.content):
            yield ("agent_delta", {"agent_id": result.agent_id, "delta": chunk})
            await asyncio.sleep(0.015)
        for artifact in result.artifacts:
            yield (
                "artifact",
                {
                    "agent_id": result.agent_id,
                    "artifact": artifact.model_dump(mode="json"),
                },
            )
        yield ("agent_done", {"result": result.model_dump(mode="json")})

    def _build_agent_error_result(self, agent_id: str, exc: Exception) -> AgentRunResult:
        message = _agent_error_message(agent_id, exc)
        return AgentRunResult(
            agent_id=agent_id,
            content=message,
            artifacts=[],
            next_actions=[],
        )


def _looks_like_development_request(message: str) -> bool:
    if not message or _CHAT_RE.match(message.strip()):
        return False
    return bool(_DEV_RE.search(message))


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _normalize_capabilities(values: list[str]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        capability = value.strip()
        if capability and capability not in normalized:
            normalized.append(capability)
    return normalized


def _normalize_mention_text(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()


def _ensure_required_harness_tasks(decision: OrchestratorDecision) -> OrchestratorDecision:
    if decision.mode != "plan" or decision.plan is None:
        return decision

    next_plan = _ensure_plan_has_required_harness_tasks(decision.plan)
    if next_plan == decision.plan:
        return decision
    return decision.model_copy(
        update={
            "plan": next_plan,
            "content": _build_guarded_harness_content(next_plan),
        }
    )


def _ensure_plan_has_required_harness_tasks(plan: OrchestratorPlan) -> OrchestratorPlan:
    tasks = list(plan.tasks)
    if not any(task.agent_id == AGENT_CODE for task in tasks):
        return plan

    base_tasks = [task for task in tasks if task.agent_id not in {AGENT_REVIEW, AGENT_PREVIEW}]
    last_code_task_id = next(
        task.task_id for task in reversed(base_tasks) if task.agent_id == AGENT_CODE
    )

    review_task = next((task for task in tasks if task.agent_id == AGENT_REVIEW), None)
    if review_task is None:
        review_task = AgentTask(
            task_id="task-review",
            agent_id=AGENT_REVIEW,
            instruction=(
                "审查 Code Agent 的代码和 diff，检查功能完整性、交互风险、路径安全，"
                "并输出 findings 与 risk_level。"
            ),
            depends_on=[last_code_task_id],
        )
    elif not review_task.depends_on:
        review_task = review_task.model_copy(update={"depends_on": [last_code_task_id]})

    preview_task = next((task for task in tasks if task.agent_id == AGENT_PREVIEW), None)
    if preview_task is None:
        preview_task = AgentTask(
            task_id="task-preview",
            agent_id=AGENT_PREVIEW,
            instruction=(
                "基于 workspace preview 状态和前序产物验证页面入口、preview_url 与可访问性，"
                "输出 preview artifact 和可读检查结论。"
            ),
            depends_on=[review_task.task_id],
        )
    elif not preview_task.depends_on:
        preview_task = preview_task.model_copy(update={"depends_on": [review_task.task_id]})

    return OrchestratorPlan(
        summary=plan.summary or "AgentHub guarded harness plan",
        tasks=[*base_tasks, review_task, preview_task],
    )


def _build_guarded_harness_content(plan: OrchestratorPlan) -> str:
    lines = [
        "## 任务拆解",
        "",
        "我将按以下步骤执行并校验产物：",
        "",
    ]
    for index, task in enumerate(_child_tasks(plan), start=1):
        dependency_text = f"；依赖：{', '.join(task.depends_on)}" if task.depends_on else ""
        lines.append(f"{index}. **{task.agent_id}** - {task.instruction}{dependency_text}")
    return "\n".join(lines)


def _agent_error_message(agent_id: str, exc: Exception) -> str:
    cause = exc.__cause__
    text = str(exc)
    if isinstance(cause, RealAgentSchemaError) or isinstance(exc, RealAgentSchemaError):
        return (
            f"Agent {agent_id} failed: 模型连续返回了不符合结构要求的内容。\n\n"
            "系统已静默重试输出格式，但最终仍无法解析为 AgentHub 需要的结构。"
            "可以尝试更换模型、降低结构化输出难度，或让该 Agent 输出更短的结果。"
        )
    if isinstance(cause, RealAgentConfigurationError) or isinstance(
        exc, RealAgentConfigurationError
    ):
        return (
            f"Agent {agent_id} failed: {text}\n\n"
            "请检查 `.env` 中的 OPENAI_API_KEY、AGENT_BASE_URL、AGENT_MODEL。"
        )
    if isinstance(cause, RealAgentTransportError) or isinstance(exc, RealAgentTransportError):
        return (
            f"Agent {agent_id} failed: {text}\n\n"
            "请检查本机网络、供应商服务状态，以及 AGENT_REQUEST_TIMEOUT_SECONDS。"
        )
    return f"Agent {agent_id} failed: {text}"


def _has_child_agent_tasks(plan: OrchestratorPlan) -> bool:
    return any(task.agent_id != AGENT_ORCHESTRATOR for task in plan.tasks)


def _build_orchestrator_safe_fallback_content(plan: OrchestratorPlan) -> str:
    lines = [
        "## 任务拆解",
        "",
        "Orchestrator 将按以下分工继续调用后续 Agent。",
        "",
    ]
    for index, task in enumerate(_child_tasks(plan), start=1):
        lines.append(f"{index}. **{task.agent_id}** - {task.instruction}")
    return "\n".join(lines)


def _child_tasks(plan: OrchestratorPlan) -> list[AgentTask]:
    return [task for task in plan.tasks if task.agent_id != AGENT_ORCHESTRATOR]


def _task_user_message(task: AgentTask, original_user_message: str) -> str:
    if task.agent_id != AGENT_CODE:
        return task.instruction
    return (
        f"{task.instruction}\n\n"
        "用户原始需求如下，Code Agent 必须以这段需求为实现依据，不得只实现泛化任务：\n"
        f"{original_user_message}"
    )


def _history_with_results(
    history: list[Message],
    conversation_id: str,
    results: list[AgentRunResult],
) -> list[Message]:
    next_history = list(history)
    for result in results:
        next_history.append(
            Message(
                id=f"history-{result.agent_id}",
                conversation_id=conversation_id,
                role="agent",
                sender_id=result.agent_id,
                content=result.content,
                artifacts=result.artifacts,
            )
        )
    return next_history


def _artifact_payloads(results: list[AgentRunResult]) -> list[dict[str, Any]]:
    return [artifact.model_dump(mode="json") for result in results for artifact in result.artifacts]


def _verify_agent_result(agent_id: str, result: AgentRunResult) -> VerificationResult:
    artifact_types = {artifact.type for artifact in result.artifacts}
    if agent_id == AGENT_CODE:
        issues = []
        if "code" not in artifact_types:
            issues.append("Code Agent 缺少 code artifact")
        if "diff" not in artifact_types:
            issues.append("Code Agent 缺少 diff artifact")
        return VerificationResult(
            ok=not issues,
            message="Code Agent 产物校验通过" if not issues else "Code Agent 产物校验失败",
            issues=issues,
        )
    if agent_id == AGENT_REVIEW:
        review_artifact = next(
            (artifact for artifact in result.artifacts if artifact.type == "file"), None
        )
        issues = []
        if review_artifact is None:
            issues.append("Review Agent 缺少 file review artifact")
        elif not ("findings" in review_artifact.data and "risk_level" in review_artifact.data):
            issues.append("Review artifact 缺少 findings 或 risk_level")
        return VerificationResult(
            ok=not issues,
            message="Review Agent 校验通过" if not issues else "Review Agent 校验失败",
            issues=issues,
        )
    if agent_id == AGENT_PREVIEW:
        issues = []
        if "preview" not in artifact_types:
            issues.append("Preview Agent 缺少 preview artifact")
        return VerificationResult(
            ok=not issues,
            message="Preview Agent 校验通过" if not issues else "Preview Agent 校验失败",
            issues=issues,
        )
    return VerificationResult(ok=True, message=f"{agent_id} 校验通过")


def _content_chunks(content: str, *, size: int = 36) -> list[str]:
    if not content:
        return []
    chunks: list[str] = []
    current = ""
    for token in re.split(r"(\s+)", content):
        if len(current) + len(token) > size and current:
            chunks.append(current)
            current = token
        else:
            current += token
        while len(current) > size:
            chunks.append(current[:size])
            current = current[size:]
    if current:
        chunks.append(current)
    return chunks
