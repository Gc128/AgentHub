from collections.abc import AsyncIterator

import pytest

from agenthub.agents.langchain_agent import LangChainAgent
from agenthub.agents.registry import create_default_registry
from agenthub.config import Settings
from agenthub.schemas.agent import AgentRunInput


class FakeLangChainMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class FakeLangChainModel:
    def __init__(self, responses: list[str], *, stream_chunks: list[str] | None = None) -> None:
        self.responses = responses
        self.stream_chunks = stream_chunks or []
        self.calls: list[list[tuple[str, str]]] = []
        self.stream_calls: list[list[tuple[str, str]]] = []

    async def ainvoke(self, messages: list[tuple[str, str]]) -> FakeLangChainMessage:
        self.calls.append(messages)
        return FakeLangChainMessage(self.responses.pop(0))

    async def astream(self, messages: list[tuple[str, str]]) -> AsyncIterator[FakeLangChainMessage]:
        self.stream_calls.append(messages)
        for chunk in self.stream_chunks:
            yield FakeLangChainMessage(chunk)


@pytest.mark.asyncio
async def test_langchain_agent_runs_model_and_parses_agent_result() -> None:
    model = FakeLangChainModel(
        [
            (
                '{"agent_id":"code-agent","content":"Generated via LangChain",'
                '"artifacts":[{"type":"code","title":"index.html",'
                '"data":{"filename":"index.html","content":"<main>ok</main>"}}],'
                '"next_actions":["review-agent"]}'
            )
        ]
    )
    agent = LangChainAgent(agent_id="code-agent", api_key="test-key", chat_model=model)

    result = await agent.run(
        AgentRunInput(
            conversation_id="conv_001",
            workspace_id="ws_001",
            user_message="生成页面",
        )
    )

    assert result.agent_id == "code-agent"
    assert result.content == "Generated via LangChain"
    assert result.artifacts[0].type == "code"
    assert result.next_actions == ["review-agent"]
    assert model.calls
    assert model.calls[0][0][0] == "system"
    assert model.calls[0][-1][0] == "user"


@pytest.mark.asyncio
async def test_langchain_agent_streams_model_chunks() -> None:
    model = FakeLangChainModel([], stream_chunks=["hello", " world"])
    agent = LangChainAgent(agent_id="code-agent", api_key="test-key", chat_model=model)

    chunks = [
        chunk
        async for chunk in agent.stream(
            AgentRunInput(
                conversation_id="conv_001",
                workspace_id="ws_001",
                user_message="hello",
            )
        )
    ]

    assert chunks == ["hello", " world"]
    assert model.stream_calls


def test_real_registry_uses_langchain_backed_agent() -> None:
    registry = create_default_registry(
        Settings(
            use_mock_agents=False,
            openai_api_key="test-key",
        )
    )

    orchestrator = registry.get("orchestrator")
    assert isinstance(orchestrator._llm, LangChainAgent)


@pytest.mark.asyncio
async def test_langchain_agent_uses_plain_text_model_after_structured_run() -> None:
    captured_kwargs: list[dict[str, object]] = []

    def factory(**kwargs: object) -> FakeLangChainModel:
        captured_kwargs.append(dict(kwargs))
        return FakeLangChainModel(
            [
                (
                    '{"agent_id":"code-agent","content":"structured",'
                    '"artifacts":[],"next_actions":[]}'
                )
                if len(captured_kwargs) == 1
                else "plain text"
            ]
        )

    agent = LangChainAgent(
        agent_id="code-agent",
        api_key="test-key",
        response_format="json_object",
        chat_model_factory=factory,
    )
    input_data = AgentRunInput(
        conversation_id="conv_001",
        workspace_id="ws_001",
        user_message="hello",
    )

    await agent.run(input_data)
    content = await agent.request_text(input_data, force_text=True)

    assert content == "plain text"
    assert captured_kwargs[0]["model_kwargs"] == {"response_format": {"type": "json_object"}}
    assert "model_kwargs" not in captured_kwargs[1]


def test_langchain_agent_maps_deepseek_extra_parameters() -> None:
    captured_kwargs: dict[str, object] = {}

    def factory(**kwargs: object) -> FakeLangChainModel:
        captured_kwargs.update(kwargs)
        return FakeLangChainModel(
            [('{"agent_id":"code-agent","content":"structured","artifacts":[],"next_actions":[]}')]
        )

    agent = LangChainAgent(
        agent_id="code-agent",
        api_key="test-key",
        model="deepseek-v4-flash",
        base_url="https://api.deepseek.com",
        response_format="json_object",
        thinking="disabled",
        max_tokens=4096,
        chat_model_factory=factory,
    )

    agent._get_chat_model()

    assert captured_kwargs["model_kwargs"] == {"response_format": {"type": "json_object"}}
    assert captured_kwargs["extra_body"] == {"thinking": {"type": "disabled"}}
    assert captured_kwargs["max_completion_tokens"] == 4096
    assert "max_tokens" not in captured_kwargs
