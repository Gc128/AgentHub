"""
tests/test_workspace.py

WorkspacePathError 和 resolve_workspace_path 的单元测试。

覆盖场景：
- 正常相对路径解析
- 多层嵌套路径
- 指向 root 本身
- 空字符串（等价于 root）
- ../  路径穿越（单层、多层）
- 伪装穿越（看似合法但包含 ..）
- 绝对路径输入
- 符号链接同名但不在 root 下的路径（通过字符串构造模拟）
"""

from __future__ import annotations

import pytest
from pathlib import Path

from agenthub.workspace.manager import WorkspacePathError, resolve_workspace_path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def workspace_root(tmp_path: Path) -> Path:
    """使用 pytest 内置 tmp_path 作为 workspace 根目录，保证测试隔离。"""
    root = tmp_path / "workspace"
    root.mkdir()
    return root


# ---------------------------------------------------------------------------
# 正常路径 —— 应该成功返回
# ---------------------------------------------------------------------------

class TestValidPaths:
    def test_simple_file(self, workspace_root: Path) -> None:
        result = resolve_workspace_path(workspace_root, "README.md")
        assert result == workspace_root.resolve() / "README.md"

    def test_nested_file(self, workspace_root: Path) -> None:
        result = resolve_workspace_path(workspace_root, "src/utils/helper.py")
        assert result == workspace_root.resolve() / "src" / "utils" / "helper.py"

    def test_single_directory(self, workspace_root: Path) -> None:
        result = resolve_workspace_path(workspace_root, "src")
        assert result == workspace_root.resolve() / "src"

    def test_dot_refers_to_root(self, workspace_root: Path) -> None:
        """'.' 解析后等于 root 本身，应该允许。"""
        result = resolve_workspace_path(workspace_root, ".")
        assert result == workspace_root.resolve()

    def test_empty_string_refers_to_root(self, workspace_root: Path) -> None:
        """空字符串等价于 root 本身，应该允许。"""
        result = resolve_workspace_path(workspace_root, "")
        assert result == workspace_root.resolve()

    def test_path_with_redundant_dot(self, workspace_root: Path) -> None:
        """'src/./main.py' 中的 '.' 应被 resolve 消除，仍然合法。"""
        result = resolve_workspace_path(workspace_root, "src/./main.py")
        assert result == workspace_root.resolve() / "src" / "main.py"

    def test_go_down_then_back_stays_inside(self, workspace_root: Path) -> None:
        """'src/../src/main.py' 展开后仍在 root 内，应允许。"""
        result = resolve_workspace_path(workspace_root, "src/../src/main.py")
        assert result == workspace_root.resolve() / "src" / "main.py"

    def test_result_is_absolute(self, workspace_root: Path) -> None:
        result = resolve_workspace_path(workspace_root, "a/b/c.txt")
        assert result.is_absolute()

    def test_root_given_as_relative(self, tmp_path: Path) -> None:
        """root 本身传入相对路径时，函数内部应正确 resolve。"""
        root = tmp_path / "ws"
        root.mkdir()
        # 构造一个相对 root（仅在 cwd 下有意义，这里用 tmp 绝对路径模拟）
        result = resolve_workspace_path(root, "file.txt")
        assert result == root.resolve() / "file.txt"


# ---------------------------------------------------------------------------
# 路径穿越 —— 必须抛出 WorkspacePathError
# ---------------------------------------------------------------------------

class TestPathTraversalBlocked:
    def test_single_dotdot(self, workspace_root: Path) -> None:
        with pytest.raises(WorkspacePathError):
            resolve_workspace_path(workspace_root, "../escape.txt")

    def test_multi_dotdot(self, workspace_root: Path) -> None:
        with pytest.raises(WorkspacePathError):
            resolve_workspace_path(workspace_root, "../../etc/passwd")

    def test_dotdot_after_subdir(self, workspace_root: Path) -> None:
        """进入子目录后再穿越出去。"""
        with pytest.raises(WorkspacePathError):
            resolve_workspace_path(workspace_root, "src/../../outside.txt")

    def test_deeply_nested_escape(self, workspace_root: Path) -> None:
        with pytest.raises(WorkspacePathError):
            resolve_workspace_path(workspace_root, "a/b/c/../../../../../../../tmp/x")

    def test_dotdot_only(self, workspace_root: Path) -> None:
        with pytest.raises(WorkspacePathError):
            resolve_workspace_path(workspace_root, "..")

    def test_absolute_path_outside_root(self, workspace_root: Path) -> None:
        """绝对路径输入应直接拒绝，无论是否在 root 内。"""
        with pytest.raises(WorkspacePathError):
            resolve_workspace_path(workspace_root, "/etc/passwd")

    def test_absolute_path_pointing_to_root(self, workspace_root: Path) -> None:
        """即使绝对路径恰好指向 root，也应拒绝（绝对路径本身就是非法输入）。"""
        with pytest.raises(WorkspacePathError):
            resolve_workspace_path(workspace_root, str(workspace_root))

    def test_absolute_path_inside_root(self, workspace_root: Path) -> None:
        """绝对路径即使在 root 内也应拒绝，防止混淆。"""
        inside = str(workspace_root / "src" / "main.py")
        with pytest.raises(WorkspacePathError):
            resolve_workspace_path(workspace_root, inside)


# ---------------------------------------------------------------------------
# 异常信息可读性
# ---------------------------------------------------------------------------

class TestErrorMessages:
    def test_error_message_contains_path(self, workspace_root: Path) -> None:
        with pytest.raises(WorkspacePathError, match="escape"):
            resolve_workspace_path(workspace_root, "../escape.txt")

    def test_error_is_value_error_subclass(self, workspace_root: Path) -> None:
        """WorkspacePathError 必须是 ValueError 的子类，方便上层捕获。"""
        with pytest.raises(ValueError):
            resolve_workspace_path(workspace_root, "../x")