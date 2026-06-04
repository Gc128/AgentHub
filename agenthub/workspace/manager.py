"""
agenthub/workspace/manager.py

Workspace 基础路径管理模块。

职责：
- 定义 WorkspacePathError 异常
- 提供 resolve_workspace_path 安全路径解析函数，防止路径穿越攻击

本模块不涉及文件读写、Diff、Git 操作。
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath


class WorkspacePathError(ValueError):
    """当解析路径越出 workspace 根目录时抛出。"""


def normalize_workspace_file_path(path: str) -> str:
    """规范化 workspace 内文件路径。

    这个 helper 用于 API 层的逻辑文件路径，不访问物理磁盘。它接受 git diff
    常见的 `a/`、`b/` 前缀，并拒绝绝对路径、空路径和 `..` 越权片段。
    """

    value = path.strip()
    if value.startswith(("a/", "b/")):
        value = value[2:]

    candidate = PurePosixPath(value)
    if (
        not value
        or candidate.is_absolute()
        or any(part in {"", ".", ".."} for part in candidate.parts)
    ):
        raise WorkspacePathError("文件路径必须是 workspace 内的相对路径")
    return candidate.as_posix()


def resolve_workspace_path(root: Path, relative_path: str) -> Path:
    """将相对路径解析为绝对路径，并校验其必须在 root 目录内。

    Args:
        root: workspace 根目录（可以是相对或绝对路径，函数内部会 resolve）。
        relative_path: 用户传入的相对路径字符串。

    Returns:
        经过 resolve 的、位于 root 目录内的绝对 Path 对象。

    Raises:
        WorkspacePathError: 解析后的路径越出 root 目录，或 relative_path
            以绝对路径形式传入并指向 root 之外。

    Examples:
        >>> from pathlib import Path
        >>> root = Path("/workspace/project")
        >>> resolve_workspace_path(root, "src/main.py")
        PosixPath('/workspace/project/src/main.py')
        >>> resolve_workspace_path(root, "../secret")  # raises WorkspacePathError
    """
    resolved_root = root.resolve()
    # 拒绝绝对路径输入（用户不应绕过 root 直接指定系统路径）
    if Path(relative_path).is_absolute():
        raise WorkspacePathError(
            f"relative_path must be a relative path, got absolute: {relative_path!r}"
        )

    target = (resolved_root / relative_path).resolve()

    # 核心越权检查：target 必须等于 root 本身，或是 root 的子路径
    # 使用 Path.is_relative_to()（Python 3.9+）确保严格包含关系
    if target != resolved_root and not target.is_relative_to(resolved_root):
        raise WorkspacePathError(f"Path {relative_path!r} escapes workspace root {resolved_root}")

    return target
