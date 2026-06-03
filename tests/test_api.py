from fastapi.testclient import TestClient

from agenthub.api.deps import reset_dependency_caches
from agenthub.main import app


def client() -> TestClient:
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
        json={"title": "Todo App", "agent_ids": ["orchestrator"]},
    )
    assert create_response.status_code == 201
    conversation = create_response.json()

    message_response = test_client.post(
        f"/api/conversations/{conversation['id']}/messages",
        json={"content": "@Orchestrator 帮我做一个 Todo List 网页"},
    )
    assert message_response.status_code == 201
    payload = message_response.json()
    assert payload["user_message"]["role"] == "user"
    assert payload["agent_messages"][0]["sender_id"] == "orchestrator"
    artifact_types = {artifact["type"] for artifact in payload["agent_messages"][0]["artifacts"]}
    assert {"code", "diff", "preview"}.issubset(artifact_types)

    history_response = test_client.get(f"/api/conversations/{conversation['id']}/messages")
    assert history_response.status_code == 200
    assert len(history_response.json()) == 2


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
    assert "event: status" in body
    assert "event: done" in body
    assert "Code Agent 正在生成代码" in body
