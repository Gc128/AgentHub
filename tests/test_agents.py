import pytest

from agenthub.agents.mock_agent import MockAgent
from agenthub.agents.registry import create_default_registry
from agenthub.core.errors import NotFoundError
from agenthub.schemas.agent import AgentRunInput
from agenthub.services.agent_service import AgentService


@pytest.mark.asyncio
async def test_mock_agent_returns_artifact() -> None:
    result = await MockAgent().run(
        AgentRunInput(
            conversation_id="conv_001",
            workspace_id="ws_001",
            user_message="生成一个 Todo 页面",
        )
    )
    assert result.agent_id == "mock-agent"
    assert result.artifacts[0].type == "code"


@pytest.mark.asyncio
async def test_code_and_review_agents_return_distinct_artifacts() -> None:
    registry = create_default_registry()
    code_result = await registry.get("code-agent").run(
        AgentRunInput(
            conversation_id="conv_001",
            workspace_id="ws_001",
            user_message="实现页面",
        )
    )
    review_result = await registry.get("review-agent").run(
        AgentRunInput(
            conversation_id="conv_001",
            workspace_id="ws_001",
            user_message="检查代码",
        )
    )
    assert code_result.artifacts[0].type == "code"
    assert review_result.artifacts[0].type == "file"
    assert code_result.content != review_result.content


def test_unknown_agent_raises_not_found() -> None:
    registry = create_default_registry()
    with pytest.raises(NotFoundError):
        registry.get("missing-agent")


def test_agent_service_lists_agents() -> None:
    service = AgentService(registry=create_default_registry())
    agent_ids = {agent.id for agent in service.list_agents()}
    assert {"orchestrator", "code-agent", "review-agent", "preview-agent"}.issubset(agent_ids)
