from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from flask.testing import FlaskClient

from agenthub.workspace.diff import create_unified_diff
from frontend.flask import main as flask_main


@pytest.fixture()
def flask_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[FlaskClient]:
    table_paths = {
        flask_main.conversations_table: "conversations",
        flask_main.messages_table: "messages",
        flask_main.previews_table: "previews",
        flask_main.applied_diffs_table: "applied_diffs",
        flask_main.workspace_files_table: "workspace_files",
    }
    for table, name in table_paths.items():
        monkeypatch.setattr(table, "path", tmp_path / f"{name}.json")

    flask_main.write_json(
        flask_main.conversations_table.path,
        [
            {
                "id": "conv_demo",
                "title": "Demo Conversation",
                "mode": "group",
                "agent_ids": [
                    "orchestrator",
                    "code-agent",
                    "review-agent",
                    "preview-agent",
                ],
                "is_pinned": False,
                "workspace_id": "ws_demo",
                "created_at": "2026-06-03T09:00:00Z",
                "updated_at": "2026-06-03T09:00:00Z",
            }
        ],
    )
    flask_main.write_json(flask_main.messages_table.path, [])
    flask_main.write_json(
        flask_main.previews_table.path,
        [
            {
                "workspace_id": "ws_demo",
                "status": "running",
                "preview_url": "https://preview.example/ws_demo",
            }
        ],
    )
    flask_main.write_json(
        flask_main.applied_diffs_table.path,
        [
            {
                "id": "apply_existing",
                "workspace_id": "ws_demo",
                "artifact_id": "artifact_diff_existing",
                "diff": "--- a/src/App.tsx\n+++ b/src/App.tsx\n",
                "applied_at": "2026-06-03T09:00:00Z",
            }
        ],
    )
    flask_main.write_json(
        flask_main.workspace_files_table.path,
        [
            {
                "workspace_id": "ws_demo",
                "path": "src/App.tsx",
                "content": "export default function App() { return null }\n",
                "updated_at": "2026-06-03T09:00:00Z",
            }
        ],
    )

    flask_main.app.config.update(TESTING=True)
    with flask_main.app.test_client() as client:
        yield client


def envelope(response_data: dict[str, Any]) -> Any:
    assert response_data["success"] is True
    assert response_data["error"] is None
    return response_data["data"]


def test_workspace_preview_includes_preview_url(flask_client: FlaskClient) -> None:
    response = flask_client.get("/api/workspaces/ws_demo/preview")

    assert response.status_code == 200
    data = envelope(response.get_json())
    assert data == {
        "workspace_id": "ws_demo",
        "status": "running",
        "preview_url": "https://preview.example/ws_demo",
    }


def test_workspace_applied_diffs_returns_workspace_history(flask_client: FlaskClient) -> None:
    response = flask_client.get("/api/workspaces/ws_demo/applied-diffs")

    assert response.status_code == 200
    data = envelope(response.get_json())
    assert data == [
        {
            "id": "apply_existing",
            "workspace_id": "ws_demo",
            "artifact_id": "artifact_diff_existing",
            "diff": "--- a/src/App.tsx\n+++ b/src/App.tsx\n",
            "applied_at": "2026-06-03T09:00:00Z",
        }
    ]


def test_apply_diff_appends_history_and_preserves_preview_url(
    flask_client: FlaskClient,
) -> None:
    diff = create_unified_diff(
        "export default function App() { return null }\n",
        "export default function App() { return <main>new</main> }\n",
        "src/App.tsx",
    )

    response = flask_client.post(
        "/api/workspaces/ws_demo/apply-diff",
        json={
            "artifact_id": "artifact_diff_new",
            "diff": diff,
        },
    )

    assert response.status_code == 200
    data = envelope(response.get_json())
    assert data["workspace_id"] == "ws_demo"
    assert data["status"] == "ready"
    assert data["applied_artifact_id"] == "artifact_diff_new"
    assert data["path"] == "src/App.tsx"

    history_response = flask_client.get("/api/workspaces/ws_demo/applied-diffs")
    history = envelope(history_response.get_json())
    assert [row["artifact_id"] for row in history] == [
        "artifact_diff_existing",
        "artifact_diff_new",
    ]
    assert history[-1]["path"] == "src/App.tsx"

    file_response = flask_client.get(
        "/api/workspaces/ws_demo/files/content",
        query_string={"path": "src/App.tsx"},
    )
    file_record = envelope(file_response.get_json())
    assert file_record["content"] == "export default function App() { return <main>new</main> }\n"

    preview_response = flask_client.get("/api/workspaces/ws_demo/preview")
    preview = envelope(preview_response.get_json())
    assert preview["status"] == "ready"
    assert preview["preview_url"] == "https://preview.example/ws_demo"


def test_apply_diff_preserves_missing_trailing_newline(
    flask_client: FlaskClient,
) -> None:
    create_response = flask_client.post(
        "/api/workspaces/ws_demo/files",
        json={"path": "src/no-newline.ts", "content": "old"},
    )
    assert create_response.status_code == 201
    diff = create_unified_diff("old", "new", "src/no-newline.ts")

    response = flask_client.post(
        "/api/workspaces/ws_demo/apply-diff",
        json={"artifact_id": "artifact_diff_no_newline", "diff": diff},
    )

    assert response.status_code == 200
    data = envelope(response.get_json())
    assert data["path"] == "src/no-newline.ts"

    file_response = flask_client.get(
        "/api/workspaces/ws_demo/files/content",
        query_string={"path": "src/no-newline.ts"},
    )
    file_record = envelope(file_response.get_json())
    assert file_record["content"] == "new"


def test_code_artifact_generates_pending_diff_without_writing_workspace_file(
    flask_client: FlaskClient,
) -> None:
    response = flask_client.post(
        "/api/conversations/conv_demo/messages",
        json={
            "sender_id": "code-agent",
            "content": "Code Agent generated a component.",
            "artifacts": [
                {
                    "id": "artifact_code_pending",
                    "type": "code",
                    "title": "Pending Component",
                    "data": {
                        "filename": "src/App.tsx",
                        "language": "tsx",
                        "content": (
                            "export default function App() { return <main>pending</main> }\n"
                        ),
                    },
                }
            ],
        },
    )

    assert response.status_code == 201
    message = envelope(response.get_json())
    artifact_types = [artifact["type"] for artifact in message["artifacts"]]
    assert artifact_types == ["code", "diff"]
    diff_artifact = message["artifacts"][1]
    assert diff_artifact["data"]["filename"] == "src/App.tsx"
    assert diff_artifact["data"]["source_artifact_id"] == "artifact_code_pending"
    assert "-export default function App() { return null }\n" in diff_artifact["data"]["diff"]
    assert (
        "+export default function App() { return <main>pending</main> }\n"
        in diff_artifact["data"]["diff"]
    )

    file_response = flask_client.get(
        "/api/workspaces/ws_demo/files/content",
        query_string={"path": "src/App.tsx"},
    )
    file_record = envelope(file_response.get_json())
    assert file_record["content"] == "export default function App() { return null }\n"


def test_orchestrator_result_contains_structured_plan_artifact(
    flask_client: FlaskClient,
) -> None:
    response = flask_client.post(
        "/api/agents/run",
        json={
            "conversation_id": "conv_demo",
            "workspace_id": "ws_demo",
            "user_message": "@Orchestrator 请组织开发 Todo 页面",
            "history": [],
            "context": {"agent_id": "orchestrator"},
        },
    )

    assert response.status_code == 200
    result = envelope(response.get_json())
    assert result["agent_id"] == "orchestrator"
    assert result["next_actions"] == ["code-agent", "review-agent"]

    artifact = result["artifacts"][0]
    assert artifact["type"] == "file"
    assert artifact["title"] == "Task Breakdown"
    assert artifact["data"]["steps"] == [
        "Code Agent 生成页面代码",
        "Review Agent 检查实现风险",
    ]
    assert [task["agent_id"] for task in artifact["data"]["tasks"]] == [
        "code-agent",
        "review-agent",
    ]
