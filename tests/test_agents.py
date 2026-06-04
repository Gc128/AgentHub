import httpx
import pytest

from agenthub.agents.code_agent import CodeAgent
from agenthub.agents.mock_agent import MockAgent
from agenthub.agents.real_agent import RealAgent, RealAgentUnavailableError
from agenthub.agents.registry import AgentRegistry, create_default_registry
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


@pytest.mark.asyncio
async def test_preview_agent_uses_preview_url_field() -> None:
    registry = create_default_registry()
    result = await registry.get("preview-agent").run(
        AgentRunInput(
            conversation_id="conv_001",
            workspace_id="ws_001",
            user_message="预览页面",
        )
    )

    assert result.artifacts[0].type == "preview"
    assert "preview_url" in result.artifacts[0].data
    assert "url" not in result.artifacts[0].data


@pytest.mark.asyncio
async def test_real_agent_requires_configuration() -> None:
    agent = RealAgent(api_key=None)

    with pytest.raises(RealAgentUnavailableError, match="not configured"):
        await agent.run(
            AgentRunInput(
                conversation_id="conv_001",
                workspace_id="ws_001",
                user_message="hello",
            )
        )


@pytest.mark.asyncio
async def test_real_agent_requires_api_key_without_leaking_secret() -> None:
    agent = RealAgent(api_key=None)

    with pytest.raises(RealAgentUnavailableError) as exc_info:
        await agent.run(
            AgentRunInput(
                conversation_id="conv_001",
                workspace_id="ws_001",
                user_message="hello",
            )
        )

    assert "not configured" in str(exc_info.value)
    assert "sk-" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_real_agent_parses_structured_artifacts() -> None:
    payload = {
        "choices": [
            {
                "message": {
                    "content": (
                        '{"agent_id":"code-agent","content":"Generated code",'
                        '"artifacts":[{"id":"artifact_code","type":"code",'
                        '"title":"Code","data":{"filename":"index.html",'
                        '"language":"html","content":"<main>ok</main>"}}],'
                        '"next_actions":["review-agent"]}'
                    )
                }
            }
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-key"
        return httpx.Response(200, json=payload)

    agent = RealAgent(
        agent_id="code-agent",
        api_key="test-key",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    result = await agent.run(
        AgentRunInput(
            conversation_id="conv_001",
            workspace_id="ws_001",
            user_message="生成页面",
        )
    )

    assert result.agent_id == "code-agent"
    assert result.content == "Generated code"
    assert result.artifacts[0].type == "code"
    assert result.artifacts[0].data["filename"] == "index.html"
    assert result.next_actions == ["review-agent"]


@pytest.mark.asyncio
async def test_real_agent_normalizes_loose_code_artifacts() -> None:
    payload = {
        "choices": [
            {
                "message": {
                    "content": (
                        '{"agent_id":"code-agent","content":"Generated code",'
                        '"artifacts":[{"filename":"todo.html","language":"html",'
                        '"content":"<main>ok</main>"}],"next_actions":[]}'
                    )
                }
            }
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    agent = RealAgent(
        agent_id="code-agent",
        api_key="test-key",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    result = await agent.run(
        AgentRunInput(
            conversation_id="conv_001",
            workspace_id="ws_001",
            user_message="生成页面",
        )
    )

    assert result.artifacts[0].id == "artifact-code-agent-1"
    assert result.artifacts[0].type == "code"
    assert result.artifacts[0].title == "todo.html"
    assert result.artifacts[0].data["filename"] == "todo.html"


@pytest.mark.asyncio
async def test_real_agent_infers_type_from_nested_artifact_data() -> None:
    payload = {
        "choices": [
            {
                "message": {
                    "content": (
                        '{"agent_id":"code-agent","content":"Generated code",'
                        '"artifacts":[{"data":{"filename":"todo.html","language":"html",'
                        '"content":"<main>ok</main>"}}],"next_actions":[]}'
                    )
                }
            }
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    agent = RealAgent(
        agent_id="code-agent",
        api_key="test-key",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    result = await agent.run(
        AgentRunInput(
            conversation_id="conv_001",
            workspace_id="ws_001",
            user_message="生成页面",
        )
    )

    assert result.artifacts[0].type == "code"
    assert result.artifacts[0].title == "todo.html"


@pytest.mark.asyncio
async def test_real_agent_extracts_code_artifacts_from_markdown_content() -> None:
    markdown = (
        "已生成页面代码。\n\n"
        '```tsx filename="src/App.tsx"\n'
        "export default function App() { return <main>ok</main> }\n"
        "```\n\n"
        "点击 Diff 后可以写入 workspace。"
    )
    payload = {"choices": [{"message": {"content": markdown}}]}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    agent = RealAgent(
        agent_id="code-agent",
        api_key="test-key",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    result = await agent.run(
        AgentRunInput(
            conversation_id="conv_001",
            workspace_id="ws_001",
            user_message="生成页面",
        )
    )

    assert result.content == markdown
    assert result.artifacts[0].type == "code"
    assert result.artifacts[0].title == "src/App.tsx"
    assert result.artifacts[0].data == {
        "filename": "src/App.tsx",
        "language": "tsx",
        "content": "export default function App() { return <main>ok</main> }",
    }


@pytest.mark.asyncio
async def test_real_agent_extracts_artifacts_from_json_markdown_content() -> None:
    markdown = "下面是页面代码。\n\n```html index.html\n<main>ok</main>\n```"
    payload = {
        "choices": [
            {
                "message": {
                    "content": (
                        '{"agent_id":"code-agent","content":'
                        f"{json_string(markdown)},"
                        '"artifacts":[],"next_actions":[]}'
                    )
                }
            }
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    agent = RealAgent(
        agent_id="code-agent",
        api_key="test-key",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    result = await agent.run(
        AgentRunInput(
            conversation_id="conv_001",
            workspace_id="ws_001",
            user_message="生成页面",
        )
    )

    assert result.content == markdown
    assert result.artifacts[0].type == "code"
    assert result.artifacts[0].data["filename"] == "index.html"
    assert result.artifacts[0].data["content"] == "<main>ok</main>"


@pytest.mark.asyncio
async def test_code_agent_synthesizes_diff_from_code_artifact() -> None:
    class CodeOnlyAdapter:
        id = "llm"
        name = "LLM"
        capabilities = ["llm"]

        async def run(self, input_data: AgentRunInput) -> object:
            from agenthub.schemas.agent import AgentRunResult
            from agenthub.schemas.artifact import Artifact

            return AgentRunResult(
                agent_id="code-agent",
                content="Generated code",
                artifacts=[
                    Artifact(
                        id="artifact-code",
                        type="code",
                        title="todo.html",
                        data={
                            "filename": "todo.html",
                            "language": "html",
                            "content": "<main>ok</main>\n",
                        },
                    )
                ],
                next_actions=[],
            )

    result = await CodeAgent(CodeOnlyAdapter()).run(
        AgentRunInput(
            conversation_id="conv_001",
            workspace_id="ws_001",
            user_message="生成页面",
        )
    )

    artifact_types = [artifact.type for artifact in result.artifacts]
    assert artifact_types == ["code", "diff"]
    assert '```html filename="todo.html"' in result.content
    assert "<main>ok</main>" in result.content
    assert result.artifacts[1].data["filename"] == "todo.html"
    assert "+++ b/todo.html" in result.artifacts[1].data["diff"]


@pytest.mark.asyncio
async def test_code_agent_generates_diff_against_existing_workspace_file(tmp_path) -> None:
    workspace_dir = tmp_path / "ws_001"
    workspace_dir.mkdir()
    (workspace_dir / "todo.html").write_text("<main>old</main>\n", encoding="utf-8")

    class CodeOnlyAdapter:
        id = "llm"
        name = "LLM"
        capabilities = ["llm"]

        async def run(self, input_data: AgentRunInput) -> object:
            from agenthub.schemas.agent import AgentRunResult
            from agenthub.schemas.artifact import Artifact

            return AgentRunResult(
                agent_id="code-agent",
                content="Generated code",
                artifacts=[
                    Artifact(
                        id="artifact-code",
                        type="code",
                        title="todo.html",
                        data={
                            "filename": "todo.html",
                            "language": "html",
                            "content": "<main>new</main>\n",
                        },
                    )
                ],
                next_actions=[],
            )

    result = await CodeAgent(CodeOnlyAdapter(), workspace_root=tmp_path).run(
        AgentRunInput(
            conversation_id="conv_001",
            workspace_id="ws_001",
            user_message="生成页面",
        )
    )

    diff = str(result.artifacts[1].data["diff"])
    assert "-<main>old</main>" in diff
    assert "+<main>new</main>" in diff


@pytest.mark.asyncio
async def test_code_agent_allows_non_code_greeting_without_artifacts() -> None:
    class TextOnlyAdapter:
        id = "llm"
        name = "LLM"
        capabilities = ["llm"]

        async def run(self, input_data: AgentRunInput) -> object:
            from agenthub.schemas.agent import AgentRunResult

            return AgentRunResult(
                agent_id="code-agent",
                content="你好，请告诉我你想实现的开发需求。",
                artifacts=[],
                next_actions=[],
            )

    result = await CodeAgent(TextOnlyAdapter()).run(
        AgentRunInput(
            conversation_id="conv_001",
            workspace_id="ws_001",
            user_message="@CodeAgent 你好",
        )
    )

    assert result.content == "你好，请告诉我你想实现的开发需求。"
    assert result.artifacts == []


@pytest.mark.asyncio
async def test_real_agent_sends_structured_generation_parameters() -> None:
    payload = {
        "choices": [
            {
                "message": {
                    "content": (
                        '{"agent_id":"code-agent","content":"Generated code",'
                        '"artifacts":[],"next_actions":[]}'
                    )
                }
            }
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        request_payload = json_from_request(request)
        assert request_payload["response_format"] == {"type": "json_object"}
        assert request_payload["thinking"] == {"type": "disabled"}
        assert request_payload["max_tokens"] == 4096
        return httpx.Response(200, json=payload)

    agent = RealAgent(
        agent_id="code-agent",
        api_key="test-key",
        response_format="json_object",
        thinking="disabled",
        max_tokens=4096,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    await agent.run(
        AgentRunInput(
            conversation_id="conv_001",
            workspace_id="ws_001",
            user_message="生成页面",
        )
    )


@pytest.mark.asyncio
async def test_real_agent_reports_auth_status_without_leaking_secret() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            text="Authentication Fails (auth header format should be Bearer sk-secret)",
        )

    agent = RealAgent(
        api_key="sk-secret",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(RealAgentUnavailableError) as exc_info:
        await agent.run(
            AgentRunInput(
                conversation_id="conv_001",
                workspace_id="ws_001",
                user_message="hello",
            )
        )

    message = str(exc_info.value)
    assert "authentication failed with status 401" in message
    assert "sk-secret" not in message


@pytest.mark.asyncio
async def test_real_agent_reports_timeout_with_config_hint() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    agent = RealAgent(
        api_key="test-key",
        timeout_seconds=12,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(RealAgentUnavailableError) as exc_info:
        await agent.run(
            AgentRunInput(
                conversation_id="conv_001",
                workspace_id="ws_001",
                user_message="hello",
            )
        )

    assert "timed out after 12" in str(exc_info.value)
    assert "AGENT_REQUEST_TIMEOUT_SECONDS" in str(exc_info.value)


@pytest.mark.asyncio
async def test_agent_service_does_not_duplicate_agent_failure_prefix() -> None:
    class FailingAdapter:
        id = "code-agent"
        name = "Code Agent"
        capabilities = ["code"]

        async def run(self, input_data: AgentRunInput) -> object:
            raise RuntimeError("provider unavailable")

    service = AgentService(registry=AgentRegistry([FailingAdapter()]))

    results = await service.run_for_message(
        AgentRunInput(
            conversation_id="conv_001",
            workspace_id="ws_001",
            user_message="@CodeAgent hello",
        )
    )

    assert results[0].content.count("Agent code-agent failed") == 1
    assert "provider unavailable" in results[0].content


def test_unknown_agent_raises_not_found() -> None:
    registry = create_default_registry()
    with pytest.raises(NotFoundError):
        registry.get("missing-agent")


def test_agent_service_lists_agents() -> None:
    service = AgentService(registry=create_default_registry())
    agent_ids = {agent.id for agent in service.list_agents()}
    assert {"orchestrator", "code-agent", "review-agent", "preview-agent"}.issubset(agent_ids)


def json_from_request(request: httpx.Request) -> dict[str, object]:
    import json

    payload = json.loads(request.content.decode())
    assert isinstance(payload, dict)
    return payload


def json_string(value: str) -> str:
    import json

    return json.dumps(value, ensure_ascii=False)
