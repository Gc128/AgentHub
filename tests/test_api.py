import os

from fastapi.testclient import TestClient

from agenthub.api.deps import reset_dependency_caches
from agenthub.config import get_settings
from agenthub.main import app


def client() -> TestClient:
    os.environ["PERSISTENCE_BACKEND"] = "memory"
    os.environ["USE_MOCK_AGENTS"] = "true"
    get_settings.cache_clear()
    reset_dependency_caches()
    return TestClient(app)


def test_health() -> None:
    response = client().get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_conversation_and_send_orchestrated_message() -> None:
    test_client = client()
    create_response = test_client.post(
        "/api/conversations",
        json={
            "title": "Todo App",
            "agent_ids": ["orchestrator", "code-agent", "review-agent", "preview-agent"],
        },
    )
    assert create_response.status_code == 201
    conversation = create_response.json()

    message_response = test_client.post(
        f"/api/conversations/{conversation['id']}/messages",
        json={"content": "@Orchestrator 帮我做一个 Todo List 网页", "sender_id": "user"},
    )
    assert message_response.status_code == 201
    message = message_response.json()
    assert message["role"] == "user"
    assert message["sender_id"] == "user"

    history_response = test_client.get(f"/api/conversations/{conversation['id']}/messages")
    assert history_response.status_code == 200
    assert len(history_response.json()) == 1


def test_message_run_endpoint_runs_full_orchestrator_pipeline() -> None:
    test_client = client()
    create_response = test_client.post(
        "/api/conversations",
        json={
            "title": "Todo App",
            "agent_ids": ["orchestrator", "code-agent", "review-agent", "preview-agent"],
        },
    )
    conversation = create_response.json()

    response = test_client.post(
        f"/api/conversations/{conversation['id']}/messages/run",
        json={"content": "@Orchestrator 帮我做一个 Todo List 网页"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["user_message"]["role"] == "user"
    assert [message["sender_id"] for message in payload["agent_messages"]] == [
        "orchestrator",
        "code-agent",
        "review-agent",
        "preview-agent",
    ]
    assert payload["agent_messages"][0]["artifacts"] == []
    assert payload["agent_messages"][1]["artifacts"][0]["type"] == "code"
    assert payload["agent_messages"][1]["artifacts"][1]["type"] == "diff"
    assert payload["agent_messages"][2]["artifacts"][0]["type"] == "file"
    assert payload["agent_messages"][3]["artifacts"][0]["type"] == "preview"

    history_response = test_client.get(f"/api/conversations/{conversation['id']}/messages")
    assert history_response.status_code == 200
    assert [message["sender_id"] for message in history_response.json()] == [
        "user",
        "orchestrator",
        "code-agent",
        "review-agent",
        "preview-agent",
    ]


def test_direct_agent_message_runs_only_target_agent() -> None:
    test_client = client()
    create_response = test_client.post(
        "/api/conversations",
        json={
            "title": "Review",
            "agent_ids": ["orchestrator", "code-agent", "review-agent", "preview-agent"],
        },
    )
    conversation = create_response.json()

    response = test_client.post(
        f"/api/conversations/{conversation['id']}/messages/run",
        json={"content": "@ReviewAgent 检查这段代码有没有 bug"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert [message["sender_id"] for message in payload["agent_messages"]] == ["review-agent"]
    assert payload["agent_messages"][0]["artifacts"][0]["type"] == "file"


def test_message_without_agent_mention_gets_default_chat_response() -> None:
    test_client = client()
    create_response = test_client.post(
        "/api/conversations",
        json={
            "title": "Plain Chat",
            "agent_ids": ["orchestrator", "code-agent", "review-agent", "preview-agent"],
        },
    )
    conversation = create_response.json()

    response = test_client.post(
        f"/api/conversations/{conversation['id']}/messages/run",
        json={"content": "先记录一下需求，暂时不要调用任何人"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["user_message"]["sender_id"] == "user"
    assert [message["sender_id"] for message in payload["agent_messages"]] == ["orchestrator"]
    assert "我已收到" in payload["agent_messages"][0]["content"]

    history_response = test_client.get(f"/api/conversations/{conversation['id']}/messages")
    assert [message["sender_id"] for message in history_response.json()] == [
        "user",
        "orchestrator",
    ]


def test_message_without_agent_mention_can_auto_plan_development_request() -> None:
    test_client = client()
    create_response = test_client.post(
        "/api/conversations",
        json={
            "title": "Auto Plan",
            "agent_ids": ["orchestrator", "code-agent", "review-agent", "preview-agent"],
        },
    )
    conversation = create_response.json()

    response = test_client.post(
        f"/api/conversations/{conversation['id']}/messages/run",
        json={"content": "帮我实现一个 Todo 页面"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert [message["sender_id"] for message in payload["agent_messages"][:4]] == [
        "orchestrator",
        "code-agent",
        "review-agent",
        "preview-agent",
    ]


def test_agent_failure_returns_chat_message_instead_of_502(monkeypatch) -> None:
    monkeypatch.setenv("PERSISTENCE_BACKEND", "memory")
    monkeypatch.setenv("USE_MOCK_AGENTS", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()
    reset_dependency_caches()
    test_client = TestClient(app)
    create_response = test_client.post(
        "/api/conversations",
        json={"title": "Real Agent", "agent_ids": ["code-agent"]},
    )
    conversation = create_response.json()

    response = test_client.post(
        f"/api/conversations/{conversation['id']}/messages/run",
        json={"content": "@CodeAgent 实现一个页面"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["user_message"]["sender_id"] == "user"
    assert [message["sender_id"] for message in payload["agent_messages"]] == ["code-agent"]
    assert "Agent code-agent failed" in payload["agent_messages"][0]["content"]


def test_agent_run_orchestrator_returns_plan_without_child_artifacts() -> None:
    response = client().post(
        "/api/agents/run",
        json={
            "conversation_id": "conv_001",
            "workspace_id": "ws_001",
            "user_message": "@Orchestrator 帮我做一个 Todo List 网页",
            "history": [],
            "context": {"agent_id": "orchestrator"},
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["agent_id"] == "orchestrator"
    assert result["next_actions"] == ["code-agent", "review-agent", "preview-agent"]
    assert result["artifacts"] == []
    assert "@Orchestrator 帮我做一个 Todo List 网页" not in result["content"]
    assert "Code Agent" not in result["content"]
    assert "code-agent" in result["content"]


def test_agent_runtime_reports_mock_mode_without_secret() -> None:
    response = client().get("/api/agents/runtime")

    assert response.status_code == 200
    payload = response.json()
    assert payload["agent_mode"] == "mock"
    assert payload["provider"]
    assert "api_key" not in payload
    assert "secret" not in str(payload).lower()


def test_update_and_delete_conversation_match_frontend_contract() -> None:
    test_client = client()
    create_response = test_client.post(
        "/api/conversations",
        json={"title": "Review", "agent_ids": ["review-agent"], "is_pinned": False},
    )
    conversation = create_response.json()

    patch_response = test_client.patch(
        f"/api/conversations/{conversation['id']}",
        json={
            "title": "Pinned Review",
            "mode": "single",
            "agent_ids": ["review-agent"],
            "is_pinned": True,
        },
    )

    assert patch_response.status_code == 200
    updated = patch_response.json()
    assert updated["title"] == "Pinned Review"
    assert updated["mode"] == "single"
    assert updated["agent_ids"] == ["review-agent"]
    assert updated["is_pinned"] is True

    delete_response = test_client.delete(f"/api/conversations/{conversation['id']}")
    assert delete_response.status_code == 200
    assert delete_response.json() == {"id": conversation["id"], "deleted": True}

    missing_response = test_client.get(f"/api/conversations/{conversation['id']}")
    assert missing_response.status_code == 404


def test_missing_conversation_returns_error() -> None:
    response = client().get("/api/conversations/missing/messages")
    assert response.status_code == 404
    assert response.json()["code"] == "conversation_not_found"


def test_agents_stream_returns_sse_events() -> None:
    test_client = client()
    with test_client.stream(
        "POST",
        "/api/agents/stream",
        json={
            "conversation_id": "conv_001",
            "workspace_id": "ws_001",
            "user_message": "@CodeAgent 实现页面",
        },
    ) as response:
        body = "".join(response.iter_text())
    assert response.status_code == 200
    assert "event: agent_started" in body
    assert "event: agent_delta" in body
    assert "event: done" in body


def test_message_stream_persists_user_and_agent_messages() -> None:
    test_client = client()
    create_response = test_client.post(
        "/api/conversations",
        json={
            "title": "Stream",
            "agent_ids": ["orchestrator", "code-agent", "review-agent", "preview-agent"],
        },
    )
    conversation = create_response.json()

    with test_client.stream(
        "POST",
        f"/api/conversations/{conversation['id']}/messages/stream",
        json={"content": "@Orchestrator 帮我做一个 Todo List 网页"},
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert body.index("event: user_message") < body.index("event: harness_step")
    assert "event: agent_started" in body
    assert "event: agent_delta" in body
    assert body.count("event: agent_delta") > 3
    assert "event: agent_done" in body
    assert "event: done" in body
    assert '"agent_messages"' in body

    history_response = test_client.get(f"/api/conversations/{conversation['id']}/messages")
    assert history_response.status_code == 200
    assert [message["sender_id"] for message in history_response.json()] == [
        "user",
        "orchestrator",
        "code-agent",
        "review-agent",
        "preview-agent",
    ]
