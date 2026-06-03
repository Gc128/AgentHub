from agenthub.orchestrator.planner import create_plan
from agenthub.orchestrator.router import route_agent


def test_route_code_agent_for_generation_request() -> None:
    assert route_agent("帮我实现一个页面") == "code-agent"


def test_create_plan_includes_review_agent() -> None:
    plan = create_plan("检查这个 bug")
    assert plan.tasks[0].agent_id == "review-agent"


def test_orchestrator_plan_includes_demo_chain() -> None:
    plan = create_plan("@Orchestrator 帮我做一个 Todo List 网页")
    assert [task.agent_id for task in plan.tasks] == [
        "code-agent",
        "review-agent",
        "preview-agent",
    ]


def test_route_mentions_are_case_insensitive() -> None:
    assert route_agent("@codeagent 实现页面") == "code-agent"
