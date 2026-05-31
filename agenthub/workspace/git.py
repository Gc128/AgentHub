import subprocess
from pathlib import Path


class GitCommandError(RuntimeError):
    pass


def run_git(workspace_root: Path, args: list[str]) -> str:
    allowed = {"init", "status", "diff", "add", "commit", "log"}
    if not args or args[0] not in allowed:
        raise GitCommandError("Unsupported git command.")

    result = subprocess.run(
        ["git", *args],
        cwd=workspace_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "Git command failed."
        raise GitCommandError(message)
    return result.stdout
