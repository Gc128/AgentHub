import asyncio
import json
import re
from collections.abc import AsyncIterator
from typing import Any, Literal

from pydantic import ValidationError

from agenthub.agents.real_agent import (
    RealAgentConfigurationError,
    RealAgentSchemaError,
    RealAgentTransportError,
    RealAgentUnavailableError,
)
from agenthub.agents.registry import AgentRegistry
from agenthub.core.errors import AgentExecutionError, NotFoundError
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
from agenthub.schemas.agent import Agent, AgentRunInput, AgentRunResult
from agenthub.schemas.message import Message

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
            or AGENT_ORCHESTRATOR
        )
        if agent_id == AGENT_ORCHESTRATOR:
            try:
                decision = await self._decide_orchestrator(input_data)
            except AgentExecutionError as exc:
                return self._build_agent_error_result(AGENT_ORCHESTRATOR, exc)
            return self._result_from_orchestrator_decision(decision)
        try:
            agent = self._registry.get(agent_id)
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
        agent_id = route_agent(input_data.user_message)
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
        agent_id = route_agent(input_data.user_message)
        if agent_id is None:
            async for event in self._stream_orchestrator_entry(input_data):
                yield event
            return
        if agent_id == AGENT_ORCHESTRATOR:
            async for event in self._stream_orchestrator_entry(input_data):
                yield event
            return

        yield (
            "harness_step",
            {
                "status": "started",
                "agent_id": agent_id,
                "message": f"{agent_id} 正在生成回复",
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
        "我已理解这是开发任务，将按安全兜底计划继续执行。",
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
