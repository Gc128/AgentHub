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


def test_custom_agent_crud_test_and_direct_run() -> None:
    test_client = client()

    create_response = test_client.post(
        "/api/agents/custom",
        json={
            "name": "需求澄清 Agent",
            "description": "帮助用户澄清需求",
            "system_prompt": "你专门负责提出需求澄清问题。",
            "capabilities": ["clarify", "product"],
            "is_enabled": True,
        },
    )

    assert create_response.status_code == 201
    custom_agent = create_response.json()
    assert custom_agent["id"].startswith("custom-agent")
    assert custom_agent["system_prompt"] == "你专门负责提出需求澄清问题。"

    custom_list = test_client.get("/api/agents/custom").json()
    assert [agent["id"] for agent in custom_list] == [custom_agent["id"]]

    visible_agents = test_client.get("/api/agents").json()
    assert custom_agent["id"] in {agent["id"] for agent in visible_agents}

    test_response = test_client.post(
        f"/api/agents/custom/{custom_agent['id']}/test",
        json={"message": "帮我确认需求"},
    )
    assert test_response.status_code == 200
    test_result = test_response.json()
    assert test_result["agent_id"] == custom_agent["id"]
    assert "你专门负责提出需求澄清问题" in test_result["content"]

    run_response = test_client.post(
        "/api/agents/run",
        json={
            "conversation_id": "conv_custom",
            "workspace_id": "ws_custom",
            "user_message": "@需求澄清Agent 帮我确认需求",
            "history": [],
            "context": {},
        },
    )
    assert run_response.status_code == 200
    assert run_response.json()["agent_id"] == custom_agent["id"]

    update_response = test_client.patch(
        f"/api/agents/custom/{custom_agent['id']}",
        json={
            "system_prompt": "你现在负责输出三条问题。",
            "is_enabled": False,
        },
    )
    assert update_response.status_code == 200
    updated_agent = update_response.json()
    assert updated_agent["system_prompt"] == "你现在负责输出三条问题。"
    assert updated_agent["is_enabled"] is False

    hidden_agents = test_client.get("/api/agents").json()
    assert custom_agent["id"] not in {agent["id"] for agent in hidden_agents}

    delete_response = test_client.delete(f"/api/agents/custom/{custom_agent['id']}")
    assert delete_response.status_code == 200
    assert delete_response.json() == {"id": custom_agent["id"], "deleted": True}

    missing_run_response = test_client.post(
        "/api/agents/run",
        json={
            "conversation_id": "conv_custom",
            "workspace_id": "ws_custom",
            "user_message": "hello",
            "history": [],
            "context": {"agent_id": custom_agent["id"]},
        },
    )
    assert missing_run_response.status_code == 404
    assert missing_run_response.json()["code"] == "agent_not_found"


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


def test_conversation_archive_filter_defaults_to_active() -> None:
    test_client = client()
    active_response = test_client.post(
        "/api/conversations",
        json={"title": "Active", "agent_ids": ["orchestrator"]},
    )
    archived_response = test_client.post(
        "/api/conversations",
        json={"title": "Archived", "agent_ids": ["orchestrator"]},
    )
    active_conversation = active_response.json()
    archived_conversation = archived_response.json()

    patch_response = test_client.patch(
        f"/api/conversations/{archived_conversation['id']}",
        json={"status": "archived"},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["status"] == "archived"

    default_list = test_client.get("/api/conversations").json()
    archived_list = test_client.get("/api/conversations?status=archived").json()
    all_list = test_client.get("/api/conversations?status=all").json()

    assert [conversation["id"] for conversation in default_list] == [active_conversation["id"]]
    assert [conversation["id"] for conversation in archived_list] == [archived_conversation["id"]]
    assert {conversation["id"] for conversation in all_list} == {
        active_conversation["id"],
        archived_conversation["id"],
    }

    restore_response = test_client.patch(
        f"/api/conversations/{archived_conversation['id']}",
        json={"status": "active"},
    )
    assert restore_response.status_code == 200
    assert restore_response.json()["status"] == "active"
    assert len(test_client.get("/api/conversations").json()) == 2


def test_message_reply_soft_delete_and_pin_context() -> None:
    test_client = client()
    create_response = test_client.post(
        "/api/conversations",
        json={"title": "IM", "agent_ids": ["orchestrator"]},
    )
    conversation = create_response.json()

    first_response = test_client.post(
        f"/api/conversations/{conversation['id']}/messages",
        json={"content": "第一条", "sender_id": "user"},
    )
    first_message = first_response.json()
    reply_response = test_client.post(
        f"/api/conversations/{conversation['id']}/messages",
        json={
            "content": "回复第一条",
            "sender_id": "user",
            "reply_to_id": first_message["id"],
        },
    )
    reply_message = reply_response.json()

    assert reply_message["reply_to_id"] == first_message["id"]
    assert reply_message["is_context_pinned"] is False
    assert reply_message["deleted_at"] is None

    pin_response = test_client.post(
        f"/api/conversations/{conversation['id']}/messages/{reply_message['id']}/pin-context"
    )
    assert pin_response.status_code == 200
    assert pin_response.json()["is_context_pinned"] is True

    unpin_response = test_client.delete(
        f"/api/conversations/{conversation['id']}/messages/{reply_message['id']}/pin-context"
    )
    assert unpin_response.status_code == 200
    assert unpin_response.json()["is_context_pinned"] is False

    artifact_message_response = test_client.post(
        f"/api/conversations/{conversation['id']}/messages",
        json={
            "content": "带产物",
            "sender_id": "code-agent",
            "artifacts": [
                {
                    "id": "artifact_delete_test",
                    "type": "code",
                    "title": "demo",
                    "data": {"content": "<html></html>"},
                }
            ],
        },
    )
    artifact_message = artifact_message_response.json()
    delete_response = test_client.delete(
        f"/api/conversations/{conversation['id']}/messages/{artifact_message['id']}"
    )

    assert delete_response.status_code == 200
    deleted_message = delete_response.json()
    assert deleted_message["deleted_at"] is not None
    assert deleted_message["artifacts"] == []
    assert deleted_message["content"] == "消息已删除"

    history_response = test_client.get(f"/api/conversations/{conversation['id']}/messages")
    assert [message["id"] for message in history_response.json()] == [
        first_message["id"],
        reply_message["id"],
        artifact_message["id"],
    ]


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


def test_regenerate_stream_reuses_user_message_without_duplication() -> None:
    test_client = client()
    create_response = test_client.post(
        "/api/conversations",
        json={"title": "Regenerate", "agent_ids": ["code-agent"]},
    )
    conversation = create_response.json()
    message_response = test_client.post(
        f"/api/conversations/{conversation['id']}/messages",
        json={"content": "@CodeAgent 做一个按钮", "sender_id": "user"},
    )
    user_message = message_response.json()

    with test_client.stream(
        "POST",
        f"/api/conversations/{conversation['id']}/messages/{user_message['id']}/regenerate/stream",
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "event: user_message" not in body
    assert "event: agent_started" in body
    assert "event: agent_done" in body
    assert "event: done" in body

    history_response = test_client.get(f"/api/conversations/{conversation['id']}/messages")
    messages = history_response.json()
    assert [message["sender_id"] for message in messages] == ["user", "code-agent"]
    assert messages[1]["regenerated_from_id"] == user_message["id"]
