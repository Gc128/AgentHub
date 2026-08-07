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

import pytest
from pydantic import ValidationError

from agenthub.orchestrator.planner import (
    AGENT_CODE,
    AGENT_ORCHESTRATOR,
    AGENT_PREVIEW,
    AGENT_REVIEW,
    AgentTask,
    OrchestratorPlan,
    create_plan,
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


class TestCreatePlan:
    def test_orchestrator_mention_creates_full_demo_plan(self) -> None:
        plan = create_plan("@Orchestrator 帮我做一个 Todo 页面")

        assert plan.agent_ids == [AGENT_CODE, AGENT_REVIEW]
        assert all(
            "@Orchestrator 帮我做一个 Todo 页面" not in task.instruction for task in plan.tasks
        )
        assert "context.user_request" not in plan.tasks[0].instruction
        assert "开发需求" in plan.tasks[0].instruction
        assert "审查前序代码" in plan.tasks[1].instruction

    def test_code_intent_creates_harness_tasks(self) -> None:
        plan = create_plan("写一段代码然后帮我 review 一下")

        assert plan.agent_ids == [AGENT_CODE, AGENT_REVIEW]
        assert plan.tasks[1].depends_on == ["task-code"]

    def test_development_display_word_does_not_add_preview_agent(self) -> None:
        plan = create_plan("@Orchestrator 创建一个展示学生成绩的页面")

        assert plan.agent_ids == [AGENT_CODE, AGENT_REVIEW]

    def test_explicit_preview_agent_only_adds_manual_preview_task(self) -> None:
        plan = create_plan("@Orchestrator 创建页面，然后 @PreviewAgent 打开预览")

        assert plan.agent_ids == [AGENT_CODE, AGENT_REVIEW, AGENT_PREVIEW]
        assert "不运行浏览器检查" in plan.tasks[-1].instruction
