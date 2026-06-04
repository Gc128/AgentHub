"""
agenthub/workspace/preview.py

Workspace 本地预览服务模块。

职责（本模块唯一关注点）：
  1. 将某个 workspace_id 对应的目录以 HTTP 静态文件方式暴露出去。
  2. 生成指向特定文件的预览 URL（辅助函数）。
  3. 对 workspace_id 和文件路径做严格的安全校验，防止路径穿越。
  4. 以后台线程启动轻量级 HTTP 服务，含端口冲突检测与进程生命周期管理。

不做的事：
  - 不修改 api/main.py 的全局路由（由成员 B 负责）。
  - 不依赖 diff / git / manager 等其他 workspace 子模块。

架构选择说明：
  使用 Python 标准库 http.server + threading 启动后台 HTTP 服务，
  而不是依赖 FastAPI/uvicorn 子进程，理由：
    * 零额外依赖，环境移植性更好；
    * 可在同一进程内精确管理线程生命周期；
    * MVP 阶段只需静态文件服务，不需要 SSE / WebSocket；
    * 通过 socketserver.TCPServer(allow_reuse_address=True) 规避 TIME_WAIT。

  同时提供 `make_static_files_app` 供 FastAPI 路由挂载（可选），
  两种模式互不干扰。
"""

from __future__ import annotations

import logging
import re
import socket
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler
from pathlib import Path
from socketserver import TCPServer
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 配置常量
# ---------------------------------------------------------------------------

# 预览服务默认监听地址
_DEFAULT_HOST = "127.0.0.1"
# 端口范围（在此区间内自动找空闲端口）
_PORT_RANGE_START = 18_000
_PORT_RANGE_END = 18_999
# workspace 根目录（实际部署时由 config 注入；此处提供可覆盖的模块级变量）
WORKSPACES_ROOT: Path = Path("workspaces").resolve()


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------


class PreviewError(RuntimeError):
    """预览服务相关的运行时异常。"""


class PreviewPathError(ValueError):
    """路径校验失败时抛出（workspace_id 非法或文件路径穿越）。"""


# ---------------------------------------------------------------------------
# 路径安全校验
# ---------------------------------------------------------------------------

# workspace_id 只允许字母、数字、连字符、下划线，防止路径注入
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _validate_workspace_id(workspace_id: str) -> None:
    """校验 workspace_id 格式，不合法则抛出 PreviewPathError。"""
    if not workspace_id or not _SAFE_ID_RE.match(workspace_id):
        raise PreviewPathError(
            f"workspace_id {workspace_id!r} is invalid. "
            "Only letters, digits, hyphens and underscores are allowed."
        )


def resolve_preview_path(
    workspace_id: str,
    file_path: str = "index.html",
    *,
    workspaces_root: Optional[Path] = None,
) -> Path:
    """将 workspace_id + 相对文件路径解析为绝对路径，并做越权检查。

    Args:
        workspace_id: workspace 唯一标识符（只允许安全字符）。
        file_path: workspace 内的相对文件路径，默认 "index.html"。
        workspaces_root: workspace 根目录，默认使用模块级 WORKSPACES_ROOT。

    Returns:
        已解析的绝对 Path，保证在 workspace 目录内。

    Raises:
        PreviewPathError: workspace_id 非法、file_path 穿越目录、
                          或解析结果不在 workspace 根目录内。
    """
    _validate_workspace_id(workspace_id)

    root = (workspaces_root or WORKSPACES_ROOT).resolve()
    workspace_dir = (root / workspace_id).resolve()

    # workspace_dir 必须在 workspaces_root 下（防止 ../.. 绕过）
    if workspace_dir != root and not workspace_dir.is_relative_to(root):
        raise PreviewPathError(
            f"workspace_dir {workspace_dir} escapes workspaces root {root}"
        )

    # file_path 不允许绝对路径输入
    if Path(file_path).is_absolute():
        raise PreviewPathError(
            f"file_path must be relative, got absolute: {file_path!r}"
        )

    target = (workspace_dir / file_path).resolve()

    # target 必须在 workspace_dir 内
    if target != workspace_dir and not target.is_relative_to(workspace_dir):
        raise PreviewPathError(
            f"file_path {file_path!r} escapes workspace directory {workspace_dir}"
        )

    return target


# ---------------------------------------------------------------------------
# URL 辅助函数
# ---------------------------------------------------------------------------


def get_preview_url(
    workspace_id: str,
    file_path: str = "index.html",
    *,
    host: str = _DEFAULT_HOST,
    port: int,
) -> str:
    """生成指向预览服务的 HTTP URL。

    调用方必须先通过 PreviewServer 获取实际监听端口，再传入此函数。

    Args:
        workspace_id: workspace 唯一标识符。
        file_path: workspace 内的相对文件路径。
        host: 预览服务监听地址，默认 127.0.0.1。
        port: 预览服务实际监听端口。

    Returns:
        形如 "http://127.0.0.1:18000/index.html" 的 URL 字符串。

    Raises:
        PreviewPathError: workspace_id 或 file_path 校验失败。
    """
    # 校验路径（resolve_preview_path 负责具体安全检查）
    # 不要求 workspaces_root 下的目录实际存在（URL 可以在目录创建前生成）
    _validate_workspace_id(workspace_id)

    # 前导 '/' 在 URL 上下文里只是格式噪音（如 "/index.html"），
    # 安全上等价于 "index.html"，直接剥离而不拒绝。
    # 真正的绝对路径（含驱动器字母 C:\ 或多层 //host）由后续检查拦截。
    stripped = file_path.lstrip("/").lstrip("\\")

    # 剥离前导斜杠后若 Path 仍被识别为绝对路径（如 Windows UNC 路径），才拒绝
    if Path(stripped).is_absolute():
        raise PreviewPathError(
            f"file_path must be relative, got absolute: {file_path!r}"
        )

    # 规范化路径分隔符（Windows 路径也用 /）
    normalised = stripped.replace("\\", "/")
    return f"http://{host}:{port}/{normalised}"


# ---------------------------------------------------------------------------
# 端口工具
# ---------------------------------------------------------------------------


def _is_port_free(host: str, port: int) -> bool:
    """检查给定地址+端口是否可用。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def find_free_port(
    host: str = _DEFAULT_HOST,
    start: int = _PORT_RANGE_START,
    end: int = _PORT_RANGE_END,
) -> int:
    """在 [start, end] 范围内找到第一个空闲端口。

    Raises:
        PreviewError: 范围内无可用端口。
    """
    for port in range(start, end + 1):
        if _is_port_free(host, port):
            return port
    raise PreviewError(
        f"No free port available in range [{start}, {end}] on {host}"
    )


# ---------------------------------------------------------------------------
# 静态文件 HTTP 服务器（后台线程）
# ---------------------------------------------------------------------------


class _SilentHandler(SimpleHTTPRequestHandler):
    """抑制 SimpleHTTPRequestHandler 的标准日志输出，避免污染应用日志。"""

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        logger.debug("preview-http: " + format, *args)


class PreviewServer:
    """在后台线程中为指定 workspace 目录提供 HTTP 静态文件服务。

    用法示例::

        server = PreviewServer(workspace_id="proj-123")
        server.start()
        url = server.get_url("index.html")
        # ... 使用 url ...
        server.stop()

        # 或作为上下文管理器：
        with PreviewServer(workspace_id="proj-123") as srv:
            print(srv.get_url())
    """

    def __init__(
        self,
        workspace_id: str,
        *,
        host: str = _DEFAULT_HOST,
        port: Optional[int] = None,
        workspaces_root: Optional[Path] = None,
    ) -> None:
        """
        Args:
            workspace_id: 要服务的 workspace 标识符。
            host: 监听地址，默认 127.0.0.1（仅本地可访问）。
            port: 指定监听端口；None 表示自动选择空闲端口。
            workspaces_root: workspace 根目录，默认使用模块级 WORKSPACES_ROOT。

        Raises:
            PreviewPathError: workspace_id 格式非法。
            PreviewError: 无可用端口。
        """
        _validate_workspace_id(workspace_id)
        self.workspace_id = workspace_id
        self.host = host
        self.workspaces_root = (workspaces_root or WORKSPACES_ROOT).resolve()
        self.workspace_dir = (self.workspaces_root / workspace_id).resolve()

        # 安全检查：workspace_dir 必须在 workspaces_root 下
        if not self.workspace_dir.is_relative_to(self.workspaces_root):
            raise PreviewPathError(
                f"workspace_id {workspace_id!r} resolves outside workspaces root"
            )

        self.port: int = port if port is not None else 0
        self._server: Optional[TCPServer] = None
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def start(self) -> None:
        """在后台线程启动 HTTP 服务器。"""
        if self._server is not None:
            raise PreviewError(
                f"PreviewServer for {self.workspace_id!r} is already running"
            )

        if not self.workspace_dir.exists():
            raise PreviewError(
                f"Workspace directory does not exist: {self.workspace_dir}. "
                "Create the workspace before starting the preview server."
            )

        handler = partial(
            _SilentHandler,
            directory=str(self.workspace_dir),
        )

        try:
            # 关键修改 1：传入 bind_and_activate=False，阻止它自动绑定
            server = TCPServer((self.host, self.port), handler, bind_and_activate=False)
            
            # 关键修改 2：在真正绑定前，设置端口复用标志
            server.allow_reuse_address = True
            
            # 关键修改 3：手动执行绑定和激活
            server.server_bind()
            server.server_activate()
            
            # 关键修改 4：如果初始化时端口是 0，这里需要把系统实际分配的真实端口存下来
            # 否则 get_url() 拼出来的会是 http://127.0.0.1:0/...
            self.port = server.server_address[1]
            
        except OSError as exc:
            raise PreviewError(
                f"Failed to bind preview server on {self.host}:{self.port}: {exc}"
            ) from exc

        self._server = server
        self._thread = threading.Thread(
            target=server.serve_forever,
            name=f"preview-{self.workspace_id}",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "Preview server started for workspace %r at http://%s:%d",
            self.workspace_id,
            self.host,
            self.port,
        )

    def stop(self) -> None:
        """关闭后台 HTTP 服务器并等待线程退出。"""
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        self._server = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("Preview server stopped for workspace %r", self.workspace_id)

    @property
    def is_running(self) -> bool:
        """返回服务器是否正在运行。"""
        return self._server is not None

    # ------------------------------------------------------------------
    # 上下文管理器支持
    # ------------------------------------------------------------------

    def __enter__(self) -> PreviewServer:
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.stop()

    # ------------------------------------------------------------------
    # URL 生成
    # ------------------------------------------------------------------

    def get_url(self, file_path: str = "index.html") -> str:
        """生成指向本服务的预览 URL。

        Args:
            file_path: workspace 内的相对文件路径。

        Returns:
            形如 "http://127.0.0.1:18000/index.html" 的字符串。

        Raises:
            PreviewPathError: file_path 路径穿越校验失败。
        """
        return get_preview_url(
            self.workspace_id,
            file_path,
            host=self.host,
            port=self.port,
        )


# ---------------------------------------------------------------------------
# FastAPI StaticFiles 集成辅助（供成员 B 在 api/main.py 中挂载）
# ---------------------------------------------------------------------------


def make_static_files_app(
    workspace_id: str,
    *,
    workspaces_root: Optional[Path] = None,
) -> "starlette.staticfiles.StaticFiles":  # type: ignore[name-defined]  # noqa: F821
    """返回一个 Starlette StaticFiles 实例，供 FastAPI router.mount() 使用。

    调用示例（由成员 B 在 api/routes/workspaces.py 中完成）::

        from agenthub.workspace.preview import make_static_files_app

        preview_app = make_static_files_app("proj-123")
        router.mount("/preview/proj-123", preview_app)

    Args:
        workspace_id: workspace 标识符。
        workspaces_root: workspace 根目录，默认使用模块级 WORKSPACES_ROOT。

    Returns:
        starlette.staticfiles.StaticFiles 实例。

    Raises:
        PreviewPathError: workspace_id 非法或目录穿越。
        ImportError: starlette 未安装（不是必须依赖，按需安装）。
        PreviewError: workspace 目录不存在。
    """
    try:
        from starlette.staticfiles import StaticFiles
    except ImportError as exc:
        raise ImportError(
            "starlette is required for make_static_files_app. "
            "Install it with: pip install starlette"
        ) from exc

    _validate_workspace_id(workspace_id)
    root = (workspaces_root or WORKSPACES_ROOT).resolve()
    workspace_dir = (root / workspace_id).resolve()

    if not workspace_dir.is_relative_to(root):
        raise PreviewPathError(
            f"workspace_id {workspace_id!r} resolves outside workspaces root"
        )

    if not workspace_dir.exists():
        raise PreviewError(
            f"Workspace directory does not exist: {workspace_dir}"
        )

    return StaticFiles(directory=str(workspace_dir), html=True)