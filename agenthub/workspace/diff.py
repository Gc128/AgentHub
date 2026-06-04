"""
agenthub/workspace/diff.py

Workspace 文件差异生成与应用模块。

职责：
- create_unified_diff：基于 difflib 生成标准 Unified Diff 文本
- apply_diff：将 Unified Diff 文本应用到原始字符串，返回更新后内容

依赖：
- difflib（标准库）
- unidiff：Python 原生无内置"应用 diff"函数。unidiff 提供健壮的
  Unified Diff 解析，能正确处理多行增删改、上下文行、无换行符末尾
  等边界场景，比手写正则更可靠，符合 PYTHON_PROJECT_GUIDE.md 规范。

本模块不涉及物理文件读写、Git 操作，也不集成 FastAPI。
"""

from __future__ import annotations

import difflib

from unidiff import PatchSet


class DiffApplyError(ValueError):
    """当 diff 文本无法被正确应用到原始内容时抛出。"""


def create_unified_diff(old: str, new: str, filename: str) -> str:
    """生成标准 Unified Diff 格式文本。

    Args:
        old: 原始文件内容字符串。
        new: 修改后文件内容字符串。
        filename: 逻辑文件名，用于生成 --- a/<filename> / +++ b/<filename> 头。

    Returns:
        标准 Unified Diff 字符串。若 old == new 则返回空字符串。

    Notes:
        使用 splitlines(keepends=True) 保留原始换行符，保证 diff 对换行符
        敏感的场景（如 CRLF vs LF）不会静默丢失信息。

        当文件末尾无换行符时，difflib 会生成不带 '\\n' 的末行，这会导致
        unidiff 解析时报 "Hunk is shorter than expected"。此处在末行缺少
        换行符时追加标准的 '\\ No newline at end of file\\n' 标记，使 diff
        文本对 unidiff 完全合法，同时保留语义信息。
    """
    lines = list(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
        )
    )
    if not lines:
        return ""

    # difflib emits content lines without a trailing '\n' when the source
    # string has no trailing newline.  Patch parsers (incl. unidiff) expect
    # every content line to end with '\n', followed by an optional
    # '\ No newline at end of file\n' marker line.  We normalise here so
    # apply_diff always receives well-formed input.
    normalised: list[str] = []
    for line in lines:
        # Only content lines (context/added/removed) may lack a newline;
        # header lines (---, +++, @@) always have one from difflib.
        if line and line[0] in (" ", "+", "-") and not line.endswith("\n"):
            normalised.append(line + "\n")
            normalised.append("\\ No newline at end of file\n")
        else:
            normalised.append(line)

    return "".join(normalised)


def apply_diff(original_content: str, diff_text: str) -> str:
    """将 Unified Diff 文本应用到原始字符串，返回更新后内容。

    Args:
        original_content: 被打补丁的原始文件内容字符串。
        diff_text: 由 create_unified_diff（或兼容的 git diff）产生的
            Unified Diff 字符串。

    Returns:
        应用 diff 后的文件内容字符串。

    Raises:
        DiffApplyError: diff_text 为空、格式非法、或补丁与原始内容不匹配。

    Implementation notes:
        unidiff.PatchSet 将 diff 解析为结构化的 PatchedFile / Hunk / Line
        对象，比正则手解析更健壮。应用逻辑按行重建：保留上下文行和新增行，
        跳过被删除行，严格比对删除行与原始内容一致性。
    """
    if not diff_text.strip():
        raise DiffApplyError("diff_text is empty")

    try:
        patch_set = PatchSet(diff_text)
    except Exception as exc:
        raise DiffApplyError(f"Failed to parse diff: {exc}") from exc

    # unidiff silently accepts arbitrary text as an empty PatchSet;
    # a non-empty diff_text with zero patched files means the format is wrong.
    if not patch_set:
        if diff_text.strip():
            raise DiffApplyError(
                "diff_text is not empty but contains no valid patch hunks; "
                "check that it is a proper Unified Diff"
            )
        return original_content

    # 取第一个（也是唯一一个）被修改文件的补丁
    patched_file = patch_set[0]

    # 将原始内容按行分割，保留换行符以便精确重建
    original_lines = original_content.splitlines(keepends=True)

    result_lines: list[str] = []
    # 原始行的游标（0-indexed）
    src_cursor = 0

    for hunk in patched_file:
        # hunk.source_start 是 1-indexed；在抵达此 hunk 之前，
        # 先把游标前未涉及的原始行（上下文之前的部分）原样保留。
        hunk_src_start = hunk.source_start - 1  # 转换为 0-indexed

        # 将游标推进到 hunk 起始位置
        if src_cursor < hunk_src_start:
            result_lines.extend(original_lines[src_cursor:hunk_src_start])
            src_cursor = hunk_src_start

        for line in hunk:
            if line.is_context:
                # 上下文行：直接从原始内容取（保持换行符一致）
                if src_cursor < len(original_lines):
                    result_lines.append(original_lines[src_cursor])
                src_cursor += 1
            elif line.is_removed:
                # 删除行：跳过原始行，可选地做一致性校验
                if src_cursor < len(original_lines):
                    original_line_value = original_lines[src_cursor].rstrip("\n").rstrip("\r")
                    diff_line_value = line.value.rstrip("\n").rstrip("\r")
                    if original_line_value != diff_line_value:
                        raise DiffApplyError(
                            f"Patch mismatch at source line {src_cursor + 1}: "
                            f"expected {diff_line_value!r}, got {original_line_value!r}"
                        )
                src_cursor += 1
            elif line.is_added:
                # 新增行：写入结果，不推进 src_cursor
                result_lines.append(line.value)

    # hunk 处理完毕后，将剩余原始行追加到结果
    result_lines.extend(original_lines[src_cursor:])

    result = "".join(result_lines)

    # 如果 diff 表明目标文件末尾无换行符，去掉重建结果末尾多余的 \n
    # unidiff 在 patched_file 上提供 is_binary_file 但不直接暴露 no-newline；
    # 通过检查新文件末尾是否有 no-newline 标记来判断。
    target_no_newline = any(
        not line.is_added and not line.is_removed and not line.is_context
        for hunk in patched_file
        for line in hunk
    )
    if target_no_newline and result.endswith("\n"):
        result = result[:-1]

    return result
