from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from flask.testing import FlaskClient

from frontend.flask import main as flask_main


@pytest.fixture()
def flask_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[FlaskClient]:
    table_paths = {
        flask_main.previews_table: "previews",
        flask_main.applied_diffs_table: "applied_diffs",
        flask_main.workspace_files_table: "workspace_files",
    }
    for table, name in table_paths.items():
        monkeypatch.setattr(table, "path", tmp_path / f"{name}.json")

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
    response = flask_client.post(
        "/api/workspaces/ws_demo/apply-diff",
        json={
            "artifact_id": "artifact_diff_new",
            "diff": "--- a/src/App.tsx\n+++ b/src/App.tsx\n@@\n-old\n+new\n",
        },
    )

    assert response.status_code == 200
    data = envelope(response.get_json())
    assert data["workspace_id"] == "ws_demo"
    assert data["status"] == "ready"
    assert data["applied_artifact_id"] == "artifact_diff_new"

    history_response = flask_client.get("/api/workspaces/ws_demo/applied-diffs")
    history = envelope(history_response.get_json())
    assert [row["artifact_id"] for row in history] == [
        "artifact_diff_existing",
        "artifact_diff_new",
    ]

    preview_response = flask_client.get("/api/workspaces/ws_demo/preview")
    preview = envelope(preview_response.get_json())
    assert preview["status"] == "ready"
    assert preview["preview_url"] == "https://preview.example/ws_demo"
