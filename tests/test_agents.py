import pytest

from agenthub.agents.mock_agent import MockAgent
from agenthub.schemas.agent import AgentRunInput


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
