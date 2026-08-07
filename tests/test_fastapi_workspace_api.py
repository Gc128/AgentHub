import os

import pytest
from fastapi import BackgroundTasks
from fastapi.testclient import TestClient

from agenthub.api.deps import reset_dependency_caches
from agenthub.api.workspaces import re_review_change_set, reapply_change_set
from agenthub.config import get_settings
from agenthub.main import app
from agenthub.schemas.change_set import ChangeSet
from agenthub.workspace.diff import create_unified_diff


def client() -> TestClient:
    os.environ["PERSISTENCE_BACKEND"] = "memory"
    os.environ["USE_MOCK_AGENTS"] = "true"
    # Legacy endpoint coverage is explicit; production defaults keep it disabled.
    os.environ["LEGACY_APPLY_DIFF_ENABLED"] = "true"
    get_settings.cache_clear()
    reset_dependency_caches()
    return TestClient(app)


@pytest.mark.asyncio
async def test_reapply_returns_candidate_before_background_validation() -> None:
    candidate = ChangeSet(
        id="changeset-reapply-candidate",
        conversation_id="conv-reapply",
        workspace_id="ws-reapply",
        parent_change_set_id="changeset-original",
        status="validating",
        base_snapshot_sha256="base-hash",
    )

    class ReapplyService:
        async def prepare_reapply(self, workspace_id: str, change_set_id: str) -> ChangeSet:
            assert workspace_id == "ws-reapply"
            assert change_set_id == "changeset-original"
            return candidate

    class ReapplyAgentService:
        calls = 0

        async def validate_existing_change_set(
            self,
            input_data: object,
            change_set_id: str,
        ) -> list[object]:
            del input_data
            assert change_set_id == candidate.id
            self.calls += 1
            return []

    background_tasks = BackgroundTasks()
    agent_service = ReapplyAgentService()
    response = await reapply_change_set(
        "ws-reapply",
        "changeset-original",
        background_tasks,
        ReapplyService(),  # type: ignore[arg-type]
        agent_service,  # type: ignore[arg-type]
    )

    assert response.change_set.id == candidate.id
    assert response.change_set.status == "validating"
    assert agent_service.calls == 0
    await background_tasks()
    assert agent_service.calls == 1


@pytest.mark.asyncio
async def test_re_review_returns_child_before_background_review() -> None:
    candidate = ChangeSet(
        id="changeset-rereview-candidate",
        conversation_id="conv-rereview",
        workspace_id="ws-rereview",
        parent_change_set_id="changeset-failed",
        status="validating",
        base_snapshot_sha256="base-hash",
    )

    class ReReviewService:
        async def prepare_re_review(self, workspace_id: str, change_set_id: str) -> ChangeSet:
            assert workspace_id == "ws-rereview"
            assert change_set_id == "changeset-failed"
            return candidate

    class ReReviewAgentService:
        calls = 0

        async def validate_existing_change_set(
            self,
            input_data: object,
            change_set_id: str,
        ) -> list[object]:
            del input_data
            assert change_set_id == candidate.id
            self.calls += 1
            return []

    background_tasks = BackgroundTasks()
    agent_service = ReReviewAgentService()
    response = await re_review_change_set(
        "ws-rereview",
        "changeset-failed",
        background_tasks,
        ReReviewService(),  # type: ignore[arg-type]
        agent_service,  # type: ignore[arg-type]
    )

    assert response.change_set.id == candidate.id
    assert response.change_set.parent_change_set_id == "changeset-failed"
    assert agent_service.calls == 0
    await background_tasks()
    assert agent_service.calls == 1


def test_workspace_preview_uses_preview_url_field() -> None:
    response = client().get("/api/workspaces/ws_demo/preview")

    assert response.status_code == 200
    assert response.json() == {
        "workspace_id": "ws_demo",
        "status": "not_started",
        "preview_url": None,
        "entry_path": None,
    }


def test_legacy_apply_diff_is_disabled_without_explicit_opt_in(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    test_client = client()
    monkeypatch.setenv("LEGACY_APPLY_DIFF_ENABLED", "false")
    get_settings.cache_clear()

    response = test_client.post(
        "/api/workspaces/ws_legacy_disabled/apply-diff",
        json={"artifact_id": "legacy", "diff": "not used"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "legacy_apply_diff_disabled"
    assert not (tmp_path / "ws_legacy_disabled").exists()


def test_workspace_file_write_list_read_and_apply_diff_flow(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    test_client = client()

    create_response = test_client.post(
        "/api/workspaces/ws_demo/files",
        json={
            "path": "src/App.tsx",
            "content": "export default function App() { return null }\n",
        },
    )
    assert create_response.status_code == 201

    list_response = test_client.get("/api/workspaces/ws_demo/files")
    assert list_response.status_code == 200
    assert list_response.json() == [
        {"path": "src/App.tsx", "updated_at": create_response.json()["updated_at"]}
    ]

    diff = create_unified_diff(
        "export default function App() { return null }\n",
        "export default function App() { return <main>ready</main> }\n",
        "src/App.tsx",
    )
    apply_response = test_client.post(
        "/api/workspaces/ws_demo/apply-diff",
        json={"artifact_id": "artifact_diff_demo", "diff": diff},
    )

    assert apply_response.status_code == 200
    applied = apply_response.json()
    assert applied["workspace_id"] == "ws_demo"
    assert applied["status"] == "ready"
    assert applied["applied_artifact_id"] == "artifact_diff_demo"
    assert applied["path"] == "src/App.tsx"

    file_response = test_client.get(
        "/api/workspaces/ws_demo/files/content",
        params={"path": "src/App.tsx"},
    )
    assert file_response.status_code == 200
    assert (
        file_response.json()["content"]
        == "export default function App() { return <main>ready</main> }\n"
    )

    history_response = test_client.get("/api/workspaces/ws_demo/applied-diffs")
    assert history_response.status_code == 200
    history = history_response.json()
    assert len(history) == 1
    assert history[0]["artifact_id"] == "artifact_diff_demo"
    assert history[0]["path"] == "src/App.tsx"

    preview_response = test_client.get("/api/workspaces/ws_demo/preview")
    assert preview_response.status_code == 200
    preview = preview_response.json()
    assert preview["status"] == "ready"
    assert preview["preview_url"].endswith("/api/workspaces/ws_demo/preview-page")
    assert preview["entry_path"] is None


def test_workspace_file_content_reads_real_workspace_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    workspace_dir = tmp_path / "ws_real_file"
    workspace_dir.mkdir()
    (workspace_dir / "script.js").write_text("console.log('disk')\n", encoding="utf-8")
    test_client = client()

    response = test_client.get(
        "/api/workspaces/ws_real_file/files/content",
        params={"path": "script.js"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["workspace_id"] == "ws_real_file"
    assert payload["path"] == "script.js"
    assert payload["content"] == "console.log('disk')\n"


def test_workspace_delete_file_removes_real_file_and_metadata(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    test_client = client()
    create_response = test_client.post(
        "/api/workspaces/ws_delete/files",
        json={"path": "index.html", "content": "<main>delete me</main>\n"},
    )
    assert create_response.status_code == 201
    target_file = tmp_path / "ws_delete" / "index.html"
    assert target_file.exists()

    delete_response = test_client.delete(
        "/api/workspaces/ws_delete/files",
        params={"path": "index.html"},
    )

    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] is True
    assert delete_response.json()["path"] == "index.html"
    assert not target_file.exists()
    list_response = test_client.get("/api/workspaces/ws_delete/files")
    assert list_response.status_code == 200
    assert list_response.json() == []
    content_response = test_client.get(
        "/api/workspaces/ws_delete/files/content",
        params={"path": "index.html"},
    )
    assert content_response.status_code == 404


def test_workspace_delete_missing_file_returns_readable_error(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    test_client = client()

    response = test_client.delete(
        "/api/workspaces/ws_delete_missing/files",
        params={"path": "missing.html"},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "workspace_file_not_found"
    assert "missing.html" in response.json()["message"]


def test_workspace_delete_rejects_path_traversal(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    test_client = client()

    response = test_client.delete(
        "/api/workspaces/ws_delete_escape/files",
        params={"path": "../escape.txt"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_workspace_path"
    assert not (tmp_path.parent / "escape.txt").exists()


def test_apply_diff_writes_real_workspace_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    test_client = client()

    create_response = test_client.post(
        "/api/workspaces/ws_fs/files",
        json={"path": "index.html", "content": "<main>old</main>\n"},
    )
    assert create_response.status_code == 201
    target_file = tmp_path / "ws_fs" / "index.html"
    assert target_file.read_text(encoding="utf-8") == "<main>old</main>\n"

    diff = create_unified_diff("<main>old</main>\n", "<main>new</main>\n", "index.html")
    apply_response = test_client.post(
        "/api/workspaces/ws_fs/apply-diff",
        json={"artifact_id": "artifact_diff_fs", "diff": diff},
    )

    assert apply_response.status_code == 200
    assert target_file.read_text(encoding="utf-8") == "<main>new</main>\n"


def test_revert_applied_diff_restores_previous_file_content(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    test_client = client()

    test_client.post(
        "/api/workspaces/ws_revert/files",
        json={"path": "index.html", "content": "<main>old</main>\n"},
    )
    diff = create_unified_diff("<main>old</main>\n", "<main>new</main>\n", "index.html")
    apply_response = test_client.post(
        "/api/workspaces/ws_revert/apply-diff",
        json={"artifact_id": "artifact_diff_revert", "diff": diff},
    )
    assert apply_response.status_code == 200
    history_response = test_client.get("/api/workspaces/ws_revert/applied-diffs")
    record_id = history_response.json()[0]["id"]
    assert history_response.json()[0]["reverted_at"] is None

    revert_response = test_client.post(
        f"/api/workspaces/ws_revert/applied-diffs/{record_id}/revert"
    )

    assert revert_response.status_code == 200
    assert revert_response.json()["path"] == "index.html"
    content_response = test_client.get(
        "/api/workspaces/ws_revert/files/content",
        params={"path": "index.html"},
    )
    assert content_response.json()["content"] == "<main>old</main>\n"
    preview_response = test_client.get("/api/workspaces/ws_revert/preview")
    assert preview_response.json()["entry_path"] == "index.html"
    reverted_history = test_client.get("/api/workspaces/ws_revert/applied-diffs").json()
    assert reverted_history[0]["reverted_at"] is not None


def test_revert_applied_diff_removes_file_created_by_diff(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    test_client = client()
    diff = create_unified_diff("", "<main>created</main>\n", "created.html")
    apply_response = test_client.post(
        "/api/workspaces/ws_revert_created/apply-diff",
        json={"artifact_id": "artifact_diff_created", "diff": diff},
    )
    assert apply_response.status_code == 200
    record_id = test_client.get("/api/workspaces/ws_revert_created/applied-diffs").json()[0]["id"]

    revert_response = test_client.post(
        f"/api/workspaces/ws_revert_created/applied-diffs/{record_id}/revert"
    )

    assert revert_response.status_code == 200
    assert not (tmp_path / "ws_revert_created" / "created.html").exists()
    content_response = test_client.get(
        "/api/workspaces/ws_revert_created/files/content",
        params={"path": "created.html"},
    )
    assert content_response.status_code == 404


def test_workspace_file_is_created_only_after_apply_diff(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    test_client = client()
    target_file = tmp_path / "ws_apply_later" / "index.html"

    list_response = test_client.get("/api/workspaces/ws_apply_later/files")
    assert list_response.status_code == 200
    assert list_response.json() == []
    assert not target_file.exists()

    diff = create_unified_diff("", "<main>created after apply</main>\n", "index.html")
    assert not target_file.exists()

    apply_response = test_client.post(
        "/api/workspaces/ws_apply_later/apply-diff",
        json={"artifact_id": "artifact_diff_new_file", "diff": diff},
    )

    assert apply_response.status_code == 200
    assert apply_response.json()["path"] == "index.html"
    assert target_file.read_text(encoding="utf-8") == "<main>created after apply</main>\n"


def test_apply_diff_sets_html_preview_entry_path(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    test_client = client()

    diff = create_unified_diff("", "<main>todo preview</main>\n", "todo.html")
    apply_response = test_client.post(
        "/api/workspaces/ws_todo_preview/apply-diff",
        json={"artifact_id": "artifact_diff_todo", "diff": diff},
    )

    assert apply_response.status_code == 200
    applied = apply_response.json()
    assert applied["path"] == "todo.html"
    assert applied["entry_path"] == "todo.html"
    assert applied["preview_url"].endswith(
        "/api/workspaces/ws_todo_preview/preview-page?path=todo.html"
    )

    preview_response = test_client.get("/api/workspaces/ws_todo_preview/preview")
    assert preview_response.status_code == 200
    assert preview_response.json()["entry_path"] == "todo.html"
    assert preview_response.json()["preview_url"] == applied["preview_url"]

    page_response = test_client.get(
        "/api/workspaces/ws_todo_preview/preview-page",
        params={"path": "todo.html"},
    )
    assert page_response.status_code == 200
    assert "<main>todo preview</main>" in page_response.text


def test_workspace_path_traversal_is_rejected(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    test_client = client()

    response = test_client.post(
        "/api/workspaces/ws_fs/files",
        json={"path": "../escape.txt", "content": "bad"},
    )

    assert response.status_code == 400
    assert not (tmp_path.parent / "escape.txt").exists()


def test_workspace_preview_page_serves_index_html_when_present(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    test_client = client()
    write_response = test_client.post(
        "/api/workspaces/ws_demo/files",
        json={"path": "index.html", "content": "<main>hello workspace</main>"},
    )
    assert write_response.status_code == 201

    response = test_client.get("/api/workspaces/ws_demo/preview-page")

    assert response.status_code == 200
    assert "<main>hello workspace</main>" in response.text


def test_preview_page_returns_no_store_header(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    test_client = client()
    write_response = test_client.post(
        "/api/workspaces/ws_no_store/files",
        json={"path": "index.html", "content": "<main>fresh preview</main>"},
    )
    assert write_response.status_code == 201

    response = test_client.get("/api/workspaces/ws_no_store/preview-page")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"


def test_preview_page_serves_latest_workspace_file_after_rewrite(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    test_client = client()
    first_write = test_client.post(
        "/api/workspaces/ws_fresh_file/files",
        json={"path": "index.html", "content": "<main>old preview</main>"},
    )
    assert first_write.status_code == 201

    first_response = test_client.get("/api/workspaces/ws_fresh_file/preview-page")
    assert first_response.status_code == 200
    assert "<main>old preview</main>" in first_response.text

    second_write = test_client.post(
        "/api/workspaces/ws_fresh_file/files",
        json={"path": "index.html", "content": "<main>new preview</main>"},
    )
    assert second_write.status_code == 201

    second_response = test_client.get("/api/workspaces/ws_fresh_file/preview-page")
    assert second_response.status_code == 200
    assert "<main>new preview</main>" in second_response.text
    assert "<main>old preview</main>" not in second_response.text


def test_preview_page_rewrites_or_bases_relative_assets(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    test_client = client()
    write_response = test_client.post(
        "/api/workspaces/ws_assets/files",
        json={
            "path": "index.html",
            "content": (
                '<!doctype html><html><head><link rel="stylesheet" href="style.css">'
                '</head><body><script src="script.js"></script></body></html>'
            ),
        },
    )
    assert write_response.status_code == 201

    response = test_client.get("/api/workspaces/ws_assets/preview-page")

    assert response.status_code == 200
    assert '<base href="http://testserver/api/workspaces/ws_assets/preview-assets/">' in (
        response.text
    )
    assert 'href="style.css"' in response.text
    assert 'src="script.js"' in response.text


def test_preview_page_uses_nested_entry_directory_for_relative_assets(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    test_client = client()
    write_response = test_client.post(
        "/api/workspaces/ws_nested_assets/files",
        json={
            "path": "pages/demo.html",
            "content": (
                '<!doctype html><html><head><link rel="stylesheet" href="style.css">'
                '</head><body><script src="script.js"></script></body></html>'
            ),
        },
    )
    assert write_response.status_code == 201

    response = test_client.get(
        "/api/workspaces/ws_nested_assets/preview-page",
        params={"path": "pages/demo.html"},
    )

    assert response.status_code == 200
    assert (
        '<base href="http://testserver/api/workspaces/ws_nested_assets/preview-assets/pages/">'
    ) in response.text
    assert 'href="style.css"' in response.text
    assert 'src="script.js"' in response.text


def test_preview_asset_serves_workspace_javascript_with_content_type(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    test_client = client()
    write_response = test_client.post(
        "/api/workspaces/ws_assets/files",
        json={"path": "script.js", "content": "window.todoReady = true;\n"},
    )
    assert write_response.status_code == 201

    response = test_client.get("/api/workspaces/ws_assets/preview-assets/script.js")

    assert response.status_code == 200
    assert response.text == "window.todoReady = true;\n"
    assert response.headers["content-type"].startswith("text/javascript")


def test_preview_asset_returns_no_store_header(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    test_client = client()
    write_response = test_client.post(
        "/api/workspaces/ws_asset_no_store/files",
        json={"path": "script.js", "content": "window.todoReady = true;\n"},
    )
    assert write_response.status_code == 201

    response = test_client.get("/api/workspaces/ws_asset_no_store/preview-assets/script.js")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"


def test_preview_asset_serves_workspace_css_with_content_type(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    test_client = client()
    write_response = test_client.post(
        "/api/workspaces/ws_assets/files",
        json={"path": "style.css", "content": "body { color: green; }\n"},
    )
    assert write_response.status_code == 201

    response = test_client.get("/api/workspaces/ws_assets/preview-assets/style.css")

    assert response.status_code == 200
    assert response.text == "body { color: green; }\n"
    assert response.headers["content-type"].startswith("text/css")


def test_preview_asset_rejects_path_traversal(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    test_client = client()

    response = test_client.get("/api/workspaces/ws_assets/preview-assets/%2E%2E/escape.js")

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_workspace_path"


def test_preview_asset_missing_file_returns_404(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    test_client = client()

    response = test_client.get("/api/workspaces/ws_assets/preview-assets/missing.js")

    assert response.status_code == 404
    assert response.json()["code"] == "workspace_file_not_found"
