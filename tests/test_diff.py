"""
tests/test_diff.py

create_unified_diff 和 apply_diff 的单元测试。

覆盖场景：
- 闭环验证（生成 diff 后再应用，必须还原）
- diff 格式头部校验
- 无变化时 diff 为空
- 单行修改 / 增加 / 删除
- 多行增删改混合
- 文件末尾无换行符
- 空文件到有内容 / 有内容到空文件
- apply_diff 对非法输入的错误处理
"""

from __future__ import annotations

import pytest

from agenthub.workspace.diff import DiffApplyError, apply_diff, create_unified_diff

# ---------------------------------------------------------------------------
# 辅助常量
# ---------------------------------------------------------------------------

SIMPLE_OLD = "line1\nline2\nline3\n"
SIMPLE_NEW = "line1\nline2 modified\nline3\n"

MULTILINE_OLD = "a\nb\nc\nd\ne\n"
MULTILINE_NEW = "a\nB\nC\nd\nE\n"


# ---------------------------------------------------------------------------
# create_unified_diff：格式校验
# ---------------------------------------------------------------------------


class TestCreateUnifiedDiff:
    def test_header_from_file(self) -> None:
        diff = create_unified_diff(SIMPLE_OLD, SIMPLE_NEW, "foo.py")
        assert "--- a/foo.py" in diff

    def test_header_to_file(self) -> None:
        diff = create_unified_diff(SIMPLE_OLD, SIMPLE_NEW, "foo.py")
        assert "+++ b/foo.py" in diff

    def test_contains_removed_line(self) -> None:
        diff = create_unified_diff(SIMPLE_OLD, SIMPLE_NEW, "foo.py")
        assert "-line2\n" in diff

    def test_contains_added_line(self) -> None:
        diff = create_unified_diff(SIMPLE_OLD, SIMPLE_NEW, "foo.py")
        assert "+line2 modified\n" in diff

    def test_no_diff_when_identical(self) -> None:
        diff = create_unified_diff(SIMPLE_OLD, SIMPLE_OLD, "foo.py")
        assert diff == ""

    def test_filename_in_header(self) -> None:
        diff = create_unified_diff("x\n", "y\n", "path/to/file.txt")
        assert "a/path/to/file.txt" in diff
        assert "b/path/to/file.txt" in diff

    def test_empty_old_to_content(self) -> None:
        diff = create_unified_diff("", "hello\n", "new.py")
        assert "+hello\n" in diff

    def test_content_to_empty_new(self) -> None:
        diff = create_unified_diff("hello\n", "", "deleted.py")
        assert "-hello\n" in diff

    def test_returns_string(self) -> None:
        diff = create_unified_diff(SIMPLE_OLD, SIMPLE_NEW, "f.py")
        assert isinstance(diff, str)

    def test_keepends_preserves_newlines(self) -> None:
        """确保 diff 文本本身是换行符完整的，不含裸 None 或截断行。"""
        diff = create_unified_diff(SIMPLE_OLD, SIMPLE_NEW, "f.py")
        for line in diff.splitlines(keepends=True):
            assert line.endswith("\n"), f"Line missing newline: {line!r}"


# ---------------------------------------------------------------------------
# apply_diff：闭环验证（核心场景）
# ---------------------------------------------------------------------------


class TestApplyDiffRoundtrip:
    def _roundtrip(self, old: str, new: str, filename: str = "f.py") -> None:
        diff = create_unified_diff(old, new, filename)
        result = apply_diff(old, diff)
        assert result == new, f"Roundtrip failed.\nExpected:\n{new!r}\nGot:\n{result!r}"

    def test_single_line_modify(self) -> None:
        self._roundtrip(SIMPLE_OLD, SIMPLE_NEW)

    def test_multiline_mixed_changes(self) -> None:
        self._roundtrip(MULTILINE_OLD, MULTILINE_NEW)

    def test_add_line_at_end(self) -> None:
        self._roundtrip("a\nb\n", "a\nb\nc\n")

    def test_add_line_at_start(self) -> None:
        self._roundtrip("b\nc\n", "a\nb\nc\n")

    def test_add_line_in_middle(self) -> None:
        self._roundtrip("a\nc\n", "a\nb\nc\n")

    def test_remove_first_line(self) -> None:
        self._roundtrip("a\nb\nc\n", "b\nc\n")

    def test_remove_last_line(self) -> None:
        self._roundtrip("a\nb\nc\n", "a\nb\n")

    def test_remove_middle_line(self) -> None:
        self._roundtrip("a\nb\nc\n", "a\nc\n")

    def test_remove_all_lines(self) -> None:
        self._roundtrip("a\nb\nc\n", "")

    def test_empty_to_content(self) -> None:
        self._roundtrip("", "hello\nworld\n")

    def test_single_line_file(self) -> None:
        self._roundtrip("old\n", "new\n")

    def test_no_trailing_newline(self) -> None:
        """文件末尾无换行符的情况。"""
        self._roundtrip("a\nb", "a\nc")

    def test_large_file_many_hunks(self) -> None:
        """多 hunk 场景：修改分布在文件头、中、尾，产生多个独立 hunk。"""
        lines = [f"line{i}\n" for i in range(1, 51)]
        old = "".join(lines)
        modified = lines[:]
        modified[0] = "CHANGED_TOP\n"
        modified[25] = "CHANGED_MIDDLE\n"
        modified[49] = "CHANGED_BOTTOM\n"
        new = "".join(modified)
        self._roundtrip(old, new)

    def test_add_multiple_consecutive_lines(self) -> None:
        self._roundtrip("a\ne\n", "a\nb\nc\nd\ne\n")

    def test_remove_multiple_consecutive_lines(self) -> None:
        self._roundtrip("a\nb\nc\nd\ne\n", "a\ne\n")

    def test_identical_content_returns_original(self) -> None:
        """diff 为空时 apply_diff 应直接返回原始内容。"""
        content = "unchanged\n"
        diff = create_unified_diff(content, content, "f.py")
        # diff == ""，apply_diff 应拒绝空 diff
        # 因为"没有 diff"意味着调用方逻辑有误，应提前检测
        with pytest.raises(DiffApplyError):
            apply_diff(content, diff)


# ---------------------------------------------------------------------------
# apply_diff：非法输入的错误处理
# ---------------------------------------------------------------------------


class TestApplyDiffErrors:
    def test_empty_diff_raises(self) -> None:
        with pytest.raises(DiffApplyError):
            apply_diff("content\n", "")

    def test_whitespace_only_diff_raises(self) -> None:
        with pytest.raises(DiffApplyError):
            apply_diff("content\n", "   \n  ")

    def test_invalid_diff_format_raises(self) -> None:
        with pytest.raises(DiffApplyError):
            apply_diff("content\n", "this is not a diff at all!!!")

    def test_error_is_value_error_subclass(self) -> None:
        with pytest.raises(ValueError):
            apply_diff("x\n", "")
