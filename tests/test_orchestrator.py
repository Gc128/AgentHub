from agenthub.orchestrator.planner import create_plan
from agenthub.orchestrator.router import route_agent


def test_route_code_agent_for_generation_request() -> None:
    assert route_agent("帮我实现一个页面") == "code-agent"


def test_create_plan_includes_review_agent() -> None:
    plan = create_plan("检查这个 bug")
    assert plan.tasks[0].agent_id == "review-agent"
