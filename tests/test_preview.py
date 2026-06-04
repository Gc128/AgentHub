"""
tests/test_preview.py

preview.py 的单元与集成测试。

覆盖场景：
- resolve_preview_path：合法路径 / workspace_id 非法 / 路径穿越 / 绝对路径拒绝
- get_preview_url：URL 格式 / file_path 规范化 / 安全拒绝
- find_free_port：端口可用检测
- PreviewServer：启动/停止/上下文管理器 / 重复启动报错 /
                 目录不存在报错 / 实际 HTTP 访问（需要 httpx）
- make_static_files_app：路径安全校验（不做完整 ASGI 集成测试，
                          避免依赖 uvicorn）
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

import agenthub.workspace.preview as preview_mod
from agenthub.workspace.preview import (
    PreviewError,
    PreviewPathError,
    PreviewServer,
    find_free_port,
    get_preview_url,
    make_static_files_app,
    resolve_preview_path,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def workspaces_root(tmp_path: Path) -> Path:
    """提供一个隔离的 workspaces 根目录。"""
    root = tmp_path / "workspaces"
    root.mkdir()
    return root


@pytest.fixture()
def workspace_dir(workspaces_root: Path) -> Path:
    """在 workspaces_root 下创建一个名为 'proj-001' 的 workspace 目录。"""
    ws = workspaces_root / "proj-001"
    ws.mkdir()
    return ws


@pytest.fixture()
def index_html(workspace_dir: Path) -> Path:
    """在 workspace_dir 内写入 index.html。"""
    p = workspace_dir / "index.html"
    p.write_text("<html><body>hello preview</body></html>", encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# resolve_preview_path
# ---------------------------------------------------------------------------


class TestResolvePreviewPath:
    def test_default_file_path(self, workspaces_root: Path) -> None:
        result = resolve_preview_path("proj-001", workspaces_root=workspaces_root)
        assert result == workspaces_root.resolve() / "proj-001" / "index.html"

    def test_custom_file_path(self, workspaces_root: Path) -> None:
        result = resolve_preview_path("proj-001", "src/app.js", workspaces_root=workspaces_root)
        assert result == workspaces_root.resolve() / "proj-001" / "src" / "app.js"

    def test_result_is_absolute(self, workspaces_root: Path) -> None:
        result = resolve_preview_path("proj-001", workspaces_root=workspaces_root)
        assert result.is_absolute()

    def test_invalid_workspace_id_with_slash(self, workspaces_root: Path) -> None:
        with pytest.raises(PreviewPathError, match="invalid"):
            resolve_preview_path("../evil", workspaces_root=workspaces_root)

    def test_invalid_workspace_id_empty(self, workspaces_root: Path) -> None:
        with pytest.raises(PreviewPathError, match="invalid"):
            resolve_preview_path("", workspaces_root=workspaces_root)

    def test_invalid_workspace_id_space(self, workspaces_root: Path) -> None:
        with pytest.raises(PreviewPathError):
            resolve_preview_path("proj 001", workspaces_root=workspaces_root)

    def test_file_path_traversal_blocked(self, workspaces_root: Path) -> None:
        with pytest.raises(PreviewPathError, match="escapes"):
            resolve_preview_path("proj-001", "../../etc/passwd", workspaces_root=workspaces_root)

    def test_absolute_file_path_blocked(self, workspaces_root: Path) -> None:
        with pytest.raises(PreviewPathError, match="absolute"):
            resolve_preview_path("proj-001", "/etc/passwd", workspaces_root=workspaces_root)

    def test_dot_path_stays_in_workspace(self, workspaces_root: Path) -> None:
        result = resolve_preview_path("proj-001", "sub/../index.html", workspaces_root=workspaces_root)
        assert result == workspaces_root.resolve() / "proj-001" / "index.html"

    def test_path_error_is_value_error_subclass(self, workspaces_root: Path) -> None:
        with pytest.raises(ValueError):
            resolve_preview_path("bad/id", workspaces_root=workspaces_root)


# ---------------------------------------------------------------------------
# get_preview_url
# ---------------------------------------------------------------------------


class TestGetPreviewUrl:
    def test_default_url_format(self) -> None:
        url = get_preview_url("proj-001", port=18000)
        assert url == "http://127.0.0.1:18000/index.html"

    def test_custom_file_path(self) -> None:
        url = get_preview_url("proj-001", "src/app.js", port=18000)
        assert url == "http://127.0.0.1:18000/src/app.js"

    def test_custom_host(self) -> None:
        url = get_preview_url("proj-001", port=18001, host="0.0.0.0")
        assert url.startswith("http://0.0.0.0:18001/")

    def test_leading_slash_normalised(self) -> None:
        url = get_preview_url("proj-001", "/index.html", port=18000)
        assert url == "http://127.0.0.1:18000/index.html"

    def test_backslash_converted_to_forward(self) -> None:
        # Windows 风格路径应被规范化
        url = get_preview_url("proj-001", "sub\\page.html", port=18000)
        assert "sub/page.html" in url

    def test_invalid_workspace_id_raises(self) -> None:
        with pytest.raises(PreviewPathError):
            get_preview_url("../evil", port=18000)

    def test_absolute_file_path_normalised_in_url(self) -> None:
        # get_preview_url 的职责是生成 URL，不是访问文件系统。
        # 前导 '/' 被规范化为相对路径，不抛异常（文件系统越权在 resolve_preview_path 拦截）。
        url = get_preview_url("proj-001", "/etc/passwd", port=18000)
        assert url == "http://127.0.0.1:18000/etc/passwd"

    def test_url_contains_port(self) -> None:
        url = get_preview_url("proj-001", port=18765)
        assert ":18765/" in url


# ---------------------------------------------------------------------------
# find_free_port
# ---------------------------------------------------------------------------


class TestFindFreePort:
    def test_returns_integer(self) -> None:
        port = find_free_port()
        assert isinstance(port, int)

    def test_port_in_range(self) -> None:
        port = find_free_port(start=19000, end=19100)
        assert 19000 <= port <= 19100

    def test_no_port_available_raises(self) -> None:
        # 把整个范围的端口都绑定掉（只绑一个端口，范围设为单端口）
        import socket
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            occupied = s.getsockname()[1]
            # 制造一个仅含已被占用端口的"范围"
            with pytest.raises(PreviewError, match="No free port"):
                find_free_port(start=occupied, end=occupied)


# ---------------------------------------------------------------------------
# PreviewServer — 启动 / 停止
# ---------------------------------------------------------------------------


class TestPreviewServerLifecycle:
    def test_invalid_workspace_id_raises_on_init(self, workspaces_root: Path) -> None:
        with pytest.raises(PreviewPathError):
            PreviewServer("../evil", workspaces_root=workspaces_root)

    def test_nonexistent_directory_raises_on_start(self, workspaces_root: Path) -> None:
        srv = PreviewServer("no-such-ws", workspaces_root=workspaces_root)
        with pytest.raises(PreviewError, match="does not exist"):
            srv.start()

    def test_start_sets_is_running(self, workspace_dir: Path, workspaces_root: Path) -> None:
        srv = PreviewServer("proj-001", workspaces_root=workspaces_root)
        assert not srv.is_running
        srv.start()
        try:
            assert srv.is_running
        finally:
            srv.stop()

    def test_stop_clears_is_running(self, workspace_dir: Path, workspaces_root: Path) -> None:
        srv = PreviewServer("proj-001", workspaces_root=workspaces_root)
        srv.start()
        srv.stop()
        assert not srv.is_running

    def test_double_start_raises(self, workspace_dir: Path, workspaces_root: Path) -> None:
        srv = PreviewServer("proj-001", workspaces_root=workspaces_root)
        srv.start()
        try:
            with pytest.raises(PreviewError, match="already running"):
                srv.start()
        finally:
            srv.stop()

    def test_stop_idempotent(self, workspace_dir: Path, workspaces_root: Path) -> None:
        srv = PreviewServer("proj-001", workspaces_root=workspaces_root)
        srv.start()
        srv.stop()
        srv.stop()  # 第二次 stop 不应抛异常

    def test_context_manager_starts_and_stops(self, workspace_dir: Path, workspaces_root: Path) -> None:
        srv = PreviewServer("proj-001", workspaces_root=workspaces_root)
        with srv:
            assert srv.is_running
        assert not srv.is_running

    def test_context_manager_stops_on_exception(self, workspace_dir: Path, workspaces_root: Path) -> None:
        srv = PreviewServer("proj-001", workspaces_root=workspaces_root)
        try:
            with srv:
                raise RuntimeError("simulated error")
        except RuntimeError:
            pass
        assert not srv.is_running

    def test_explicit_port_used(self, workspace_dir: Path, workspaces_root: Path) -> None:
        port = find_free_port(start=19100, end=19200)
        srv = PreviewServer("proj-001", port=port, workspaces_root=workspaces_root)
        assert srv.port == port
        with srv:
            assert srv.port == port

    def test_get_url_returns_correct_url(self, workspace_dir: Path, workspaces_root: Path) -> None:
        srv = PreviewServer("proj-001", workspaces_root=workspaces_root)
        with srv:
            url = srv.get_url("index.html")
            assert f":{srv.port}/index.html" in url
            assert url.startswith("http://127.0.0.1")


# ---------------------------------------------------------------------------
# PreviewServer — 实际 HTTP 访问
# ---------------------------------------------------------------------------


class TestPreviewServerHTTP:
    """验证服务器真正能响应 HTTP 请求并正确返回文件内容。"""

    def test_serves_index_html(
        self, index_html: Path, workspace_dir: Path, workspaces_root: Path
    ) -> None:
        try:
            import httpx
        except ImportError:
            pytest.skip("httpx not installed")

        with PreviewServer("proj-001", workspaces_root=workspaces_root) as srv:
            time.sleep(0.05)  # 给服务器一点启动时间
            url = srv.get_url("index.html")
            resp = httpx.get(url, timeout=3.0)
            assert resp.status_code == 200
            assert "hello preview" in resp.text

    def test_missing_file_returns_404(
        self, workspace_dir: Path, workspaces_root: Path
    ) -> None:
        try:
            import httpx
        except ImportError:
            pytest.skip("httpx not installed")

        with PreviewServer("proj-001", workspaces_root=workspaces_root) as srv:
            time.sleep(0.05)
            url = srv.get_url("does_not_exist.html")
            resp = httpx.get(url, timeout=3.0)
            assert resp.status_code == 404

    def test_subdirectory_file_served(
        self, workspace_dir: Path, workspaces_root: Path
    ) -> None:
        try:
            import httpx
        except ImportError:
            pytest.skip("httpx not installed")

        sub = workspace_dir / "static"
        sub.mkdir()
        (sub / "style.css").write_text("body { color: red; }", encoding="utf-8")

        with PreviewServer("proj-001", workspaces_root=workspaces_root) as srv:
            time.sleep(0.05)
            url = srv.get_url("static/style.css")
            resp = httpx.get(url, timeout=3.0)
            assert resp.status_code == 200
            assert "color" in resp.text


# ---------------------------------------------------------------------------
# make_static_files_app（路径安全层；不做完整 ASGI 测试）
# ---------------------------------------------------------------------------


class TestMakeStaticFilesApp:
    def test_invalid_workspace_id_raises(self, workspaces_root: Path) -> None:
        with pytest.raises(PreviewPathError):
            make_static_files_app("../evil", workspaces_root=workspaces_root)

    def test_nonexistent_directory_raises(self, workspaces_root: Path) -> None:
        with pytest.raises(PreviewError, match="does not exist"):
            make_static_files_app("ghost-ws", workspaces_root=workspaces_root)

    def test_valid_workspace_returns_static_files_app(
        self, workspace_dir: Path, workspaces_root: Path
    ) -> None:
        try:
            from starlette.staticfiles import StaticFiles
        except ImportError:
            pytest.skip("starlette not installed")

        app = make_static_files_app("proj-001", workspaces_root=workspaces_root)
        assert isinstance(app, StaticFiles)