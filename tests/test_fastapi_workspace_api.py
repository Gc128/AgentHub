import os

from fastapi.testclient import TestClient

from agenthub.api.deps import reset_dependency_caches
from agenthub.config import get_settings
from agenthub.main import app
from agenthub.workspace.diff import create_unified_diff


def client() -> TestClient:
    os.environ["PERSISTENCE_BACKEND"] = "memory"
    os.environ["USE_MOCK_AGENTS"] = "true"
    get_settings.cache_clear()
    reset_dependency_caches()
    return TestClient(app)


def test_workspace_preview_uses_preview_url_field() -> None:
    response = client().get("/api/workspaces/ws_demo/preview")

    assert response.status_code == 200
    assert response.json() == {
        "workspace_id": "ws_demo",
        "status": "not_started",
        "preview_url": None,
    }


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
