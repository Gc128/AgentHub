from pathlib import Path

import pytest

from agenthub.workspace.diff import create_unified_diff
from agenthub.workspace.manager import WorkspaceManager, WorkspacePathError


def test_workspace_write_and_read(tmp_path: Path) -> None:
    manager = WorkspaceManager(tmp_path)
    manager.write_text("conv_001", "src/app.py", "print('ok')")
    assert manager.read_text("conv_001", "src/app.py") == "print('ok')"


def test_workspace_blocks_path_traversal(tmp_path: Path) -> None:
    manager = WorkspaceManager(tmp_path)
    with pytest.raises(WorkspacePathError):
        manager.resolve("conv_001", "../outside.txt")


def test_create_unified_diff() -> None:
    diff = create_unified_diff("a\n", "b\n", "demo.txt")
    assert "--- a/demo.txt" in diff
    assert "+++ b/demo.txt" in diff
