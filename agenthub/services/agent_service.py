import asyncio
import json
import logging
import re
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import ValidationError

from agenthub.agents.custom_agent import CustomAgentAdapter
from agenthub.agents.real_agent import (
    RealAgentConfigurationError,
    RealAgentSchemaError,
    RealAgentTransportError,
    RealAgentUnavailableError,
)
from agenthub.agents.registry import AgentRegistry
from agenthub.config import Settings
from agenthub.core.errors import AgentExecutionError, AgentHubError, BadRequestError, NotFoundError
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
from agenthub.schemas.agent import (
    AcceptanceCriterion,
    Agent,
    AgentAdapter,
    AgentRunInput,
    AgentRunResult,
    ReviewFinding,
    ReviewReport,
)
from agenthub.schemas.artifact import Artifact
from agenthub.schemas.change_set import ChangeSet
from agenthub.schemas.custom_agent import CustomAgent, CustomAgentCreate, CustomAgentUpdate
from agenthub.schemas.message import Message
from agenthub.schemas.run import AgentErrorCategory, AgentRunError
from agenthub.services.change_set_service import ChangeSetService
from agenthub.services.static_review import StaticCandidateInspector
from agenthub.utils.ids import new_id

AgentRole = Literal["orchestrator", "code", "review", "preview", "custom"]
AgentStreamEvent = tuple[str, dict[str, Any]]

_MAX_STEP_ATTEMPTS = 1
_CHAT_RE = re.compile(r"^(你好|您好|hello|hi|hey|嗨|在吗|谢谢|thanks)[!！。\\s]*$", re.I)
_DEV_RE = re.compile(
    r"写|实现|生成|创建|开发|构建|编写|制作|页面|网页|组件|功能|代码|"
    r"待办|清单|bug|修复|优化|预览|检查|"
    r"todo|list|app|review|code|implement|create|build|fix|preview",
    re.I,
)
_PREVIEW_REQUEST_RE = re.compile(r"@previewagent\b", re.I)

_RESERVED_AGENT_IDS = {
    AGENT_ORCHESTRATOR,
    AGENT_CODE,
    AGENT_REVIEW,
    AGENT_PREVIEW,
}
logger = logging.getLogger(__name__)


class AgentService:
    def __init__(
        self,
        registry: AgentRegistry,
        custom_agent_repository: CustomAgentRepository | None = None,
        settings: Settings | None = None,
        change_set_service: ChangeSetService | None = None,
        static_inspector: StaticCandidateInspector | None = None,
    ) -> None:
        self._registry = registry
        self._custom_agent_repository = custom_agent_repository
        self._settings = settings
        self._change_set_service = change_set_service
        self._static_inspector = static_inspector or StaticCandidateInspector()

    async def list_agents(self) -> list[Agent]:
        built_in_agents = [
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
        return [*built_in_agents, *await self._list_enabled_custom_agent_summaries()]

    async def list_custom_agents(self) -> list[CustomAgent]:
        if self._custom_agent_repository is None:
            return []
        return await self._custom_agent_repository.list()

    async def create_custom_agent(self, request: CustomAgentCreate) -> CustomAgent:
        if self._custom_agent_repository is None:
            raise AgentExecutionError("Custom Agent repository is not configured.")
        await self._ensure_custom_agent_name_is_allowed(request.name)
        now = _utc_now()
        agent = CustomAgent(
            id=new_id("custom-agent"),
            name=request.name.strip(),
            description=request.description.strip(),
            system_prompt=request.system_prompt.strip(),
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
            except AgentHubError as exc:
                return self._build_agent_error_result(AGENT_ORCHESTRATOR, exc)
            return self._result_from_orchestrator_decision(decision)
        try:
            if agent_id == AGENT_PREVIEW and self._change_set_service is not None:
                raw_artifacts = input_data.context.get("prior_artifacts", [])
                prior_artifacts = raw_artifacts if isinstance(raw_artifacts, list) else []
                return await self._build_manual_preview(input_data, prior_artifacts)
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
        if agent_id == AGENT_CODE and self._change_set_service is not None:
            plan = _direct_code_change_set_plan(input_data.user_message)
            return await self._run_orchestrator_pipeline(
                input_data,
                plan=plan,
                plan_content=(
                    "Code Agent 会生成隔离候选代码；系统随后执行静态安全检查和"
                    "Review，审查通过后由用户决定是否合入正式 Workspace。"
                ),
                include_plan_result=False,
            )
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

        if agent_id == AGENT_CODE and self._change_set_service is not None:
            async for event in self._stream_orchestrator_pipeline(
                input_data,
                plan=_direct_code_change_set_plan(input_data.user_message),
                plan_content=(
                    "Code Agent 会生成隔离候选代码；系统随后执行静态安全检查和"
                    "Review，通过后即可由用户手动合入正式 Workspace。"
                ),
                include_plan_result=False,
            ):
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
        adapter_type: Literal["mock", "custom"] = "custom"
        if self._settings is not None and self._settings.use_mock_agents:
            adapter_type = "mock"
        return [
            Agent(
                id=agent.id,
                name=agent.name,
                role="custom",
                description=agent.description,
                capabilities=agent.capabilities,
                adapter_type=adapter_type,
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
                return _ensure_required_harness_tasks(
                    OrchestratorDecision.model_validate(decision),
                    include_preview=bool(_PREVIEW_REQUEST_RE.search(input_data.user_message)),
                )
            except (RealAgentSchemaError, ValidationError) as exc:
                raise AgentExecutionError(
                    "Orchestrator model output could not be parsed after one format repair."
                ) from exc
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
                "我会为 Code 和 Review Agent 拆解执行步骤；Preview Agent 仅提供人工预览入口。"
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
        include_plan_result: bool = True,
    ) -> list[AgentRunResult]:
        plan = plan or create_plan(input_data.user_message)
        results = (
            [self._build_orchestrator_plan_result(input_data, plan, plan_content)]
            if include_plan_result
            else []
        )
        history = _history_with_results(input_data.history, input_data.conversation_id, results)
        prior_artifacts = _artifact_payloads(results)
        report = ExecutionReport(plan_summary=plan.summary)
        pipeline_input = input_data.model_copy(
            update={
                "context": {
                    **input_data.context,
                    "acceptance_criteria": [
                        item.model_dump(mode="json") for item in plan.acceptance_criteria
                    ],
                }
            }
        )

        for task in _child_tasks(plan):
            task_result = await self._run_harness_step(
                task=task,
                input_data=pipeline_input,
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

        repair_results = await self._run_auto_fix_cycle(
            input_data=pipeline_input,
            plan=plan,
            history=history,
            prior_artifacts=prior_artifacts,
            report=report,
        )
        results.extend(repair_results)
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
        include_plan_result: bool = True,
    ) -> AsyncIterator[AgentStreamEvent]:
        results: list[AgentRunResult] = []
        if include_plan_result:
            plan_result = self._build_orchestrator_plan_result(input_data, plan, plan_content)
            yield (
                "harness_step",
                {"status": "started", "message": "Orchestrator 已生成执行计划"},
            )
            async for event in self._stream_result(plan_result):
                yield event
            results.append(plan_result)
        history = _history_with_results(input_data.history, input_data.conversation_id, results)
        prior_artifacts = _artifact_payloads(results)
        report = ExecutionReport(plan_summary=plan.summary)
        pipeline_input = input_data.model_copy(
            update={
                "context": {
                    **input_data.context,
                    "acceptance_criteria": [
                        item.model_dump(mode="json") for item in plan.acceptance_criteria
                    ],
                }
            }
        )

        for task in _child_tasks(plan):
            if task.agent_id == AGENT_REVIEW:
                yield (
                    "validation_started",
                    {
                        "task_id": task.task_id,
                        "agent_id": task.agent_id,
                        "change_set_id": _change_set_id_from_artifacts(prior_artifacts),
                    },
                )
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
                input_data=pipeline_input,
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
            if _is_agent_error_result(task_result):
                report.succeeded = False
                break

        repair_results = await self._run_auto_fix_cycle(
            input_data=pipeline_input,
            plan=plan,
            history=history,
            prior_artifacts=prior_artifacts,
            report=report,
        )
        if repair_results:
            yield (
                "harness_step",
                {
                    "status": "retrying",
                    "message": "Review 发现真实 blocker，正在执行唯一一次代码修复并重新审查",
                },
            )
        for result in repair_results:
            async for event in self._stream_result(result):
                yield event

    async def _run_auto_fix_cycle(
        self,
        *,
        input_data: AgentRunInput,
        plan: OrchestratorPlan,
        history: list[Message],
        prior_artifacts: list[dict[str, Any]],
        report: ExecutionReport,
    ) -> list[AgentRunResult]:
        if self._change_set_service is None:
            return []
        parent_id = _change_set_id_from_artifacts(prior_artifacts)
        if parent_id is None:
            return []
        parent = await self._change_set_service.get(input_data.workspace_id, parent_id)
        if parent.status != "needs_fix" or parent.repair_count != 0:
            return []

        failure_context = {
            "review_report": parent.review_report.model_dump(mode="json")
            if parent.review_report
            else None,
        }
        repair_input = input_data.model_copy(
            update={
                "context": {
                    **input_data.context,
                    "parent_change_set_id": parent.id,
                    "repair_count": 1,
                    "validation_failures": failure_context,
                }
            }
        )
        repair_task = AgentTask(
            task_id="task-code-repair-1",
            agent_id=AGENT_CODE,
            instruction=(
                "修复前一候选 Change Set 中有具体证据的 Review blocker。"
                "只能返回一组完整候选文件，不得生成浏览器检查或声称已经通过。"
            ),
            depends_on=[],
        )
        cycle_results: list[AgentRunResult] = []
        repair_result = await self._run_harness_step(
            task=repair_task,
            input_data=repair_input,
            history=history,
            prior_artifacts=prior_artifacts,
            report=report,
        )
        cycle_results.append(repair_result)
        if _is_agent_error_result(repair_result):
            return cycle_results
        history.append(
            Message(
                id="history-task-code-repair-1",
                conversation_id=input_data.conversation_id,
                role="agent",
                sender_id=repair_result.agent_id,
                content=repair_result.content,
                artifacts=repair_result.artifacts,
            )
        )
        prior_artifacts.extend(
            artifact.model_dump(mode="json") for artifact in repair_result.artifacts
        )

        validation_tasks = [task for task in _child_tasks(plan) if task.agent_id == AGENT_REVIEW]
        for original_task in validation_tasks:
            task = original_task.model_copy(
                update={
                    "task_id": f"{original_task.task_id}-repair-1",
                    "depends_on": [],
                }
            )
            result = await self._run_harness_step(
                task=task,
                input_data=repair_input,
                history=history,
                prior_artifacts=prior_artifacts,
                report=report,
            )
            cycle_results.append(result)
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
            prior_artifacts.extend(
                artifact.model_dump(mode="json") for artifact in result.artifacts
            )
            if _is_agent_error_result(result):
                break
        return cycle_results

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
            run_id = new_id("run")
            started = time.perf_counter()
            task_input = input_data.model_copy(
                update={
                    "history": history,
                    "context": {
                        **input_data.context,
                        "agent_id": task.agent_id,
                        "task_id": task.task_id,
                        "run_id": run_id,
                        "instruction": task.instruction,
                        "user_request": input_data.user_message,
                        "prior_artifacts": prior_artifacts,
                    },
                    "user_message": _task_user_message(task, input_data.user_message),
                }
            )
            try:
                change_set_id = _change_set_id_from_artifacts(prior_artifacts)
                if (
                    self._change_set_service is not None
                    and change_set_id is not None
                    and task.agent_id == AGENT_REVIEW
                ):
                    await self._change_set_service.start_validation(
                        input_data.workspace_id,
                        change_set_id,
                        kind="review",
                    )
                    candidate = await self._change_set_service.get(
                        input_data.workspace_id,
                        change_set_id,
                    )
                    static_findings = self._static_inspector.inspect(
                        candidate,
                        self._change_set_service.staging_dir(change_set_id),
                    )
                    task_input = task_input.model_copy(
                        update={
                            "context": {
                                **task_input.context,
                                "static_findings": [
                                    finding.model_dump(mode="json") for finding in static_findings
                                ],
                            }
                        }
                    )
                if task.agent_id == AGENT_PREVIEW and self._change_set_service is not None:
                    result = await self._build_manual_preview(task_input, prior_artifacts)
                else:
                    result = await self.run(task_input)
                if task.agent_id == AGENT_CODE and self._change_set_service is not None:
                    result = await self._attach_change_set(result, task_input)
                elif task.agent_id == AGENT_REVIEW and self._change_set_service is not None:
                    result = await self._record_review_result(result, prior_artifacts, task_input)
            except AgentHubError as exc:
                change_set_id = _change_set_id_from_artifacts(prior_artifacts)
                if (
                    self._change_set_service is not None
                    and change_set_id is not None
                    and task.agent_id == AGENT_REVIEW
                ):
                    await self._change_set_service.record_validation_error(
                        input_data.workspace_id,
                        change_set_id,
                        kind="review",
                        error_code=exc.code,
                        error_message=str(exc),
                    )
                self._log_agent_run(
                    run_id=run_id,
                    task=task,
                    input_data=input_data,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    status="failed",
                    attempt=attempt,
                    error_category=_error_category_for_exception(exc),
                )
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
                    return self._build_agent_error_result(
                        task.agent_id,
                        exc,
                        run_id=run_id,
                        task_id=task.task_id,
                    )
                continue

            verification = _verify_agent_result(task.agent_id, result)
            self._log_agent_run(
                run_id=run_id,
                task=task,
                input_data=input_data,
                duration_ms=int((time.perf_counter() - started) * 1000),
                status="succeeded" if verification.ok else "validation_failed",
                attempt=attempt,
                error_category=None if verification.ok else "validation",
            )
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
                task.agent_id,
                AgentExecutionError("Agent failed."),
                run_id=run_id,
                task_id=task.task_id,
            )
        issues = report.steps[-1].verification.issues if report.steps[-1].verification else []
        return self._build_agent_error_result(
            task.agent_id,
            AgentExecutionError(
                "Harness contract validation failed: "
                + ("; ".join(issues) if issues else "required artifacts are missing.")
            ),
            run_id=run_id,
            task_id=task.task_id,
        )

    async def validate_existing_change_set(
        self,
        input_data: AgentRunInput,
        change_set_id: str,
    ) -> list[AgentRunResult]:
        """Run a fresh static inspection and Review for a pre-staged candidate."""
        if self._change_set_service is None:
            raise AgentExecutionError("Change set validation is not configured.")
        change_set = await self._change_set_service.get(
            input_data.workspace_id,
            change_set_id,
        )
        prior_artifacts = _validation_artifacts_for_change_set(change_set)
        history = list(input_data.history)
        report = ExecutionReport(plan_summary="Revalidate a reverted change set")
        acceptance_criteria = [
            {"id": check.criterion_id, "description": check.name}
            for check in change_set.preview_checks
        ] or [
            {
                "id": "criterion-primary-flow",
                "description": "The candidate implements the requested static Web change.",
            }
        ]
        validation_input = input_data.model_copy(
            update={
                "context": {
                    **input_data.context,
                    "acceptance_criteria": acceptance_criteria,
                    "change_set_id": change_set.id,
                }
            }
        )
        tasks = [
            AgentTask(
                task_id="task-review-reapply",
                agent_id=AGENT_REVIEW,
                instruction=("对重新应用的候选快照进行全量代码审查，不得复用旧结论。"),
            ),
        ]
        results: list[AgentRunResult] = []
        for task in tasks:
            result = await self._run_harness_step(
                task=task,
                input_data=validation_input,
                history=history,
                prior_artifacts=prior_artifacts,
                report=report,
            )
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
            prior_artifacts.extend(
                artifact.model_dump(mode="json") for artifact in result.artifacts
            )
            if _is_agent_error_result(result):
                break
        return results

    def _log_agent_run(
        self,
        *,
        run_id: str,
        task: AgentTask,
        input_data: AgentRunInput,
        duration_ms: int,
        status: str,
        attempt: int,
        error_category: str | None,
    ) -> None:
        logger.info(
            "agent_run %s",
            json.dumps(
                {
                    "run_id": run_id,
                    "change_set_id": _change_set_id_from_artifacts(
                        input_data.context.get("prior_artifacts", [])
                        if isinstance(input_data.context.get("prior_artifacts"), list)
                        else []
                    ),
                    "task_id": task.task_id,
                    "agent_id": task.agent_id,
                    "provider": self._settings.agent_provider if self._settings else None,
                    "model": self._settings.agent_model if self._settings else None,
                    "duration_ms": duration_ms,
                    "retry_count": attempt - 1,
                    "token_usage": None,
                    "status": status,
                    "error_category": error_category,
                },
                ensure_ascii=False,
            ),
        )

    async def _attach_change_set(
        self,
        result: AgentRunResult,
        input_data: AgentRunInput,
    ) -> AgentRunResult:
        if self._change_set_service is None:
            return result
        parent_change_set_id = input_data.context.get("parent_change_set_id")
        repair_count = input_data.context.get("repair_count", 0)
        change_set = await self._change_set_service.create_from_artifacts(
            conversation_id=input_data.conversation_id,
            workspace_id=input_data.workspace_id,
            artifacts=result.artifacts,
            source_message_id=_optional_string(input_data.context.get("source_message_id")),
            parent_change_set_id=_optional_string(parent_change_set_id),
            repair_count=repair_count if isinstance(repair_count, int) else 0,
            preview_checks=[],
        )
        artifact = Artifact(
            id=f"artifact-change-set-{change_set.id}",
            type="change_set",
            title="Candidate change set",
            data={
                "change_set_id": change_set.id,
                "workspace_id": change_set.workspace_id,
                "status": change_set.status,
                "file_count": len(change_set.files),
                "entry_path": change_set.entry_path,
                "repair_count": change_set.repair_count,
            },
        )
        backend_diffs = [
            Artifact(
                id=f"artifact-diff-{change_set.id}-{file_record.id}",
                type="diff",
                title=f"Candidate diff: {file_record.path}",
                data={
                    "filename": file_record.path,
                    "operation": file_record.operation,
                    "diff": file_record.diff,
                    "workspace_id": change_set.workspace_id,
                    "change_set_id": change_set.id,
                    "source": "backend-generated",
                },
            )
            for file_record in change_set.files
        ]
        existing_diff_paths = {
            item.data.get("filename") for item in result.artifacts if item.type == "diff"
        }
        backend_diffs = [
            item for item in backend_diffs if item.data.get("filename") not in existing_diff_paths
        ]
        return result.model_copy(
            update={"artifacts": [*result.artifacts, *backend_diffs, artifact]}
        )

    async def _record_review_result(
        self,
        result: AgentRunResult,
        prior_artifacts: list[dict[str, Any]],
        input_data: AgentRunInput,
    ) -> AgentRunResult:
        if self._change_set_service is None:
            return result
        change_set_id = _change_set_id_from_artifacts(prior_artifacts)
        if change_set_id is None:
            raise AgentExecutionError("Review validation requires a staged change set.")
        await self._change_set_service.assert_candidate_integrity(
            input_data.workspace_id,
            change_set_id,
        )
        review_artifact = next(
            (artifact for artifact in result.artifacts if artifact.type == "file"), None
        )
        if review_artifact is None:
            raise AgentExecutionError("Review Agent did not return a ReviewReport artifact.")
        try:
            report = ReviewReport.model_validate(review_artifact.data)
        except ValidationError as exc:
            raise AgentExecutionError("Review Agent returned an invalid ReviewReport.") from exc
        raw_criteria = input_data.context.get("acceptance_criteria", [])
        criterion_ids: set[str] = {
            str(item["id"])
            for item in raw_criteria
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        uncovered = sorted(criterion_ids.difference(report.covered_criteria))
        if uncovered:
            raise AgentHubError(
                "review_contract_failed",
                "Review Agent did not cover acceptance criteria: " + ", ".join(uncovered),
                status_code=422,
            )

        normalized_findings: list[ReviewFinding] = []
        downgraded_count = 0
        for finding in report.findings:
            if finding.severity != "blocker":
                normalized_findings.append(finding)
                continue
            has_supported_criterion = bool(
                finding.criterion_id
                and (
                    finding.criterion_id in criterion_ids
                    or finding.criterion_id == "criterion-static-safety"
                )
            )
            if has_supported_criterion and finding.path and finding.evidence:
                normalized_findings.append(finding)
                continue
            downgraded_count += 1
            normalized_findings.append(
                finding.model_copy(
                    update={
                        "severity": "high",
                        "message": (
                            finding.message
                            + "（缺少验收项、文件路径或具体代码证据，已降级为非阻塞警告。）"
                        ),
                    }
                )
            )

        change_set = await self._change_set_service.get(
            input_data.workspace_id,
            change_set_id,
        )
        static_findings = self._static_inspector.inspect(
            change_set,
            self._change_set_service.staging_dir(change_set_id),
        )
        merged_findings = [*normalized_findings, *static_findings]
        has_blocker = any(finding.severity == "blocker" for finding in merged_findings)
        if has_blocker:
            verdict: Literal["pass", "pass_with_warnings", "fail"] = "fail"
        elif merged_findings or report.verdict != "pass":
            verdict = "pass_with_warnings"
        else:
            verdict = "pass"
        report = report.model_copy(update={"verdict": verdict, "findings": merged_findings})

        content_prefixes: list[str] = []
        if downgraded_count:
            content_prefixes.append(
                f"{downgraded_count} 个缺少具体证据的 blocker 已降级为非阻塞警告。"
            )
        if static_findings:
            content_prefixes.append(
                f"后端静态安全检查发现 {len(static_findings)} 个确定性阻塞问题。"
            )
        if verdict in {"pass", "pass_with_warnings"}:
            content_prefixes.append("代码审查完成，候选 Change Set 已可合入。")

        updated = await self._change_set_service.set_review_report(
            input_data.workspace_id,
            change_set_id,
            report,
        )
        report_data = {
            **report.model_dump(mode="json"),
            "kind": "review_report",
            "workspace_id": input_data.workspace_id,
            "change_set_id": change_set_id,
            "change_set_status": updated.status,
        }
        result = result.model_copy(
            update={
                "content": (
                    "\n\n".join([*content_prefixes, result.content])
                    if content_prefixes
                    else result.content
                ),
                "artifacts": [
                    artifact.model_copy(update={"data": report_data})
                    if artifact.id == review_artifact.id
                    else artifact
                    for artifact in result.artifacts
                ],
                "next_actions": ["promote"] if updated.status == "ready" else [],
            }
        )
        return result

    async def _build_manual_preview(
        self,
        input_data: AgentRunInput,
        prior_artifacts: list[dict[str, Any]],
    ) -> AgentRunResult:
        if self._change_set_service is None:
            raise AgentExecutionError("Candidate preview is not configured.")
        change_set_id = _change_set_id_from_artifacts(prior_artifacts)
        if change_set_id is None:
            change_set_id = _optional_string(input_data.context.get("change_set_id"))
        candidate: ChangeSet | None = None
        if change_set_id is not None:
            candidate = await self._change_set_service.get(
                input_data.workspace_id,
                change_set_id,
            )
        else:
            candidates = await self._change_set_service.list(input_data.workspace_id)
            candidate = next(
                (
                    item
                    for item in sorted(candidates, key=lambda item: item.created_at, reverse=True)
                    if item.entry_path and item.status not in {"promoted", "rejected", "conflicted"}
                ),
                None,
            )
        if candidate is not None and candidate.entry_path:
            data: dict[str, object] = {
                "preview_status": "available",
                "scope": "candidate",
                "workspace_id": input_data.workspace_id,
                "change_set_id": candidate.id,
                "entry_path": candidate.entry_path,
            }
            content = "候选隔离预览已准备。该入口仅供人工查看，不执行浏览器自动验证。"
        else:
            entry_path = self._change_set_service.workspace_entry_path(input_data.workspace_id)
            if entry_path is None:
                raise AgentHubError(
                    "preview_not_available",
                    "当前候选和正式 Workspace 都没有可预览的 HTML 入口。",
                    status_code=404,
                )
            data = {
                "preview_status": "available",
                "scope": "workspace",
                "workspace_id": input_data.workspace_id,
                "entry_path": entry_path,
            }
            content = "正式 Workspace 预览入口已准备。该入口仅供人工查看。"
        return AgentRunResult(
            agent_id=AGENT_PREVIEW,
            content=content,
            artifacts=[
                Artifact(
                    id=f"artifact-preview-{candidate.id if candidate else input_data.workspace_id}",
                    type="preview",
                    title="Manual preview",
                    data=data,
                )
            ],
            next_actions=[],
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
            if artifact.type == "change_set":
                yield ("change_set_created", dict(artifact.data))
            elif artifact.type == "file" and artifact.data.get("kind") == "review_report":
                yield ("validation_completed", dict(artifact.data))
                if artifact.data.get("change_set_status") == "ready":
                    yield ("change_set_ready", dict(artifact.data))
        if _is_agent_error_result(result):
            error = result.error or _agent_run_error(result)
            yield (
                "agent_failed",
                {
                    "result": result.model_dump(mode="json"),
                    "error": error.model_dump(mode="json"),
                },
            )
            return
        yield ("agent_done", {"result": result.model_dump(mode="json")})

    def _build_agent_error_result(
        self,
        agent_id: str,
        exc: Exception,
        *,
        run_id: str | None = None,
        task_id: str | None = None,
    ) -> AgentRunResult:
        message = _agent_error_message(agent_id, exc)
        category = _error_category_for_exception(exc)
        code = (
            exc.code
            if isinstance(exc, AgentHubError) and exc.code != "agent_execution_failed"
            else f"agent_{category}_failed"
        )
        return AgentRunResult(
            agent_id=agent_id,
            content=message,
            artifacts=[],
            next_actions=[],
            error=AgentRunError(
                code=code,
                category=category,
                message=message,
                retryable=category == "transport",
                run_id=run_id or new_id("run"),
                task_id=task_id,
                agent_id=agent_id,
            ),
        )


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


def _ensure_required_harness_tasks(
    decision: OrchestratorDecision,
    *,
    include_preview: bool = False,
) -> OrchestratorDecision:
    if decision.mode != "plan" or decision.plan is None:
        return decision

    next_plan = _ensure_plan_has_required_harness_tasks(
        decision.plan,
        include_preview=include_preview,
    )
    if next_plan == decision.plan:
        return decision
    return decision.model_copy(
        update={
            "plan": next_plan,
            "content": _build_guarded_harness_content(next_plan),
        }
    )


def _direct_code_change_set_plan(user_message: str) -> OrchestratorPlan:
    """Wrap a direct Code Agent request in the same guarded delivery pipeline."""
    del user_message
    return OrchestratorPlan(
        summary="Direct Code Agent request with static safety and Review gates",
        tasks=[
            AgentTask(
                task_id="task-code",
                agent_id=AGENT_CODE,
                instruction="按用户原始需求生成完整候选文件，不生成浏览器检查或预览结论。",
            ),
            AgentTask(
                task_id="task-review",
                agent_id=AGENT_REVIEW,
                instruction="审查候选文件的功能完整性、代码风险和验收覆盖。",
                depends_on=["task-code"],
            ),
        ],
        acceptance_criteria=[
            AcceptanceCriterion(
                id="criterion-primary-flow",
                description="The candidate implements the user's requested static Web change.",
            )
        ],
    )


def _validation_artifacts_for_change_set(change_set: ChangeSet) -> list[dict[str, Any]]:
    artifacts: list[Artifact] = []
    for file_record in change_set.files:
        if file_record.operation == "upsert":
            artifacts.append(
                Artifact(
                    id=f"artifact-code-{change_set.id}-{file_record.id}",
                    type="code",
                    title=file_record.path,
                    data={
                        "filename": file_record.path,
                        "content": file_record.after_content or "",
                    },
                )
            )
        artifacts.append(
            Artifact(
                id=f"artifact-diff-{change_set.id}-{file_record.id}",
                type="diff",
                title=f"Candidate diff: {file_record.path}",
                data={
                    "filename": file_record.path,
                    "operation": file_record.operation,
                    "diff": file_record.diff,
                    "change_set_id": change_set.id,
                    "workspace_id": change_set.workspace_id,
                    "source": "backend-generated",
                },
            )
        )
    artifacts.append(
        Artifact(
            id=f"artifact-change-set-{change_set.id}",
            type="change_set",
            title="Candidate change set",
            data={
                "change_set_id": change_set.id,
                "workspace_id": change_set.workspace_id,
                "status": change_set.status,
                "file_count": len(change_set.files),
                "entry_path": change_set.entry_path,
            },
        )
    )
    return [artifact.model_dump(mode="json") for artifact in artifacts]


def _ensure_plan_has_required_harness_tasks(
    plan: OrchestratorPlan,
    *,
    include_preview: bool = False,
) -> OrchestratorPlan:
    tasks = list(plan.tasks)
    if not any(task.agent_id == AGENT_CODE for task in tasks):
        return plan

    explicitly_requested_previews = (
        [task for task in tasks if task.agent_id == AGENT_PREVIEW] if include_preview else []
    )
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

    preview_tasks = [
        task.model_copy(update={"depends_on": task.depends_on or [review_task.task_id]})
        for task in explicitly_requested_previews
    ]

    return OrchestratorPlan(
        summary=plan.summary or "AgentHub guarded harness plan",
        tasks=[*base_tasks, review_task, *preview_tasks],
        acceptance_criteria=plan.acceptance_criteria,
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
    if isinstance(cause, RealAgentSchemaError | ValidationError) or isinstance(
        exc, RealAgentSchemaError
    ):
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


def _change_set_id_from_artifacts(artifacts: list[dict[str, Any]]) -> str | None:
    for artifact in reversed(artifacts):
        if artifact.get("type") != "change_set":
            continue
        data = artifact.get("data")
        if isinstance(data, dict):
            change_set_id = data.get("change_set_id")
            if isinstance(change_set_id, str) and change_set_id:
                return change_set_id
    return None


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _is_agent_error_result(result: AgentRunResult) -> bool:
    return result.error is not None or (
        result.content.startswith("Agent ") and " failed:" in result.content
    )


def _agent_run_error(result: AgentRunResult) -> AgentRunError:
    content = result.content.lower()
    category: AgentErrorCategory = "validation"
    code = "agent_validation_failed"
    retryable = False
    if "api_key" in content or "configuration" in content or ".env" in content:
        category = "configuration"
        code = "agent_configuration_failed"
    elif "network" in content or "timeout" in content or "429" in content or "5xx" in content:
        category = "transport"
        code = "agent_transport_failed"
        retryable = True
    elif "schema" in content or "结构" in content or "parse" in content:
        category = "schema"
        code = "agent_schema_failed"
    elif "workspace" in content or "change set" in content or "preview" in content:
        category = "workspace"
        code = "agent_workspace_failed"
    return AgentRunError(
        code=code,
        category=category,
        message=result.content,
        retryable=retryable,
        run_id=new_id("run"),
        agent_id=result.agent_id,
    )


def _error_category_for_exception(exc: Exception) -> AgentErrorCategory:
    cause = exc.__cause__
    if isinstance(exc, RealAgentConfigurationError) or isinstance(
        cause, RealAgentConfigurationError
    ):
        return "configuration"
    if isinstance(exc, RealAgentTransportError) or isinstance(cause, RealAgentTransportError):
        return "transport"
    if isinstance(exc, RealAgentSchemaError | ValidationError) or isinstance(
        cause, RealAgentSchemaError | ValidationError
    ):
        return "schema"
    if isinstance(exc, BadRequestError | NotFoundError):
        return "workspace"
    return "validation"


def _verify_agent_result(agent_id: str, result: AgentRunResult) -> VerificationResult:
    artifact_types = {artifact.type for artifact in result.artifacts}
    if agent_id == AGENT_CODE:
        issues = []
        if "code" not in artifact_types:
            issues.append("Code Agent 缺少 code artifact")
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
        else:
            try:
                ReviewReport.model_validate(review_artifact.data)
            except ValidationError:
                issues.append("Review artifact 不符合 ReviewReport 契约")
        return VerificationResult(
            ok=not issues,
            message="Review Agent 校验通过" if not issues else "Review Agent 校验失败",
            issues=issues,
        )
    if agent_id == AGENT_PREVIEW:
        issues = []
        preview_artifact = next(
            (artifact for artifact in result.artifacts if artifact.type == "preview"), None
        )
        if preview_artifact is None:
            issues.append("Preview Agent 缺少 preview artifact")
        elif preview_artifact.data.get("preview_status") != "available":
            issues.append("Preview artifact 缺少合法 preview_status")
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
