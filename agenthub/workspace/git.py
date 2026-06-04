"""
agenthub/workspace/git.py

Workspace Git 操作封装模块。

职责：
- 封装 git init / status / add / commit / log 命令
- 所有命令以列表形式传参（严禁 shell=True 或拼接字符串）
- 命令均在指定 workspace 目录下执行（cwd 参数）
- 捕获执行错误并抛出带清晰信息的 GitError 异常

本模块不涉及 FastAPI 集成，也不处理复杂的冲突合并逻辑。
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------


class GitError(RuntimeError):
    """Git 命令执行失败时抛出。

    属性:
        command: 执行失败的命令列表（已做安全脱敏，不含密钥）。
        returncode: 进程退出码。
        stderr: 标准错误输出。
    """

    def __init__(
        self,
        message: str,
        *,
        command: list[str] | None = None,
        returncode: int | None = None,
        stderr: str = "",
    ) -> None:
        super().__init__(message)
        self.command = command or []
        self.returncode = returncode
        self.stderr = stderr


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------

_GIT = "git"
_DEFAULT_TIMEOUT = 30  # 秒


def _run(
    args: list[str],
    cwd: Path,
    timeout: int = _DEFAULT_TIMEOUT,
) -> subprocess.CompletedProcess[str]:
    """执行 git 子命令，统一处理错误。

    Args:
        args: git 之后的参数列表，例如 ["status", "--short"]。
        cwd: 命令执行目录（workspace 根目录）。
        timeout: 超时秒数，防止命令挂起。

    Returns:
        CompletedProcess，stdout 已解码为 str。

    Raises:
        GitError: returncode 非零、超时、或找不到 git 可执行文件。
    """
    cmd = [_GIT, *args]
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            # 明确不使用 shell=True，防止注入
        )
    except FileNotFoundError as exc:
        raise GitError(
            "git executable not found; ensure git is installed and in PATH",
            command=cmd,
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise GitError(
            f"git command timed out after {timeout}s: {' '.join(cmd)}",
            command=cmd,
        ) from exc

    if result.returncode != 0:
        # stderr 可能含有敏感路径，但不含密钥；直接透传以便调试
        raise GitError(
            f"git {args[0]!r} failed (exit {result.returncode}): {result.stderr.strip()}",
            command=cmd,
            returncode=result.returncode,
            stderr=result.stderr,
        )

    return result


# ---------------------------------------------------------------------------
# 公开接口
# ---------------------------------------------------------------------------


def git_init(workspace_path: Path) -> None:
    """在指定目录初始化 Git 仓库。

    如果目录已经是 Git 仓库，git init 是幂等的，不会报错。

    Args:
        workspace_path: 要初始化的目录路径。

    Raises:
        GitError: 初始化失败。
    """
    _run(["init"], cwd=workspace_path)


def git_status(workspace_path: Path, *, short: bool = False) -> str:
    """返回工作区状态文本。

    Args:
        workspace_path: workspace 根目录。
        short: 若为 True，使用 --short 格式，便于程序解析。

    Returns:
        git status 的 stdout 字符串。

    Raises:
        GitError: 命令执行失败。
    """
    args = ["status"]
    if short:
        args.append("--short")
    result = _run(args, cwd=workspace_path)
    return result.stdout


def git_add(workspace_path: Path, *paths: str) -> None:
    """将文件加入暂存区。

    Args:
        workspace_path: workspace 根目录。
        *paths: 要 add 的路径（相对于 workspace_path）。
            传入 "." 表示 add 所有变更。
            每个路径必须是字符串，不允许传入 shell glob 展开后的列表。

    Raises:
        ValueError: 未提供任何路径。
        GitError: 命令执行失败。

    Security:
        paths 各项作为独立参数传入列表，不做字符串拼接，
        不会被 shell 解释，防止注入攻击。
    """
    if not paths:
        raise ValueError("git_add requires at least one path argument")
    _run(["add", "--", *paths], cwd=workspace_path)


def git_commit(workspace_path: Path, message: str) -> None:
    """提交暂存区变更。

    Args:
        workspace_path: workspace 根目录。
        message: commit message，不可为空。

    Raises:
        ValueError: message 为空字符串或纯空白。
        GitError: 命令执行失败（如暂存区为空）。

    Security:
        message 作为 -m 参数的独立列表项传入，不做字符串拼接，
        不会被 shell 解析或执行。
    """
    if not message or not message.strip():
        raise ValueError("commit message must not be empty")
    _run(["commit", "-m", message], cwd=workspace_path)


@dataclass
class CommitEntry:
    """单条 git log 记录的结构化表示。"""

    hash: str
    author: str
    date: str
    subject: str
    body: str = field(default="")


def git_log(
    workspace_path: Path,
    *,
    max_count: int = 10,
) -> list[CommitEntry]:
    """返回结构化的提交历史列表。

    使用固定的 --format 分隔符解析，避免手写正则匹配自由格式文本。

    Args:
        workspace_path: workspace 根目录。
        max_count: 最多返回的提交数量，默认 10。

    Returns:
        CommitEntry 列表，最新提交在前。空仓库返回空列表。

    Raises:
        ValueError: max_count 小于 1。
        GitError: 命令执行失败。
    """
    if max_count < 1:
        raise ValueError(f"max_count must be >= 1, got {max_count}")

    # Use git's own escape sequences (%x1E = RS, %x1F = US) as delimiters
    # so no raw control characters appear in the subprocess args list
    # (Linux execve rejects NUL bytes in argv; RS/US are safe visually
    # and never appear in normal commit metadata).
    #
    # Record format per commit:
    #   <hash> RS <author> RS <date> RS <subject> RS <body> US
    #
    # tformat: (trailer format) appends the terminator after EACH record,
    # making splitting unambiguous even for empty bodies.
    _RS = "\x1e"  # Record Separator (output side, after git expands %x1E)
    _US = "\x1f"  # Unit Separator  (output side, after git expands %x1F)

    fmt = "%H%x1E%an%x1E%ai%x1E%s%x1E%b%x1F"

    try:
        result = _run(
            ["log", f"--max-count={max_count}", f"--format=tformat:{fmt}"],
            cwd=workspace_path,
        )
    except GitError as exc:
        # Freshly initialised repo with no commits yet
        if "does not have any commits" in exc.stderr or "fatal: your current branch" in exc.stderr:
            return []
        raise

    entries: list[CommitEntry] = []
    for record in result.stdout.split(_US):
        record = record.strip()
        if not record:
            continue
        parts = record.split(_RS, maxsplit=4)
        if len(parts) < 4:
            continue  # defensive: malformed record
        entries.append(
            CommitEntry(
                hash=parts[0].strip(),
                author=parts[1].strip(),
                date=parts[2].strip(),
                subject=parts[3].strip(),
                body=parts[4].strip() if len(parts) > 4 else "",
            )
        )

    return entries
