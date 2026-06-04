"""
tests/test_git.py

git_init / git_status / git_add / git_commit / git_log 的单元测试。

每个测试函数使用 pytest 的 tmp_path fixture 获得独立临时目录，
避免测试之间相互影响，也不污染任何真实仓库。

Git 用户信息配置：
    git commit 需要 user.email 和 user.name。CI 环境可能没有全局配置，
    所以每个需要 commit 的测试都在临时仓库里用 git config --local 设置。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from agenthub.workspace.git import (
    CommitEntry,
    GitError,
    git_add,
    git_commit,
    git_init,
    git_log,
    git_status,
)

# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _configure_git_identity(repo: Path) -> None:
    """为临时仓库设置最小化 git 用户信息，避免 CI 环境报错。"""
    subprocess.run(
        ["git", "config", "user.email", "test@agenthub.test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "AgentHub Test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def _write(repo: Path, name: str, content: str = "hello\n") -> Path:
    """在仓库内写入文件，返回文件 Path。"""
    p = repo / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _init_repo(tmp_path: Path) -> Path:
    """初始化一个带 identity 的临时仓库，返回仓库 Path。"""
    repo = tmp_path / "repo"
    repo.mkdir()
    git_init(repo)
    _configure_git_identity(repo)
    return repo


def _commit_file(repo: Path, filename: str, content: str, message: str) -> None:
    """写文件 → add → commit 一步到位。"""
    _write(repo, filename, content)
    git_add(repo, filename)
    git_commit(repo, message)


# ---------------------------------------------------------------------------
# git_init
# ---------------------------------------------------------------------------


class TestGitInit:
    def test_creates_git_dir(self, tmp_path: Path) -> None:
        repo = tmp_path / "newrepo"
        repo.mkdir()
        git_init(repo)
        assert (repo / ".git").is_dir()

    def test_idempotent_on_existing_repo(self, tmp_path: Path) -> None:
        repo = tmp_path / "existing"
        repo.mkdir()
        git_init(repo)
        git_init(repo)  # 再次 init 不应报错
        assert (repo / ".git").is_dir()

    def test_raises_on_nonexistent_directory(self, tmp_path: Path) -> None:
        bad = tmp_path / "does_not_exist"
        with pytest.raises(GitError):
            git_init(bad)


# ---------------------------------------------------------------------------
# git_status
# ---------------------------------------------------------------------------


class TestGitStatus:
    def test_clean_repo_shows_nothing_to_commit(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _commit_file(repo, "a.txt", "content\n", "initial")
        output = git_status(repo)
        assert "nothing to commit" in output

    def test_untracked_file_appears_in_status(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _write(repo, "untracked.txt")
        output = git_status(repo)
        assert "untracked.txt" in output

    def test_staged_file_appears_in_status(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _write(repo, "staged.txt")
        git_add(repo, "staged.txt")
        output = git_status(repo)
        assert "staged.txt" in output

    def test_short_flag_returns_compact_output(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _write(repo, "f.txt")
        output = git_status(repo, short=True)
        # short 格式：每行以两字符状态码开头，如 "?? f.txt"
        assert "f.txt" in output
        assert "\n" not in output.rstrip("\n")  # 只有一行内容

    def test_returns_string(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        assert isinstance(git_status(repo), str)


# ---------------------------------------------------------------------------
# git_add
# ---------------------------------------------------------------------------


class TestGitAdd:
    def test_add_single_file(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _write(repo, "a.txt")
        git_add(repo, "a.txt")  # 不应抛出异常
        output = git_status(repo, short=True)
        assert "a.txt" in output
        # short 格式中暂存文件首字母非 '?'
        assert output.strip().startswith("A")

    def test_add_dot_stages_all(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _write(repo, "x.txt")
        _write(repo, "y.txt")
        git_add(repo, ".")
        output = git_status(repo, short=True)
        assert "x.txt" in output
        assert "y.txt" in output

    def test_add_multiple_files(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _write(repo, "p.txt")
        _write(repo, "q.txt")
        git_add(repo, "p.txt", "q.txt")
        output = git_status(repo, short=True)
        assert "p.txt" in output
        assert "q.txt" in output

    def test_add_no_paths_raises_value_error(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        with pytest.raises(ValueError, match="at least one path"):
            git_add(repo)

    def test_add_nonexistent_file_raises_git_error(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        with pytest.raises(GitError):
            git_add(repo, "ghost.txt")


# ---------------------------------------------------------------------------
# git_commit
# ---------------------------------------------------------------------------


class TestGitCommit:
    def test_commit_creates_entry_in_log(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _write(repo, "f.txt")
        git_add(repo, "f.txt")
        git_commit(repo, "first commit")
        entries = git_log(repo)
        assert len(entries) == 1
        assert entries[0].subject == "first commit"

    def test_empty_message_raises_value_error(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _write(repo, "f.txt")
        git_add(repo, "f.txt")
        with pytest.raises(ValueError, match="must not be empty"):
            git_commit(repo, "")

    def test_whitespace_only_message_raises_value_error(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        with pytest.raises(ValueError):
            git_commit(repo, "   \n  ")

    def test_commit_nothing_staged_raises_git_error(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        # 没有 add 任何文件，commit 应失败
        with pytest.raises(GitError):
            git_commit(repo, "empty commit")

    def test_multiline_message_preserved(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _write(repo, "f.txt")
        git_add(repo, "f.txt")
        msg = "feat: add feature\n\nDetailed description here."
        git_commit(repo, msg)
        entries = git_log(repo)
        assert entries[0].subject == "feat: add feature"
        assert "Detailed description here." in entries[0].body

    def test_message_with_special_chars(self, tmp_path: Path) -> None:
        """commit message 含引号和特殊字符，不应触发 shell 注入。"""
        repo = _init_repo(tmp_path)
        _write(repo, "f.txt")
        git_add(repo, "f.txt")
        evil_msg = 'fix: handle "quoted" & <special> chars; $(echo owned)'
        git_commit(repo, evil_msg)
        entries = git_log(repo)
        assert entries[0].subject == evil_msg


# ---------------------------------------------------------------------------
# git_log
# ---------------------------------------------------------------------------


class TestGitLog:
    def test_empty_repo_returns_empty_list(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        assert git_log(repo) == []

    def test_single_commit_returns_one_entry(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _commit_file(repo, "a.txt", "x\n", "only commit")
        entries = git_log(repo)
        assert len(entries) == 1

    def test_entry_is_commit_entry_dataclass(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _commit_file(repo, "a.txt", "x\n", "test entry type")
        entry = git_log(repo)[0]
        assert isinstance(entry, CommitEntry)

    def test_entry_fields_populated(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _commit_file(repo, "a.txt", "x\n", "check fields")
        entry = git_log(repo)[0]
        assert len(entry.hash) == 40  # SHA-1 full hash
        assert "@" in entry.author or entry.author  # 作者名
        assert entry.date  # 日期不为空
        assert entry.subject == "check fields"

    def test_multiple_commits_ordered_newest_first(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _commit_file(repo, "a.txt", "1\n", "first")
        _commit_file(repo, "b.txt", "2\n", "second")
        _commit_file(repo, "c.txt", "3\n", "third")
        entries = git_log(repo)
        assert [e.subject for e in entries] == ["third", "second", "first"]

    def test_max_count_limits_results(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        for i in range(5):
            _commit_file(repo, f"{i}.txt", f"{i}\n", f"commit {i}")
        entries = git_log(repo, max_count=3)
        assert len(entries) == 3

    def test_max_count_less_than_one_raises(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        with pytest.raises(ValueError, match="max_count"):
            git_log(repo, max_count=0)

    def test_subject_with_special_chars(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        subject = 'fix: handle "quotes" & <xml> tags'
        _commit_file(repo, "a.txt", "x\n", subject)
        assert git_log(repo)[0].subject == subject


# ---------------------------------------------------------------------------
# GitError 结构校验
# ---------------------------------------------------------------------------


class TestGitError:
    def test_is_runtime_error_subclass(self, tmp_path: Path) -> None:
        repo = tmp_path / "norepo"
        repo.mkdir()
        with pytest.raises(RuntimeError):
            # status 在非 git 目录下会失败
            git_status(repo)

    def test_error_has_returncode(self, tmp_path: Path) -> None:
        repo = tmp_path / "norepo"
        repo.mkdir()
        try:
            git_status(repo)
        except GitError as exc:
            assert exc.returncode is not None
            assert exc.returncode != 0

    def test_error_has_stderr(self, tmp_path: Path) -> None:
        repo = tmp_path / "norepo"
        repo.mkdir()
        try:
            git_status(repo)
        except GitError as exc:
            assert isinstance(exc.stderr, str)

    def test_error_has_command(self, tmp_path: Path) -> None:
        repo = tmp_path / "norepo"
        repo.mkdir()
        try:
            git_status(repo)
        except GitError as exc:
            assert "git" in exc.command
            assert "status" in exc.command
