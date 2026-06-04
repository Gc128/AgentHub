"""
tests/test_orchestrator.py

AgentTask、OrchestratorPlan、route_task 的单元测试。

覆盖场景：
- AgentTask 合法构造 / 非法 agent_id / 空白 instruction
- OrchestratorPlan 合法构造 / 空 tasks / 悬空 depends_on 引用
- route_task 关键词路由（code / review / preview / 默认）
- route_task 边界输入（空字符串、纯空白、混合关键词优先级）
"""

from __future__ import annotations

import asyncio
import uuid as _uuid

import pytest
from pydantic import ValidationError

from agenthub.agents.base import (
    AgentRunInput,
    AgentRunResult,
    Artifact,
    Message,
)
from agenthub.orchestrator.executor import (
    ExecutionError,
    ExecutionReport,
    execute_plan,
)
from agenthub.orchestrator.planner import (
    AGENT_CODE,
    AGENT_ORCHESTRATOR,
    AGENT_PREVIEW,
    AGENT_REVIEW,
    AgentTask,
    OrchestratorPlan,
    route_task,
)

# ---------------------------------------------------------------------------
# 辅助工厂
# ---------------------------------------------------------------------------


def make_task(
    agent_id: str = "code-agent",
    instruction: str = "do something",
    task_id: str | None = None,
    depends_on: list[str] | None = None,
) -> AgentTask:
    kwargs: dict = {"agent_id": agent_id, "instruction": instruction}
    if task_id is not None:
        kwargs["task_id"] = task_id
    if depends_on is not None:
        kwargs["depends_on"] = depends_on
    return AgentTask(**kwargs)


# ---------------------------------------------------------------------------
# AgentTask 模型校验
# ---------------------------------------------------------------------------


class TestAgentTask:
    def test_default_task_id_is_generated(self) -> None:
        task = make_task()
        assert task.task_id  # 非空
        assert len(task.task_id) == 36  # UUID4 格式

    def test_explicit_task_id_preserved(self) -> None:
        task = make_task(task_id="my-task-001")
        assert task.task_id == "my-task-001"

    def test_valid_agent_ids(self) -> None:
        for agent_id in ("code-agent", "review-agent", "preview-agent", "orchestrator"):
            task = make_task(agent_id=agent_id)
            assert task.agent_id == agent_id

    def test_invalid_agent_id_raises(self) -> None:
        with pytest.raises(ValidationError, match="agent_id"):
            make_task(agent_id="unknown_agent")

    def test_blank_agent_id_raises(self) -> None:
        with pytest.raises(ValidationError):
            make_task(agent_id="")

    def test_whitespace_agent_id_raises(self) -> None:
        with pytest.raises(ValidationError):
            make_task(agent_id="   ")

    def test_empty_instruction_raises(self) -> None:
        with pytest.raises(ValidationError, match="string_too_short|at least 1 character"):
            make_task(instruction="")

    def test_blank_instruction_raises(self) -> None:
        with pytest.raises(ValidationError, match="blank"):
            make_task(instruction="   ")

    def test_depends_on_defaults_to_empty_list(self) -> None:
        task = make_task()
        assert task.depends_on == []

    def test_depends_on_populated(self) -> None:
        task = make_task(depends_on=["task-a", "task-b"])
        assert task.depends_on == ["task-a", "task-b"]

    def test_task_is_immutable(self) -> None:
        task = make_task()
        with pytest.raises(ValidationError):
            task.agent_id = "review-agent"  # type: ignore[misc]

    def test_two_tasks_with_same_content_have_different_task_ids(self) -> None:
        t1 = make_task()
        t2 = make_task()
        assert t1.task_id != t2.task_id


# ---------------------------------------------------------------------------
# OrchestratorPlan 模型校验
# ---------------------------------------------------------------------------


class TestOrchestratorPlan:
    def test_valid_plan_single_task(self) -> None:
        task = make_task(task_id="t1")
        plan = OrchestratorPlan(summary="simple plan", tasks=[task])
        assert len(plan.tasks) == 1
        assert plan.summary == "simple plan"

    def test_valid_plan_empty_summary(self) -> None:
        plan = OrchestratorPlan(tasks=[make_task()])
        assert plan.summary == ""

    def test_empty_tasks_list_raises(self) -> None:
        with pytest.raises(ValidationError, match="too_short|at least 1 item"):
            OrchestratorPlan(tasks=[])

    def test_valid_dependency_chain(self) -> None:
        t1 = make_task(task_id="t1")
        t2 = make_task(task_id="t2", agent_id="review-agent", depends_on=["t1"])
        plan = OrchestratorPlan(tasks=[t1, t2])
        assert plan.tasks[1].depends_on == ["t1"]

    def test_dangling_depends_on_raises(self) -> None:
        t1 = make_task(task_id="t1", depends_on=["nonexistent"])
        with pytest.raises(ValidationError, match="unknown task_id"):
            OrchestratorPlan(tasks=[t1])

    def test_self_dependency_is_currently_allowed_at_model_level(self) -> None:
        """模型层暂不检测自依赖（留给 Executor 的拓扑排序层）。"""
        t1 = make_task(task_id="t1", depends_on=["t1"])
        plan = OrchestratorPlan(tasks=[t1])  # 不应抛出
        assert plan.tasks[0].depends_on == ["t1"]

    def test_agent_ids_property_deduplicates(self) -> None:
        t1 = make_task(task_id="t1", agent_id="code-agent")
        t2 = make_task(task_id="t2", agent_id="review-agent")
        t3 = make_task(task_id="t3", agent_id="code-agent")  # 重复
        plan = OrchestratorPlan(tasks=[t1, t2, t3])
        assert plan.agent_ids == ["code-agent", "review-agent"]

    def test_agent_ids_property_preserves_order(self) -> None:
        t1 = make_task(task_id="t1", agent_id="preview-agent")
        t2 = make_task(task_id="t2", agent_id="code-agent")
        plan = OrchestratorPlan(tasks=[t1, t2])
        assert plan.agent_ids == ["preview-agent", "code-agent"]

    def test_multiple_tasks_multi_agent(self) -> None:
        tasks = [
            make_task(task_id="t1", agent_id="code-agent", instruction="write component"),
            make_task(
                task_id="t2",
                agent_id="review-agent",
                depends_on=["t1"],
                instruction="review it",
            ),
            make_task(
                task_id="t3",
                agent_id="preview-agent",
                depends_on=["t2"],
                instruction="preview",
            ),
        ]
        plan = OrchestratorPlan(summary="full pipeline", tasks=tasks)
        assert len(plan.tasks) == 3
        assert plan.agent_ids == ["code-agent", "review-agent", "preview-agent"]


# ---------------------------------------------------------------------------
# route_task 路由规则
# ---------------------------------------------------------------------------


class TestRouteTask:
    # --- code agent ---

    def test_route_write_chinese(self) -> None:
        assert route_task("帮我写一个登录页面") == AGENT_CODE

    def test_route_implement_chinese(self) -> None:
        assert route_task("实现一个用户注册功能") == AGENT_CODE

    def test_route_generate_chinese(self) -> None:
        assert route_task("生成一个 React 组件") == AGENT_CODE

    def test_route_page_chinese(self) -> None:
        assert route_task("做一个首页页面") == AGENT_CODE

    def test_route_component_chinese(self) -> None:
        assert route_task("开发一个侧边栏组件") == AGENT_CODE

    def test_route_implement_english(self) -> None:
        assert route_task("implement a login form") == AGENT_CODE

    def test_route_create_english(self) -> None:
        assert route_task("create a new API endpoint") == AGENT_CODE

    def test_route_build_english(self) -> None:
        assert route_task("build a dashboard component") == AGENT_CODE

    def test_route_generate_english(self) -> None:
        assert route_task("generate boilerplate code for me") == AGENT_CODE

    # --- review agent ---

    def test_route_check_chinese(self) -> None:
        assert route_task("检查一下这段代码有没有问题") == AGENT_REVIEW

    def test_route_optimize_chinese(self) -> None:
        assert route_task("优化这个函数的性能") == AGENT_REVIEW

    def test_route_bug_chinese(self) -> None:
        assert route_task("这里有个 bug 帮我看看") == AGENT_REVIEW

    def test_route_review_english(self) -> None:
        assert route_task("please review my pull request") == AGENT_REVIEW

    def test_route_bug_english(self) -> None:
        assert route_task("there is a bug in my code") == AGENT_REVIEW

    def test_route_fix_english(self) -> None:
        assert route_task("fix the error in the function") == AGENT_REVIEW

    def test_route_optimize_english(self) -> None:
        assert route_task("optimize this algorithm") == AGENT_REVIEW

    def test_route_debug_english(self) -> None:
        assert route_task("debug this module") == AGENT_REVIEW

    # --- preview agent ---

    def test_route_preview_chinese(self) -> None:
        assert route_task("预览一下当前页面的效果") == AGENT_PREVIEW

    def test_route_effect_chinese(self) -> None:
        assert route_task("看看现在的效果怎么样") == AGENT_PREVIEW

    def test_route_show_chinese(self) -> None:
        assert route_task("展示一下目前的界面") == AGENT_PREVIEW

    def test_route_preview_english(self) -> None:
        assert route_task("show me a preview of the page") == AGENT_PREVIEW

    def test_route_display_english(self) -> None:
        assert route_task("display the current view") == AGENT_PREVIEW

    def test_route_render_english(self) -> None:
        assert route_task("render the component") == AGENT_PREVIEW

    # --- orchestrator fallback ---

    def test_route_empty_string(self) -> None:
        assert route_task("") == AGENT_ORCHESTRATOR

    def test_route_whitespace_only(self) -> None:
        assert route_task("   \n  ") == AGENT_ORCHESTRATOR

    def test_route_greeting(self) -> None:
        assert route_task("你好") == AGENT_ORCHESTRATOR

    def test_route_general_question(self) -> None:
        assert route_task("帮我规划一下整个项目的架构") == AGENT_ORCHESTRATOR

    def test_route_unrelated_english(self) -> None:
        assert route_task("hello, how are you?") == AGENT_ORCHESTRATOR

    # --- 优先级（code 先于 review / preview）---

    def test_route_review_wins_over_code_when_both_match(self) -> None:
        # 新顺序 preview > review > code；"review" 词先命中 review 规则
        assert route_task("写一段代码然后帮我 review 一下") == AGENT_REVIEW

    def test_route_preview_wins_over_code_when_both_match(self) -> None:
        # "预览" 命中 preview 规则，排在 code 之前
        assert route_task("生成组件并预览效果") == AGENT_PREVIEW

    def test_route_preview_wins_over_review_when_both_match(self) -> None:
        # 新顺序 preview > review；"预览" 先命中 preview
        assert route_task("review 完之后预览一下效果") == AGENT_PREVIEW

    # --- 大小写不敏感 ---

    def test_route_case_insensitive_review(self) -> None:
        assert route_task("REVIEW this code") == AGENT_REVIEW

    def test_route_case_insensitive_preview(self) -> None:
        assert route_task("PREVIEW the page") == AGENT_PREVIEW

    def test_route_case_insensitive_implement(self) -> None:
        assert route_task("IMPLEMENT a feature") == AGENT_CODE


# ---------------------------------------------------------------------------
# Mock AgentAdapter 工厂
# ---------------------------------------------------------------------------


def _artifact(title: str = "out", atype: str = "code") -> Artifact:
    return Artifact(id=str(_uuid.uuid4()), type=atype, title=title)  # type: ignore[arg-type]


def _task(
    agent_id: str = "code-agent",
    instruction: str = "do work",
    task_id: str | None = None,
    depends_on: list[str] | None = None,
) -> AgentTask:
    kwargs: dict = {"agent_id": agent_id, "instruction": instruction}
    if task_id:
        kwargs["task_id"] = task_id
    if depends_on is not None:
        kwargs["depends_on"] = depends_on
    return AgentTask(**kwargs)


class SuccessAgent:
    """每次调用都成功，返回可配置的 Artifact 列表。"""

    id = "mock-success"
    name = "Mock Success Agent"
    capabilities: list[str] = []

    def __init__(self, artifacts: list[Artifact] | None = None, content: str = "done") -> None:
        self._artifacts = artifacts or []
        self._content = content
        self.calls: list[AgentRunInput] = []

    async def run(self, input: AgentRunInput) -> AgentRunResult:  # noqa: A002
        self.calls.append(input)
        return AgentRunResult(
            agent_id=self.id,
            content=self._content,
            artifacts=self._artifacts,
        )


class FailingAgent:
    """每次调用都抛出异常。"""

    id = "mock-fail"
    name = "Mock Failing Agent"
    capabilities: list[str] = []

    def __init__(self, exc: Exception | None = None) -> None:
        self._exc = exc or RuntimeError("agent exploded")

    async def run(self, input: AgentRunInput) -> AgentRunResult:  # noqa: A002
        raise self._exc


class SlowAgent:
    """调用会挂起超过 timeout。"""

    id = "mock-slow"
    name = "Mock Slow Agent"
    capabilities: list[str] = []

    def __init__(self, delay: float = 10.0) -> None:
        self._delay = delay

    async def run(self, input: AgentRunInput) -> AgentRunResult:  # noqa: A002
        await asyncio.sleep(self._delay)
        return AgentRunResult(agent_id=self.id, content="late")


class RecordingAgent:
    """记录每次调用的 context，供断言检查前置产物传递。"""

    id = "mock-recording"
    name = "Mock Recording Agent"
    capabilities: list[str] = []

    def __init__(self) -> None:
        self.received_contexts: list[dict] = []

    async def run(self, input: AgentRunInput) -> AgentRunResult:  # noqa: A002
        self.received_contexts.append(dict(input.context))
        return AgentRunResult(agent_id=self.id, content="recorded")


class PartialFailAgent:
    """交替成功/失败：call 0 成功，call 1 失败，call 2 成功……"""

    id = "mock-partial"
    name = "Mock Partial Agent"
    capabilities: list[str] = []

    def __init__(self, artifacts: list[Artifact] | None = None) -> None:
        self._artifacts = artifacts or []
        self._call_count = 0

    async def run(self, input: AgentRunInput) -> AgentRunResult:  # noqa: A002
        n = self._call_count
        self._call_count += 1
        if n % 2 == 1:  # 奇数次调用失败
            raise ValueError(f"simulated failure on call {n}")
        return AgentRunResult(agent_id=self.id, content="ok", artifacts=self._artifacts)


def _plan(*tasks: AgentTask, summary: str = "") -> OrchestratorPlan:
    return OrchestratorPlan(summary=summary, tasks=list(tasks))


# ---------------------------------------------------------------------------
# 基础执行
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_single_task_returns_artifacts() -> None:
    art = _artifact("my-code")
    agent = SuccessAgent(artifacts=[art])
    plan = _plan(_task())
    result = await execute_plan(plan, "conv-1", "ws-1", agent)
    assert len(result) == 1
    assert result[0].title == "my-code"


@pytest.mark.asyncio
async def test_execute_multiple_tasks_collects_all_artifacts() -> None:
    arts = [_artifact(f"out-{i}") for i in range(3)]
    # Each call returns one artifact; 3 tasks → 3 artifacts total
    call_idx = 0

    class CyclingAgent:
        id = "cycling"
        name = "Cycling"
        capabilities: list[str] = []

        async def run(self, input: AgentRunInput) -> AgentRunResult:  # noqa: A002
            nonlocal call_idx
            art = arts[call_idx % len(arts)]
            call_idx += 1
            return AgentRunResult(agent_id=self.id, content="ok", artifacts=[art])

    plan = _plan(
        _task("code-agent"),
        _task("review-agent", "check it"),
        _task("preview-agent", "show it"),
    )
    result = await execute_plan(plan, "c", "w", CyclingAgent())
    assert len(result) == 3


@pytest.mark.asyncio
async def test_execute_empty_artifacts_still_succeeds() -> None:
    agent = SuccessAgent(artifacts=[])
    plan = _plan(_task())
    result = await execute_plan(plan, "c", "w", agent)
    assert result == []


@pytest.mark.asyncio
async def test_agent_run_receives_correct_conversation_and_workspace() -> None:
    agent = SuccessAgent()
    plan = _plan(_task(instruction="do x"))
    await execute_plan(plan, "conv-42", "ws-99", agent)
    assert agent.calls[0].conversation_id == "conv-42"
    assert agent.calls[0].workspace_id == "ws-99"


@pytest.mark.asyncio
async def test_agent_run_receives_instruction_as_user_message() -> None:
    agent = SuccessAgent()
    plan = _plan(_task(instruction="write login component"))
    await execute_plan(plan, "c", "w", agent)
    assert agent.calls[0].user_message == "write login component"


@pytest.mark.asyncio
async def test_execute_plan_passes_history_to_agent() -> None:
    agent = SuccessAgent()
    msg = Message(id="m1", conversation_id="c", role="user", sender_id="user", content="hi")
    plan = _plan(_task())
    await execute_plan(plan, "c", "w", agent, history=[msg])
    assert agent.calls[0].history[0].id == "m1"


@pytest.mark.asyncio
async def test_execute_plan_passes_context_to_agent() -> None:
    agent = SuccessAgent()
    plan = _plan(_task())
    await execute_plan(plan, "c", "w", agent, context={"key": "value"})
    assert agent.calls[0].context["key"] == "value"


# ---------------------------------------------------------------------------
# 错误处理 — fail_fast=False（默认）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_failing_agent_does_not_raise_by_default() -> None:
    agent = FailingAgent()
    plan = _plan(_task())
    result = await execute_plan(plan, "c", "w", agent)
    assert result == []  # 失败任务不产出 artifact，但不抛异常


@pytest.mark.asyncio
async def test_partial_failure_continues_remaining_tasks() -> None:
    art = _artifact("success-art")
    agent = PartialFailAgent(artifacts=[art])
    # 3 tasks: call 0 success, call 1 fail, call 2 success
    plan = _plan(_task(), _task("review-agent", "check"), _task("preview-agent", "show"))
    result = await execute_plan(plan, "c", "w", agent)
    # calls 0 and 2 succeed, each returning `art`
    assert len(result) == 2


@pytest.mark.asyncio
async def test_timeout_task_treated_as_failure() -> None:
    agent = SlowAgent(delay=10.0)
    plan = _plan(_task())
    result = await execute_plan(plan, "c", "w", agent, task_timeout=0.05)
    assert result == []


@pytest.mark.asyncio
async def test_subsequent_tasks_run_after_timeout() -> None:
    """超时任务后的正常任务仍应执行（fail_fast=False）。"""
    art = _artifact("after-timeout")

    call_n = 0

    class MixedAgent:
        id = "mixed"
        name = "mixed"
        capabilities: list[str] = []

        async def run(self, input: AgentRunInput) -> AgentRunResult:  # noqa: A002
            nonlocal call_n
            n = call_n
            call_n += 1
            if n == 0:
                await asyncio.sleep(10.0)  # will timeout
            return AgentRunResult(agent_id=self.id, content="ok", artifacts=[art])

    plan = _plan(_task(), _task("review-agent", "check"))
    result = await execute_plan(plan, "c", "w", MixedAgent(), task_timeout=0.05)
    assert len(result) == 1
    assert result[0].title == "after-timeout"


# ---------------------------------------------------------------------------
# 错误处理 — fail_fast=True
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fail_fast_raises_execution_error() -> None:
    agent = FailingAgent()
    plan = _plan(_task())
    with pytest.raises(ExecutionError):
        await execute_plan(plan, "c", "w", agent, fail_fast=True)


@pytest.mark.asyncio
async def test_fail_fast_error_contains_report() -> None:
    agent = FailingAgent(RuntimeError("boom"))
    plan = _plan(_task(task_id="t1"))
    try:
        await execute_plan(plan, "c", "w", agent, fail_fast=True)
        pytest.fail("Expected ExecutionError")
    except ExecutionError as exc:
        assert isinstance(exc.report, ExecutionReport)
        assert len(exc.report.failed_tasks) == 1
        assert "t1" in exc.report.failed_tasks[0].task_id


@pytest.mark.asyncio
async def test_fail_fast_stops_after_first_failure() -> None:
    call_count = 0

    class CountingAgent:
        id = "counting"
        name = "counting"
        capabilities: list[str] = []

        async def run(self, input: AgentRunInput) -> AgentRunResult:  # noqa: A002
            nonlocal call_count
            call_count += 1
            raise RuntimeError("always fail")

    plan = _plan(_task(), _task("review-agent", "check"), _task("preview-agent", "show"))
    with pytest.raises(ExecutionError):
        await execute_plan(plan, "c", "w", CountingAgent(), fail_fast=True)
    assert call_count == 1  # 只调用了一次就中断了


@pytest.mark.asyncio
async def test_execution_error_is_runtime_error_subclass() -> None:
    agent = FailingAgent()
    plan = _plan(_task())
    with pytest.raises(RuntimeError):
        await execute_plan(plan, "c", "w", agent, fail_fast=True)


# ---------------------------------------------------------------------------
# 上下文传递（prior_artifacts）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prior_artifacts_passed_to_subsequent_tasks() -> None:
    """第一个任务的产物应出现在第二个任务的 context['prior_artifacts'] 中。"""
    art = _artifact("first-output")

    class FirstAgent:
        id = "first"
        name = "first"
        capabilities: list[str] = []

        async def run(self, input: AgentRunInput) -> AgentRunResult:  # noqa: A002
            return AgentRunResult(agent_id=self.id, content="done", artifacts=[art])

    recorder = RecordingAgent()

    class DualAgent:
        id = "dual"
        name = "dual"
        capabilities: list[str] = []
        _first_call = True

        async def run(self, input: AgentRunInput) -> AgentRunResult:  # noqa: A002
            if DualAgent._first_call:
                DualAgent._first_call = False
                return AgentRunResult(agent_id=self.id, content="done", artifacts=[art])
            recorder.received_contexts.append(dict(input.context))
            return AgentRunResult(agent_id=self.id, content="recorded")

    plan = _plan(_task(task_id="t1"), _task("review-agent", "check", task_id="t2"))
    await execute_plan(plan, "c", "w", DualAgent())

    assert len(recorder.received_contexts) == 1
    prior = recorder.received_contexts[0].get("prior_artifacts", [])
    assert len(prior) == 1
    assert prior[0]["title"] == "first-output"


@pytest.mark.asyncio
async def test_history_grows_with_each_successful_task() -> None:
    """每个成功任务的输出应追加到后续任务的 history 中。"""
    received_histories: list[list[Message]] = []

    class HistoryCapture:
        id = "capture"
        name = "capture"
        capabilities: list[str] = []
        _n = 0

        async def run(self, input: AgentRunInput) -> AgentRunResult:  # noqa: A002
            received_histories.append(list(input.history))
            HistoryCapture._n += 1
            return AgentRunResult(agent_id=self.id, content=f"reply {HistoryCapture._n}")

    plan = _plan(_task(), _task("review-agent", "check"), _task("preview-agent", "show"))
    await execute_plan(plan, "c", "w", HistoryCapture())

    # task 0 sees no agent history (only what was passed in)
    # task 1 sees 1 agent message, task 2 sees 2 agent messages
    assert len(received_histories[0]) == 0
    assert len(received_histories[1]) == 1
    assert len(received_histories[2]) == 2
    assert received_histories[1][0].role == "agent"


# ---------------------------------------------------------------------------
# ExecutionReport 结构
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execution_report_via_fail_fast_contains_all_data() -> None:
    arts = [_artifact("a1"), _artifact("a2")]
    agent = SuccessAgent(artifacts=arts)

    # 不走 fail_fast；通过捕获 ExecutionError.report 验证结构
    # 此处直接调用内部函数验证 report 结构（白盒测试）
    from agenthub.orchestrator.executor import _execute_task

    outcome = await _execute_task(
        task=AgentTask(task_id="tx", agent_id="code-agent", instruction="do it"),
        conversation_id="c",
        workspace_id="w",
        agent_service=agent,
        history=[],
        context={},
        task_timeout=5.0,
    )
    assert outcome.success is True
    assert outcome.task_id == "tx"
    assert len(outcome.artifacts) == 2


@pytest.mark.asyncio
async def test_task_outcome_on_failure_has_error_message() -> None:
    from agenthub.orchestrator.executor import _execute_task

    agent = FailingAgent(ValueError("bad input"))
    outcome = await _execute_task(
        task=AgentTask(task_id="ty", agent_id="code-agent", instruction="fail"),
        conversation_id="c",
        workspace_id="w",
        agent_service=agent,
        history=[],
        context={},
        task_timeout=5.0,
    )
    assert outcome.success is False
    assert "ValueError" in outcome.error
    assert "bad input" in outcome.error


@pytest.mark.asyncio
async def test_task_outcome_on_timeout_has_error_message() -> None:
    from agenthub.orchestrator.executor import _execute_task

    agent = SlowAgent(delay=10.0)
    outcome = await _execute_task(
        task=AgentTask(task_id="tz", agent_id="code-agent", instruction="slow"),
        conversation_id="c",
        workspace_id="w",
        agent_service=agent,
        history=[],
        context={},
        task_timeout=0.05,
    )
    assert outcome.success is False
    assert "timed out" in outcome.error.lower()
