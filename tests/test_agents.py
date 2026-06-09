import json

import httpx
import pytest

from agenthub.agents.code_agent import CodeAgent
from agenthub.agents.mock_agent import MockAgent
from agenthub.agents.real_agent import RealAgent, RealAgentSchemaError, RealAgentUnavailableError
from agenthub.agents.registry import AgentRegistry, OrchestratorAdapter, create_default_registry
from agenthub.core.errors import AgentExecutionError, NotFoundError
from agenthub.orchestrator.planner import AgentTask, OrchestratorDecision, OrchestratorPlan
from agenthub.schemas.agent import AgentRunInput, AgentRunResult
from agenthub.schemas.artifact import Artifact
from agenthub.services.agent_service import AgentService


def json_body(request: httpx.Request) -> dict[str, object]:
    payload = json.loads(request.content.decode())
    assert isinstance(payload, dict)
    return payload


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
    assert "Preview 状态为 ready" in result.content


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
async def test_real_agent_retries_transient_transport_error() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.RemoteProtocolError("server disconnected")
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"agent_id":"code-agent","content":"ok",'
                                '"artifacts":[],"next_actions":[]}'
                            )
                        }
                    }
                ]
            },
        )

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

    assert calls == 2
    assert result.content == "ok"


@pytest.mark.asyncio
async def test_real_agent_streams_openai_compatible_deltas() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert json_body(request)["stream"] is True
        return httpx.Response(
            200,
            content=(
                b'data: {"choices":[{"delta":{"content":"hello"}}]}\n\n'
                b'data: {"choices":[{"delta":{"content":" world"}}]}\n\n'
                b"data: [DONE]\n\n"
            ),
        )

    agent = RealAgent(
        agent_id="code-agent",
        api_key="test-key",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

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


@pytest.mark.asyncio
async def test_real_agent_repairs_structured_agent_result_once() -> None:
    calls: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json_body(request)
        calls.append(payload)
        if len(calls) == 1:
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "[1, 2]"}}]},
            )
        assert "repair" in str(payload["messages"][0]["content"]).lower()
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"agent_id":"review-agent","content":"fixed",'
                                '"artifacts":[],"next_actions":[]}'
                            )
                        }
                    }
                ]
            },
        )

    agent = RealAgent(
        agent_id="review-agent",
        api_key="test-key",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    result = await agent.run(
        AgentRunInput(
            conversation_id="conv_001",
            workspace_id="ws_001",
            user_message="review",
        )
    )

    assert result.content == "fixed"
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_real_agent_schema_failure_after_repair_is_specific() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "[1, 2]"}}]},
        )

    agent = RealAgent(
        agent_id="review-agent",
        api_key="test-key",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(RealAgentSchemaError, match="AgentRunResult"):
        await agent.run(
            AgentRunInput(
                conversation_id="conv_001",
                workspace_id="ws_001",
                user_message="review",
            )
        )


@pytest.mark.asyncio
async def test_real_agent_repairs_malformed_json_response() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        content = (
            '{"agent_id":"code-agent","content":"fixed","artifacts":[],"next_actions":[]}'
            if calls == 2
            else '{"agent_id":"code-agent","content":'
        )
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

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

    assert result.content == "fixed"
    assert calls == 2


@pytest.mark.asyncio
async def test_llm_orchestrator_handles_plain_chat() -> None:
    requests: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json_body(request))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"mode":"chat","content":"你好，我是大模型 Orchestrator。",'
                                '"plan":null}'
                            )
                        }
                    }
                ]
            },
        )

    orchestrator = OrchestratorAdapter(
        RealAgent(
            agent_id="orchestrator",
            api_key="test-key",
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )
    )
    service = AgentService(registry=AgentRegistry([orchestrator]))

    results = await service.run_for_message(
        AgentRunInput(
            conversation_id="conv_001",
            workspace_id="ws_001",
            user_message="你好",
        )
    )

    assert results[0].agent_id == "orchestrator"
    assert results[0].content == "你好，我是大模型 Orchestrator。"
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_llm_orchestrator_accepts_markdown_plan_text() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                "## 任务拆解\n\n"
                                "1. code-agent: 实现页面。\n"
                                "2. review-agent: 审查代码。\n"
                                "3. preview-agent: 验证预览。"
                            )
                        }
                    }
                ]
            },
        )

    orchestrator = OrchestratorAdapter(
        RealAgent(
            agent_id="orchestrator",
            api_key="test-key",
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )
    )

    decision = await orchestrator.decide(
        AgentRunInput(
            conversation_id="conv_001",
            workspace_id="ws_001",
            user_message="@Orchestrator 做一个页面",
        )
    )

    assert decision.mode == "plan"
    assert decision.plan is not None
    assert decision.plan.agent_ids == ["code-agent", "review-agent", "preview-agent"]


@pytest.mark.asyncio
async def test_llm_orchestrator_accepts_top_level_task_list_json() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                [
                                    {
                                        "agent": "code-agent",
                                        "task": "实现页面并输出 code/diff。",
                                    }
                                ]
                            )
                        }
                    }
                ]
            },
        )

    orchestrator = OrchestratorAdapter(
        RealAgent(
            agent_id="orchestrator",
            api_key="test-key",
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )
    )

    decision = await orchestrator.decide(
        AgentRunInput(
            conversation_id="conv_001",
            workspace_id="ws_001",
            user_message="@Orchestrator 做一个页面",
        )
    )

    assert decision.mode == "plan"
    assert decision.plan is not None
    assert decision.plan.tasks[0].agent_id == "code-agent"


@pytest.mark.asyncio
async def test_llm_orchestrator_plan_drives_harness_without_copying_user_request() -> None:
    user_message = "@Orchestrator 帮我做一个 Todo 页面"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "mode": "plan",
                                    "content": "## 任务拆解\n\n由 LLM 生成的任务分工。",
                                    "plan": {
                                        "summary": "llm plan",
                                        "tasks": [
                                            {
                                                "task_id": "task-code",
                                                "agent_id": "code-agent",
                                                "instruction": (
                                                    "实现 Todo 页面并输出 code/diff artifact。"
                                                ),
                                                "depends_on": [],
                                            },
                                            {
                                                "task_id": "task-review",
                                                "agent_id": "review-agent",
                                                "instruction": (
                                                    "审查前序 diff 并输出 findings/risk_level。"
                                                ),
                                                "depends_on": ["task-code"],
                                            },
                                            {
                                                "task_id": "task-preview",
                                                "agent_id": "preview-agent",
                                                "instruction": (
                                                    "验证 preview 状态并输出 preview artifact。"
                                                ),
                                                "depends_on": ["task-review"],
                                            },
                                        ],
                                    },
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            },
        )

    registry = AgentRegistry(
        [
            OrchestratorAdapter(
                RealAgent(
                    agent_id="orchestrator",
                    api_key="test-key",
                    http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
                )
            ),
            MockAgent(agent_id="code-agent"),
            MockAgent(agent_id="review-agent"),
            MockAgent(agent_id="preview-agent"),
        ]
    )
    service = AgentService(registry=registry)

    results = await service.run_for_message(
        AgentRunInput(
            conversation_id="conv_001",
            workspace_id="ws_001",
            user_message=user_message,
        )
    )

    assert [result.agent_id for result in results] == [
        "orchestrator",
        "code-agent",
        "review-agent",
        "preview-agent",
    ]
    assert user_message not in results[0].content
    assert results[0].content == "## 任务拆解\n\n由 LLM 生成的任务分工。"


@pytest.mark.asyncio
async def test_llm_orchestrator_code_plan_is_guarded_with_review_and_preview() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "mode": "plan",
                                    "content": "## 任务拆解\n\n先写代码。",
                                    "plan": {
                                        "summary": "llm partial plan",
                                        "tasks": [
                                            {
                                                "task_id": "task-code",
                                                "agent_id": "code-agent",
                                                "instruction": (
                                                    "实现页面并输出 code/diff artifact。"
                                                ),
                                                "depends_on": [],
                                            }
                                        ],
                                    },
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            },
        )

    registry = AgentRegistry(
        [
            OrchestratorAdapter(
                RealAgent(
                    agent_id="orchestrator",
                    api_key="test-key",
                    http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
                )
            ),
            MockAgent(agent_id="code-agent"),
            MockAgent(agent_id="review-agent"),
            MockAgent(agent_id="preview-agent"),
        ]
    )
    service = AgentService(registry=registry)

    results = await service.run_for_message(
        AgentRunInput(
            conversation_id="conv_001",
            workspace_id="ws_001",
            user_message="@Orchestrator 帮我做一个计数器网页",
        )
    )

    assert [result.agent_id for result in results] == [
        "orchestrator",
        "code-agent",
        "review-agent",
        "preview-agent",
    ]
    assert "review-agent" in results[0].content
    assert "preview-agent" in results[0].content
    assert "兜底" not in results[0].content


@pytest.mark.asyncio
async def test_code_agent_repairs_static_todo_before_fallback(tmp_path) -> None:
    class StaticTodoAdapter:
        id = "real-code"
        name = "Real Code"
        capabilities = ["code"]
        calls = 0

        async def run(self, input_data: AgentRunInput) -> AgentRunResult:
            self.calls += 1
            if self.calls == 2:
                return AgentRunResult(
                    agent_id="code-agent",
                    content="已修复 Todo 交互并保留优先级字段。",
                    artifacts=[
                        Artifact(
                            id="repaired-todo",
                            type="code",
                            title="index.html",
                            data={
                                "filename": "index.html",
                                "language": "html",
                                "content": (
                                    '<form id="todo-form"><input id="todo-input">'
                                    '<select id="priority"></select><button>添加</button></form>'
                                    '<ul id="todo-list"></ul><script>'
                                    'document.querySelector("#todo-form").addEventListener'
                                    '("submit", (event) => { event.preventDefault(); });'
                                    "</script>"
                                ),
                            },
                        )
                    ],
                )
            return AgentRunResult(
                agent_id="code-agent",
                content="静态 Todo 页面",
                artifacts=[
                    Artifact(
                        id="static-todo",
                        type="code",
                        title="index.html",
                        data={
                            "filename": "index.html",
                            "language": "html",
                            "content": "<button>添加</button><ul><li>Todo</li></ul>",
                        },
                    )
                ],
            )

    workspace_id = "ws_001"
    (tmp_path / workspace_id).mkdir()
    adapter = StaticTodoAdapter()
    agent = CodeAgent(adapter, workspace_root=tmp_path)

    result = await agent.run(
        AgentRunInput(
            conversation_id="conv_001",
            workspace_id=workspace_id,
            user_message="帮我做一个带优先级的 Todo List 网页",
        )
    )

    code_artifact = next(artifact for artifact in result.artifacts if artifact.type == "code")
    diff_artifact = next(artifact for artifact in result.artifacts if artifact.type == "diff")
    content = str(code_artifact.data["content"])
    assert adapter.calls == 2
    assert "addEventListener" in content
    assert "priority" in content
    assert diff_artifact.data["filename"] == "index.html"


@pytest.mark.asyncio
async def test_code_agent_repairs_missing_required_data_testids(tmp_path) -> None:
    captured_missing: list[list[str]] = []

    class MissingTestIdAdapter:
        id = "real-code"
        name = "Real Code"
        capabilities = ["code"]
        calls = 0

        async def run(self, input_data: AgentRunInput) -> AgentRunResult:
            self.calls += 1
            captured_missing.append(list(input_data.context.get("missing_data_testids", [])))
            if self.calls == 2:
                content = (
                    '<main data-testid="flashcard-app">'
                    '<section data-testid="flashcard-card">Apple</section>'
                    '<button data-testid="flip-card">翻面</button>'
                    "</main>"
                )
            else:
                content = (
                    '<main data-testid="flashcard-app">'
                    '<section data-testid="flashcard-card">Apple</section>'
                    '<button data-testid="flip-button">翻面</button>'
                    "</main>"
                )
            return AgentRunResult(
                agent_id="code-agent",
                content=f'```html filename="index.html"\n{content}\n```',
                artifacts=[
                    Artifact(
                        id=f"code-{self.calls}",
                        type="code",
                        title="index.html",
                        data={
                            "filename": "index.html",
                            "language": "html",
                            "content": content,
                        },
                    )
                ],
            )

    workspace_id = "ws_001"
    (tmp_path / workspace_id).mkdir()
    adapter = MissingTestIdAdapter()
    agent = CodeAgent(adapter, workspace_root=tmp_path)

    result = await agent.run(
        AgentRunInput(
            conversation_id="conv_001",
            workspace_id=workspace_id,
            user_message=(
                "做一个单词卡片练习网页。必须包含 data-testid: "
                "flashcard-app, flashcard-card, flip-card。"
            ),
        )
    )

    code_artifact = next(artifact for artifact in result.artifacts if artifact.type == "code")
    diff_artifact = next(artifact for artifact in result.artifacts if artifact.type == "diff")
    assert adapter.calls == 2
    assert captured_missing[-1] == ["flip-card"]
    assert 'data-testid="flip-card"' in str(code_artifact.data["content"])
    assert diff_artifact.data["filename"] == "index.html"


@pytest.mark.asyncio
async def test_code_agent_patches_existing_button_when_testid_repair_still_missing(
    tmp_path,
) -> None:
    class StillMissingTestIdAdapter:
        id = "real-code"
        name = "Real Code"
        capabilities = ["code"]
        calls = 0

        async def run(self, input_data: AgentRunInput) -> AgentRunResult:
            self.calls += 1
            content = (
                '<main data-testid="appointment-app">'
                '<form data-testid="appointment-form">'
                '<button data-testid="add-appointment">添加预约</button>'
                "</form>"
                '<ul data-testid="appointment-list">'
                '<li><button class="delete-button">删除</button></li>'
                "</ul>"
                "</main>"
            )
            return AgentRunResult(
                agent_id="code-agent",
                content=f'```html filename="index.html"\n{content}\n```',
                artifacts=[
                    Artifact(
                        id=f"code-{self.calls}",
                        type="code",
                        title="index.html",
                        data={
                            "filename": "index.html",
                            "language": "html",
                            "content": content,
                        },
                    )
                ],
            )

    workspace_id = "ws_001"
    (tmp_path / workspace_id).mkdir()
    adapter = StillMissingTestIdAdapter()
    agent = CodeAgent(adapter, workspace_root=tmp_path)

    result = await agent.run(
        AgentRunInput(
            conversation_id="conv_001",
            workspace_id=workspace_id,
            user_message=(
                "做一个预约登记网页。必须包含 data-testid: appointment-app, "
                "appointment-form, appointment-list, add-appointment, delete-appointment。"
            ),
        )
    )

    code_artifact = next(artifact for artifact in result.artifacts if artifact.type == "code")
    assert adapter.calls == 3
    assert 'data-testid="delete-appointment"' in str(code_artifact.data["content"])
    assert "删除" in str(code_artifact.data["content"])


@pytest.mark.asyncio
async def test_code_agent_replaces_empty_diff_artifact(tmp_path) -> None:
    class EmptyDiffAdapter:
        id = "real-code"
        name = "Real Code"
        capabilities = ["code"]

        async def run(self, input_data: AgentRunInput) -> AgentRunResult:
            return AgentRunResult(
                agent_id="code-agent",
                content="已生成页面。",
                artifacts=[
                    Artifact(
                        id="code",
                        type="code",
                        title="index.html",
                        data={
                            "filename": "index.html",
                            "language": "html",
                            "content": "<main>ok</main>",
                        },
                    ),
                    Artifact(
                        id="empty-diff",
                        type="diff",
                        title="index.html diff",
                        data={"filename": "index.html", "diff": ""},
                    ),
                ],
            )

    workspace_id = "ws_001"
    (tmp_path / workspace_id).mkdir()
    agent = CodeAgent(EmptyDiffAdapter(), workspace_root=tmp_path)

    result = await agent.run(
        AgentRunInput(
            conversation_id="conv_001",
            workspace_id=workspace_id,
            user_message="做一个简单网页",
        )
    )

    diff_artifacts = [artifact for artifact in result.artifacts if artifact.type == "diff"]
    assert diff_artifacts
    assert all(str(artifact.data.get("diff", "")).strip() for artifact in diff_artifacts)
    assert diff_artifacts[0].id != "empty-diff"


@pytest.mark.asyncio
async def test_code_agent_sanitizes_fallback_terms_in_generated_code(tmp_path) -> None:
    class FallbackCommentAdapter:
        id = "real-code"
        name = "Real Code"
        capabilities = ["code"]

        async def run(self, input_data: AgentRunInput) -> AgentRunResult:
            content = "<script>// 兜底逻辑\nconst mode = 'ok';</script>"
            return AgentRunResult(
                agent_id="code-agent",
                content=f'说明：兜底分支。\n\n```html filename="index.html"\n{content}\n```',
                artifacts=[
                    Artifact(
                        id="code",
                        type="code",
                        title="index.html",
                        data={
                            "filename": "index.html",
                            "language": "html",
                            "content": content,
                        },
                    )
                ],
            )

    workspace_id = "ws_001"
    (tmp_path / workspace_id).mkdir()
    agent = CodeAgent(FallbackCommentAdapter(), workspace_root=tmp_path)

    result = await agent.run(
        AgentRunInput(
            conversation_id="conv_001",
            workspace_id=workspace_id,
            user_message="做一个简单网页",
        )
    )

    assert "兜底" not in result.model_dump_json()
    assert "默认" in result.model_dump_json()


@pytest.mark.asyncio
async def test_code_agent_todo_fallback_is_request_aware(tmp_path) -> None:
    class EmptyCodeAdapter:
        id = "real-code"
        name = "Real Code"
        capabilities = ["code"]

        async def run(self, input_data: AgentRunInput) -> AgentRunResult:
            return AgentRunResult(agent_id="code-agent", content="没有代码", artifacts=[])

    workspace_id = "ws_001"
    (tmp_path / workspace_id).mkdir()
    agent = CodeAgent(EmptyCodeAdapter(), workspace_root=tmp_path, allow_fallbacks=True)

    minimal = await agent.run(
        AgentRunInput(
            conversation_id="conv_001",
            workspace_id=workspace_id,
            user_message="帮我做一个极简 Todo List 网页",
        )
    )
    detailed = await agent.run(
        AgentRunInput(
            conversation_id="conv_002",
            workspace_id=workspace_id,
            user_message="帮我做一个带优先级、截止日期和筛选的 Todo List 网页",
        )
    )

    minimal_code = next(artifact for artifact in minimal.artifacts if artifact.type == "code")
    detailed_code = next(artifact for artifact in detailed.artifacts if artifact.type == "code")
    assert minimal_code.data["content"] != detailed_code.data["content"]
    assert detailed_code.data["features"] == {
        "priority": True,
        "due_date": True,
        "filter": True,
    }
    assert minimal_code.data["features"] == {
        "priority": False,
        "due_date": False,
        "filter": False,
    }


@pytest.mark.asyncio
async def test_code_agent_grade_request_does_not_use_todo_fallback(tmp_path) -> None:
    class SchemaFailingAdapter:
        id = "real-code"
        name = "Real Code"
        capabilities = ["code"]

        async def run(self, input_data: AgentRunInput) -> AgentRunResult:
            raise RealAgentSchemaError("bad code schema")

    workspace_id = "ws_001"
    (tmp_path / workspace_id).mkdir()
    agent = CodeAgent(SchemaFailingAdapter(), workspace_root=tmp_path, allow_fallbacks=True)

    result = await agent.run(
        AgentRunInput(
            conversation_id="conv_001",
            workspace_id=workspace_id,
            user_message=(
                "根据 context.user_request 实现代码。\n\n"
                "用户原始需求如下：@Orchestrator 我想你重新输出 todolist 代码，"
                "用来展示一个班各个学生的成绩，自己写模拟生成10个，"
                "用户可以添加和删除某个数据，添加排序按钮按照成绩排序"
            ),
            context={
                "user_request": (
                    "@Orchestrator 我想你重新输出 todolist 代码，完成用来展示一个班"
                    "各个学生的成绩，模拟生成10个，用户可以添加和删除某个数据，"
                    "添加排序按钮按照成绩排序"
                )
            },
        )
    )

    code_artifact = next(artifact for artifact in result.artifacts if artifact.type == "code")
    content = str(code_artifact.data["content"])
    assert "学生成绩管理" in content
    assert "学生 10" in content
    assert "按成绩排序" in content
    assert "todo-form" not in content


@pytest.mark.asyncio
async def test_code_agent_schema_failure_does_not_fallback_by_default(tmp_path) -> None:
    class SchemaFailingAdapter:
        id = "real-code"
        name = "Real Code"
        capabilities = ["code"]

        async def run(self, input_data: AgentRunInput) -> AgentRunResult:
            raise RealAgentSchemaError("bad code schema")

    workspace_id = "ws_001"
    (tmp_path / workspace_id).mkdir()
    agent = CodeAgent(SchemaFailingAdapter(), workspace_root=tmp_path)

    with pytest.raises(AgentExecutionError, match="could not be parsed"):
        await agent.run(
            AgentRunInput(
                conversation_id="conv_001",
                workspace_id=workspace_id,
                user_message="帮我做一个 Todo List 网页",
            )
        )


@pytest.mark.asyncio
async def test_orchestrator_code_step_passes_original_request_to_code_agent() -> None:
    captured_user_messages: list[str] = []

    class CapturingCodeAdapter:
        id = "code-agent"
        name = "Code Agent"
        capabilities = ["code"]

        async def run(self, input_data: AgentRunInput) -> AgentRunResult:
            captured_user_messages.append(input_data.user_message)
            return AgentRunResult(
                agent_id="code-agent",
                content="ok",
                artifacts=[
                    Artifact(
                        id="code",
                        type="code",
                        title="index.html",
                        data={"filename": "index.html", "content": "<main></main>"},
                    ),
                    Artifact(
                        id="diff",
                        type="diff",
                        title="index.html diff",
                        data={"filename": "index.html", "diff": "--- a/index.html\n"},
                    ),
                ],
            )

    service = AgentService(registry=AgentRegistry([CapturingCodeAdapter()]))
    plan = OrchestratorPlan(
        summary="one code step",
        tasks=[
            AgentTask(
                task_id="task-code",
                agent_id="code-agent",
                instruction="根据 context.user_request 设计并实现可运行的代码变更。",
            )
        ],
    )
    original_request = (
        "@Orchestrator 我想你重新输出 todolist 代码，展示学生成绩，"
        "模拟生成10个，支持添加、删除和按成绩排序"
    )

    results = await service._run_orchestrator_pipeline(
        AgentRunInput(
            conversation_id="conv_001",
            workspace_id="ws_001",
            user_message=original_request,
        ),
        plan=plan,
        plan_content="计划",
    )

    assert [result.agent_id for result in results] == ["orchestrator", "code-agent"]
    assert captured_user_messages
    assert original_request in captured_user_messages[0]
    assert "Code Agent 必须以这段需求为实现依据" in captured_user_messages[0]


@pytest.mark.asyncio
async def test_review_agent_schema_failure_returns_findings_artifact() -> None:
    from agenthub.agents.review_agent import ReviewAgent

    class SchemaFailingAdapter:
        id = "real-review"
        name = "Real Review"
        capabilities = ["review"]

        async def run(self, input_data: AgentRunInput) -> AgentRunResult:
            raise RealAgentSchemaError("bad review schema")

    result = await ReviewAgent(SchemaFailingAdapter(), allow_fallbacks=True).run(
        AgentRunInput(
            conversation_id="conv_001",
            workspace_id="ws_001",
            user_message="检查 Todo 页面",
            context={
                "prior_artifacts": [
                    {"type": "code"},
                    {"type": "diff"},
                ]
            },
        )
    )

    assert result.agent_id == "review-agent"
    assert result.artifacts[0].type == "file"
    assert "findings" in result.artifacts[0].data
    assert "risk_level" in result.artifacts[0].data


@pytest.mark.asyncio
async def test_review_agent_schema_failure_recovers_by_default() -> None:
    from agenthub.agents.review_agent import ReviewAgent

    class SchemaFailingAdapter:
        id = "real-review"
        name = "Real Review"
        capabilities = ["review"]

        async def run(self, input_data: AgentRunInput) -> AgentRunResult:
            raise RealAgentSchemaError("bad review schema")

    result = await ReviewAgent(SchemaFailingAdapter()).run(
        AgentRunInput(
            conversation_id="conv_001",
            workspace_id="ws_001",
            user_message="检查 Todo 页面",
            context={"prior_artifacts": [{"type": "code"}, {"type": "diff"}]},
        )
    )

    assert result.agent_id == "review-agent"
    assert result.artifacts[0].type == "file"
    assert result.artifacts[0].data["source"] == "schema-recovery-review"
    assert "fallback" not in str(result.model_dump(mode="json")).lower()


@pytest.mark.asyncio
async def test_preview_agent_schema_failure_returns_preview_artifact() -> None:
    from agenthub.agents.preview_agent import PreviewAgent

    class SchemaFailingAdapter:
        id = "real-preview"
        name = "Real Preview"
        capabilities = ["preview"]

        async def run(self, input_data: AgentRunInput) -> AgentRunResult:
            raise RealAgentSchemaError("bad preview schema")

    result = await PreviewAgent(SchemaFailingAdapter(), allow_fallbacks=True).run(
        AgentRunInput(
            conversation_id="conv_001",
            workspace_id="ws_001",
            user_message="预览 Todo 页面",
            context={"preview_status": "ready", "preview_url": "http://127.0.0.1:18000"},
        )
    )

    assert result.agent_id == "preview-agent"
    assert result.artifacts[0].type == "preview"
    assert result.artifacts[0].data["status"] == "ready"
    assert "Preview 状态为 ready" in result.content


@pytest.mark.asyncio
async def test_preview_agent_schema_failure_recovers_by_default() -> None:
    from agenthub.agents.preview_agent import PreviewAgent

    class SchemaFailingAdapter:
        id = "real-preview"
        name = "Real Preview"
        capabilities = ["preview"]

        async def run(self, input_data: AgentRunInput) -> AgentRunResult:
            raise RealAgentSchemaError("bad preview schema")

    result = await PreviewAgent(SchemaFailingAdapter()).run(
        AgentRunInput(
            conversation_id="conv_001",
            workspace_id="ws_001",
            user_message="预览 Todo 页面",
            context={"preview_status": "ready", "preview_url": "http://127.0.0.1:18000"},
        )
    )

    assert result.agent_id == "preview-agent"
    assert result.artifacts[0].type == "preview"
    assert result.artifacts[0].data["status"] == "ready"
    assert "fallback" not in str(result.model_dump(mode="json")).lower()


def test_orchestrator_decision_normalizes_common_llm_plan_shape() -> None:
    decision = OrchestratorDecision.model_validate(
        {
            "mode": "plan",
            "content": "## 任务拆解",
            "plan": {
                "summary": "todo page",
                "tasks": [
                    {
                        "agent": "Code Agent",
                        "description": "实现 Todo List 网页并输出代码。",
                        "depends_on": "none",
                    },
                    {
                        "agent": "review",
                        "task": "检查实现风险。",
                        "depends_on": "code-agent",
                    },
                    {
                        "agent_name": "Preview Agent",
                        "objective": "验证预览是否可用。",
                        "depends_on": ["task_review"],
                    },
                ],
            },
        }
    )

    assert decision.plan is not None
    assert [task.agent_id for task in decision.plan.tasks] == [
        "code-agent",
        "review-agent",
        "preview-agent",
    ]
    assert [task.task_id for task in decision.plan.tasks] == [
        "task-code",
        "task-review",
        "task-preview",
    ]
    assert decision.plan.tasks[1].depends_on == ["task-code"]
    assert decision.plan.tasks[2].depends_on == ["task-review"]


def test_orchestrator_decision_accepts_top_level_tasks() -> None:
    decision = OrchestratorDecision.model_validate(
        {
            "content": "## 任务拆解",
            "tasks": [
                {
                    "agent": "Code Agent",
                    "task": "根据 context.user_request 实现页面并输出 code/diff。",
                    "depends_on": "none",
                }
            ],
        }
    )

    assert decision.mode == "plan"
    assert decision.plan is not None
    assert decision.plan.tasks[0].agent_id == "code-agent"
    assert decision.plan.tasks[0].task_id == "task-code"


@pytest.mark.asyncio
async def test_orchestrator_schema_failure_falls_back_to_executable_plan() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"mode":"plan","content":"bad"'}}]},
        )

    registry = AgentRegistry(
        [
            OrchestratorAdapter(
                RealAgent(
                    agent_id="orchestrator",
                    api_key="test-key",
                    http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
                )
            ),
            MockAgent(agent_id="code-agent"),
            MockAgent(agent_id="review-agent"),
            MockAgent(agent_id="preview-agent"),
        ]
    )
    service = AgentService(registry=registry)

    results = await service.run_for_message(
        AgentRunInput(
            conversation_id="conv_001",
            workspace_id="ws_001",
            user_message="@Orchestrator 帮我做一个简洁的 Todo List 网页",
        )
    )

    assert calls == 3
    assert [result.agent_id for result in results] == [
        "orchestrator",
        "code-agent",
        "review-agent",
        "preview-agent",
    ]
    assert "继续调用后续 Agent" in results[0].content
    assert "context.user_request" not in results[0].content
    assert "兜底" not in results[0].content
    assert "fallback" not in results[0].content.lower()
    assert "不符合结构要求" not in results[0].content


@pytest.mark.asyncio
async def test_orchestrator_schema_failure_falls_back_to_chat_for_greeting() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"mode":"chat","content":'}}]},
        )

    registry = AgentRegistry(
        [
            OrchestratorAdapter(
                RealAgent(
                    agent_id="orchestrator",
                    api_key="test-key",
                    http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
                )
            )
        ]
    )
    service = AgentService(registry=registry)

    results = await service.run_for_message(
        AgentRunInput(
            conversation_id="conv_001",
            workspace_id="ws_001",
            user_message="你好",
        )
    )

    assert calls == 3
    assert len(results) == 1
    assert results[0].agent_id == "orchestrator"
    assert "你好，我是 AgentHub Orchestrator" in results[0].content
    assert "Agent orchestrator failed" not in results[0].content
    assert "不符合结构要求" not in results[0].content


@pytest.mark.asyncio
async def test_orchestrator_schema_failure_recovers_with_relaxed_llm_plan() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls < 3:
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": '{"mode":"plan","content":"bad"'}}]},
            )
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                "## 任务拆解\n\n"
                                "1. code-agent - 实现学生成绩查询页面，包含姓名查询、"
                                "成绩范围查询和真实 DOM 更新。\n"
                                "2. review-agent - 审查查询逻辑、交互完整性和边界情况。\n"
                                "3. preview-agent - 验证应用 diff 后的 index.html "
                                "预览入口和可访问状态。"
                            )
                        }
                    }
                ]
            },
        )

    registry = AgentRegistry(
        [
            OrchestratorAdapter(
                RealAgent(
                    agent_id="orchestrator",
                    api_key="test-key",
                    http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
                )
            ),
            MockAgent(agent_id="code-agent"),
            MockAgent(agent_id="review-agent"),
            MockAgent(agent_id="preview-agent"),
        ]
    )
    service = AgentService(registry=registry)

    results = await service.run_for_message(
        AgentRunInput(
            conversation_id="conv_001",
            workspace_id="ws_001",
            user_message="@Orchestrator 帮我做一个学生成绩查询网页",
        )
    )

    assert calls == 3
    assert [result.agent_id for result in results] == [
        "orchestrator",
        "code-agent",
        "review-agent",
        "preview-agent",
    ]
    assert "学生成绩查询页面" in results[0].content
    assert "context.user_request" not in results[0].content
    assert "兜底" not in results[0].content


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
async def test_real_agent_normalizes_artifact_mapping_without_repair() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"agent_id":"code-agent","content":"Generated code",'
                                '"artifacts":{"html":"<main>ok</main>"},'
                                '"next_actions":[]}'
                            )
                        }
                    }
                ]
            },
        )

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

    assert calls == 1
    assert result.artifacts[0].type == "code"
    assert result.artifacts[0].data["filename"] == "index.html"
    assert result.artifacts[0].data["content"] == "<main>ok</main>"


@pytest.mark.asyncio
async def test_real_agent_normalizes_string_list_as_content() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '["交互完整。", "建议确认空输入提示。"]',
                        }
                    }
                ]
            },
        )

    agent = RealAgent(
        agent_id="review-agent",
        api_key="test-key",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    result = await agent.run(
        AgentRunInput(
            conversation_id="conv_001",
            workspace_id="ws_001",
            user_message="检查页面",
        )
    )

    assert result.agent_id == "review-agent"
    assert "交互完整" in result.content
    assert "建议确认空输入提示" in result.content


@pytest.mark.asyncio
async def test_real_agent_unwraps_nested_json_content_instead_of_showing_raw_json() -> None:
    inner = {
        "agent_id": "code-agent",
        "content": "## 添加查询功能\n\n已添加按姓名和成绩范围查询。",
        "artifacts": [
            {
                "id": "artifact-code",
                "type": "code",
                "title": "index.html",
                "data": {
                    "filename": "index.html",
                    "language": "html",
                    "content": '<main data-testid="search-app">ok</main>',
                },
            }
        ],
        "next_actions": [],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "agent_id": "code-agent",
                                    "content": json.dumps(inner, ensure_ascii=False),
                                    "artifacts": [],
                                    "next_actions": [],
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            },
        )

    agent = RealAgent(
        agent_id="code-agent",
        api_key="test-key",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    result = await agent.run(
        AgentRunInput(
            conversation_id="conv_001",
            workspace_id="ws_001",
            user_message="添加查询功能",
        )
    )

    assert result.content.startswith("## 添加查询功能")
    assert not result.content.lstrip().startswith("{")
    assert result.artifacts[0].type == "code"
    assert result.artifacts[0].data["filename"] == "index.html"


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
async def test_real_agent_extracts_json_object_from_wrapped_response() -> None:
    payload = {
        "choices": [
            {
                "message": {
                    "content": (
                        "Here is the result:\n"
                        '{"agent_id":"code-agent","content":"Generated code",'
                        '"files":[{"path":"todo.html","content":"<main>ok</main>"}]}'
                        "\nDone."
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

    assert result.content == "Generated code"
    assert result.artifacts[0].type == "code"
    assert result.artifacts[0].data["filename"] == "todo.html"
    assert result.artifacts[0].data["content"] == "<main>ok</main>"


@pytest.mark.asyncio
async def test_real_agent_normalizes_top_level_code_fields() -> None:
    payload = {
        "choices": [
            {
                "message": {
                    "content": (
                        '{"agent_id":"code-agent","summary":"Generated",'
                        '"filename":"index.html","code":"<main>ok</main>"}'
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

    assert result.content == "Generated"
    assert result.artifacts[0].type == "code"
    assert result.artifacts[0].data["filename"] == "index.html"
    assert result.artifacts[0].data["content"] == "<main>ok</main>"


@pytest.mark.asyncio
async def test_real_agent_keeps_markdown_with_css_braces_as_markdown() -> None:
    payload = {
        "choices": [
            {
                "message": {
                    "content": (
                        "已生成页面。\n\n"
                        '```html filename="index.html"\n'
                        "<style>body { color: red; }</style>\n"
                        "<main>ok</main>\n"
                        "```"
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

    assert result.content.startswith("已生成页面")
    assert result.artifacts[0].type == "code"
    assert result.artifacts[0].data["filename"] == "index.html"
    assert "body { color: red; }" in result.artifacts[0].data["content"]


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
async def test_real_agent_salvages_html_document_after_repair_failure() -> None:
    html = "<!doctype html><html><body><main>ok</main></body></html>"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                f'{{"agent_id":"code-agent","content":"Generated","html":"{html}"'
                            )
                        }
                    }
                ]
            },
        )

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
    assert result.artifacts[0].type == "code"
    assert result.artifacts[0].data["filename"] == "index.html"
    assert result.artifacts[0].data["content"] == html


@pytest.mark.asyncio
async def test_real_agent_salvages_broken_json_content_without_exposing_raw_json() -> None:
    broken_content = (
        "{\n"
        '  "agent_id": "code-agent",\n'
        '  "content": "## BMI 计算器\\n\\n'
        '```html filename=\\"index.html\\"\\n'
        '<!doctype html><html lang="zh-CN"><body><button id="calculate-bmi">'
        '计算</button></body></html>\\n```",\n'
        '  "artifacts": []\n'
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": broken_content}}]},
        )

    agent = RealAgent(
        agent_id="code-agent",
        api_key="test-key",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    result = await agent.run(
        AgentRunInput(
            conversation_id="conv_001",
            workspace_id="ws_001",
            user_message="生成 BMI 页面",
        )
    )

    assert not result.content.lstrip().startswith("{")
    assert '"agent_id"' not in result.content
    assert "## BMI 计算器" in result.content
    assert "```html" in result.content
    html_artifacts = [artifact for artifact in result.artifacts if artifact.type == "code"]
    assert html_artifacts
    assert html_artifacts[0].data["filename"] == "index.html"


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
async def test_code_agent_generates_diff_for_each_code_artifact() -> None:
    class MultiFileAdapter:
        id = "llm"
        name = "LLM"
        capabilities = ["llm"]

        async def run(self, input_data: AgentRunInput) -> object:
            from agenthub.schemas.agent import AgentRunResult
            from agenthub.schemas.artifact import Artifact

            return AgentRunResult(
                agent_id="code-agent",
                content="Generated split files",
                artifacts=[
                    Artifact(
                        id="artifact-html",
                        type="code",
                        title="index.html",
                        data={
                            "filename": "index.html",
                            "language": "html",
                            "content": '<link rel="stylesheet" href="style.css">\n',
                        },
                    ),
                    Artifact(
                        id="artifact-css",
                        type="code",
                        title="style.css",
                        data={
                            "filename": "style.css",
                            "language": "css",
                            "content": "body { color: #123; }",
                        },
                    ),
                    Artifact(
                        id="artifact-js",
                        type="code",
                        title="script.js",
                        data={
                            "filename": "script.js",
                            "language": "javascript",
                            "content": "console.log('ready')",
                        },
                    ),
                ],
                next_actions=[],
            )

    result = await CodeAgent(MultiFileAdapter()).run(
        AgentRunInput(
            conversation_id="conv_001",
            workspace_id="ws_001",
            user_message="生成 html css js 分开输出的页面",
        )
    )

    diff_artifacts = [artifact for artifact in result.artifacts if artifact.type == "diff"]
    assert [artifact.data["filename"] for artifact in diff_artifacts] == [
        "index.html",
        "style.css",
        "script.js",
    ]
    assert all(
        "\\ No newline at end of file" not in artifact.data["diff"] for artifact in diff_artifacts
    )


@pytest.mark.asyncio
async def test_code_agent_generates_missing_diffs_without_duplicating_existing_diff() -> None:
    class PartialDiffAdapter:
        id = "llm"
        name = "LLM"
        capabilities = ["llm"]

        async def run(self, input_data: AgentRunInput) -> object:
            from agenthub.schemas.agent import AgentRunResult
            from agenthub.schemas.artifact import Artifact

            return AgentRunResult(
                agent_id="code-agent",
                content="Generated split files",
                artifacts=[
                    Artifact(
                        id="artifact-html",
                        type="code",
                        title="index.html",
                        data={
                            "filename": "index.html",
                            "language": "html",
                            "content": "<main>ok</main>\n",
                        },
                    ),
                    Artifact(
                        id="artifact-css",
                        type="code",
                        title="style.css",
                        data={
                            "filename": "style.css",
                            "language": "css",
                            "content": "body { color: #123; }\n",
                        },
                    ),
                    Artifact(
                        id="artifact-html-diff",
                        type="diff",
                        title="index.html diff",
                        data={
                            "filename": "index.html",
                            "diff": (
                                "--- a/index.html\n"
                                "+++ b/index.html\n"
                                "@@ -0,0 +1 @@\n"
                                "+<main>ok</main>\n"
                            ),
                        },
                    ),
                ],
                next_actions=[],
            )

    result = await CodeAgent(PartialDiffAdapter()).run(
        AgentRunInput(
            conversation_id="conv_001",
            workspace_id="ws_001",
            user_message="生成 html css 分开输出的页面",
        )
    )

    diff_filenames = [
        artifact.data["filename"] for artifact in result.artifacts if artifact.type == "diff"
    ]
    assert diff_filenames == ["index.html", "style.css"]


@pytest.mark.asyncio
async def test_code_agent_multifile_diffs_use_existing_workspace_content(tmp_path) -> None:
    workspace_dir = tmp_path / "ws_001"
    workspace_dir.mkdir()
    (workspace_dir / "style.css").write_text("body { color: red; }\n", encoding="utf-8")

    class MultiFileAdapter:
        id = "llm"
        name = "LLM"
        capabilities = ["llm"]

        async def run(self, input_data: AgentRunInput) -> object:
            from agenthub.schemas.agent import AgentRunResult
            from agenthub.schemas.artifact import Artifact

            return AgentRunResult(
                agent_id="code-agent",
                content="Generated split files",
                artifacts=[
                    Artifact(
                        id="artifact-html",
                        type="code",
                        title="index.html",
                        data={
                            "filename": "index.html",
                            "language": "html",
                            "content": "<main>ok</main>\n",
                        },
                    ),
                    Artifact(
                        id="artifact-css",
                        type="code",
                        title="style.css",
                        data={
                            "filename": "style.css",
                            "language": "css",
                            "content": "body { color: green; }\n",
                        },
                    ),
                ],
                next_actions=[],
            )

    result = await CodeAgent(MultiFileAdapter(), workspace_root=tmp_path).run(
        AgentRunInput(
            conversation_id="conv_001",
            workspace_id="ws_001",
            user_message="生成 html css 分开输出的页面",
        )
    )

    css_diff = next(
        artifact.data["diff"]
        for artifact in result.artifacts
        if artifact.type == "diff" and artifact.data["filename"] == "style.css"
    )
    assert "-body { color: red; }" in css_diff
    assert "+body { color: green; }" in css_diff


@pytest.mark.asyncio
async def test_code_agent_diff_ids_change_when_diff_content_changes_for_same_filename() -> None:
    class CodeOnlyAdapter:
        id = "llm"
        name = "LLM"
        capabilities = ["llm"]

        def __init__(self, content: str) -> None:
            self._content = content

        async def run(self, input_data: AgentRunInput) -> object:
            from agenthub.schemas.agent import AgentRunResult
            from agenthub.schemas.artifact import Artifact

            return AgentRunResult(
                agent_id="code-agent",
                content="Generated code",
                artifacts=[
                    Artifact(
                        id="artifact-html",
                        type="code",
                        title="index.html",
                        data={
                            "filename": "index.html",
                            "language": "html",
                            "content": self._content,
                        },
                    )
                ],
                next_actions=[],
            )

    first_result = await CodeAgent(CodeOnlyAdapter("<main>first</main>\n")).run(
        AgentRunInput(
            conversation_id="conv_001",
            workspace_id="ws_001",
            user_message="生成页面",
        )
    )
    second_result = await CodeAgent(CodeOnlyAdapter("<main>second</main>\n")).run(
        AgentRunInput(
            conversation_id="conv_001",
            workspace_id="ws_001",
            user_message="生成页面",
        )
    )

    first_diff_id = next(
        artifact.id for artifact in first_result.artifacts if artifact.type == "diff"
    )
    second_diff_id = next(
        artifact.id for artifact in second_result.artifacts if artifact.type == "diff"
    )
    assert first_diff_id != second_diff_id


@pytest.mark.asyncio
async def test_code_agent_diff_ids_are_stable_for_same_filename_and_diff() -> None:
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
                        id="artifact-html",
                        type="code",
                        title="index.html",
                        data={
                            "filename": "index.html",
                            "language": "html",
                            "content": "<main>stable</main>\n",
                        },
                    )
                ],
                next_actions=[],
            )

    first_result = await CodeAgent(CodeOnlyAdapter()).run(
        AgentRunInput(
            conversation_id="conv_001",
            workspace_id="ws_001",
            user_message="生成页面",
        )
    )
    second_result = await CodeAgent(CodeOnlyAdapter()).run(
        AgentRunInput(
            conversation_id="conv_001",
            workspace_id="ws_001",
            user_message="生成页面",
        )
    )

    first_diff_id = next(
        artifact.id for artifact in first_result.artifacts if artifact.type == "diff"
    )
    second_diff_id = next(
        artifact.id for artifact in second_result.artifacts if artifact.type == "diff"
    )
    assert first_diff_id == second_diff_id
    assert first_diff_id.startswith("artifact-code-agent-diff-index-html-")


@pytest.mark.asyncio
async def test_code_agent_normalizes_model_supplied_diff_artifact_ids() -> None:
    class ModelDiffAdapter:
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
                        id="artifact-html",
                        type="code",
                        title="index.html",
                        data={
                            "filename": "index.html",
                            "language": "html",
                            "content": "<main>ok</main>\n",
                        },
                    ),
                    Artifact(
                        id="model-diff-1",
                        type="diff",
                        title="index.html diff",
                        data={
                            "filename": "index.html",
                            "diff": (
                                "--- a/index.html\n"
                                "+++ b/index.html\n"
                                "@@ -0,0 +1 @@\n"
                                "+<main>ok</main>\n"
                            ),
                        },
                    ),
                ],
                next_actions=[],
            )

    result = await CodeAgent(ModelDiffAdapter()).run(
        AgentRunInput(
            conversation_id="conv_001",
            workspace_id="ws_001",
            user_message="生成页面",
        )
    )

    diff_artifact = next(artifact for artifact in result.artifacts if artifact.type == "diff")
    assert diff_artifact.id != "model-diff-1"
    assert diff_artifact.id.startswith("artifact-code-agent-diff-index-html-")


@pytest.mark.asyncio
async def test_code_agent_preserves_source_artifact_id_when_rewriting_diff_id() -> None:
    class ModelDiffAdapter:
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
                        id="artifact-html",
                        type="code",
                        title="index.html",
                        data={
                            "filename": "index.html",
                            "language": "html",
                            "content": "<main>ok</main>\n",
                        },
                    ),
                    Artifact(
                        id="model-diff-1",
                        type="diff",
                        title="index.html diff",
                        data={
                            "filename": "index.html",
                            "diff": (
                                "--- a/index.html\n"
                                "+++ b/index.html\n"
                                "@@ -0,0 +1 @@\n"
                                "+<main>ok</main>\n"
                            ),
                        },
                    ),
                ],
                next_actions=[],
            )

    result = await CodeAgent(ModelDiffAdapter()).run(
        AgentRunInput(
            conversation_id="conv_001",
            workspace_id="ws_001",
            user_message="生成页面",
        )
    )

    diff_artifact = next(artifact for artifact in result.artifacts if artifact.type == "diff")
    assert diff_artifact.data["source_artifact_id"] == "model-diff-1"


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


@pytest.mark.asyncio
async def test_agent_service_schema_failure_message_does_not_blame_env() -> None:
    class SchemaFailingAdapter:
        id = "review-agent"
        name = "Review Agent"
        capabilities = ["review"]

        async def run(self, input_data: AgentRunInput) -> object:
            raise RealAgentSchemaError("模型连续返回了不符合 AgentRunResult 结构的内容。")

    service = AgentService(registry=AgentRegistry([SchemaFailingAdapter()]))

    results = await service.run_for_message(
        AgentRunInput(
            conversation_id="conv_001",
            workspace_id="ws_001",
            user_message="@ReviewAgent 检查代码",
        )
    )

    assert "不符合结构要求" in results[0].content
    assert ".env" not in results[0].content


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
