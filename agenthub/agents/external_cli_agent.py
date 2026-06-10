from __future__ import annotations

import asyncio
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from agenthub.agents.backends import (
    CLAUDE_CODE_CLI_BACKEND_ID,
    CODEX_CLI_BACKEND_ID,
    cli_command_for_backend,
    resolve_cli_executable,
)
from agenthub.config import Settings
from agenthub.core.errors import AgentExecutionError
from agenthub.schemas.agent import AgentRunInput, AgentRunResult
from agenthub.schemas.artifact import Artifact
from agenthub.workspace.diff import create_unified_diff
from agenthub.workspace.manager import WorkspacePathError, resolve_workspace_path

_MAX_FILE_BYTES = 500_000
_SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__", "dist", "build"}
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


@dataclass(frozen=True)
class FileSnapshot:
    content: str


class ExternalCliAgentAdapter:
    capabilities = ["external-cli", "code", "workspace-diff"]

    def __init__(
        self,
        *,
        agent_id: str,
        name: str,
        backend_id: str,
        settings: Settings,
        system_prompt: str,
    ) -> None:
        self.id = agent_id
        self.name = name
        self.backend_id = backend_id
        self._settings = settings
        self._system_prompt = system_prompt

    async def run(self, input_data: AgentRunInput) -> AgentRunResult:
        command = cli_command_for_backend(self._settings, self.backend_id)
        executable = resolve_cli_executable(command)
        if executable is None:
            raise AgentExecutionError(
                f"{self.name} 后端不可用：未找到命令 {command!r}。请检查 .env 中的 CLI 路径。"
            )

        with tempfile.TemporaryDirectory(prefix="agenthub-cli-") as temp_dir:
            temp_workspace = Path(temp_dir) / "workspace"
            self._prepare_workspace_copy(input_data.workspace_id, temp_workspace)
            before = _snapshot_workspace(temp_workspace)
            output = await self._run_cli(executable, temp_workspace, input_data)
            after = _snapshot_workspace(temp_workspace)

        artifacts = _artifacts_from_snapshots(
            before=before,
            after=after,
            workspace_id=input_data.workspace_id,
            agent_id=self.id,
            backend_id=self.backend_id,
        )
        content = _clean_output(output).strip()
        if not content and artifacts:
            content = f"{self.name} 已完成代码修改，已生成可应用的 diff。"
        if not content:
            content = f"{self.name} 已完成执行，但没有返回文本输出。"

        return AgentRunResult(
            agent_id=self.id,
            content=content,
            artifacts=artifacts,
            next_actions=[],
        )

    def _prepare_workspace_copy(self, workspace_id: str, target: Path) -> None:
        source = self._workspace_dir(workspace_id)
        if source.exists():
            shutil.copytree(source, target, ignore=shutil.ignore_patterns(*_SKIP_DIRS))
            return
        target.mkdir(parents=True, exist_ok=True)

    def _workspace_dir(self, workspace_id: str) -> Path:
        try:
            return resolve_workspace_path(self._settings.workspace_root, workspace_id)
        except WorkspacePathError as exc:
            raise AgentExecutionError(f"Invalid workspace_id for CLI backend: {exc}") from exc

    async def _run_cli(
        self,
        executable: str,
        workspace: Path,
        input_data: AgentRunInput,
    ) -> str:
        args = self._command_args(executable, workspace, input_data)
        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                cwd=workspace,
                env=_safe_cli_env(self._settings),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as exc:
            raise AgentExecutionError(f"{self.name} CLI 启动失败：{exc}") from exc

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=self._settings.agent_cli_timeout_seconds,
            )
        except TimeoutError as exc:
            process.kill()
            await process.wait()
            raise AgentExecutionError(
                f"{self.name} CLI 执行超时（{self._settings.agent_cli_timeout_seconds:g}s）。"
            ) from exc

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        if process.returncode != 0:
            detail = _truncate_text(_clean_output(stderr or stdout), 2000)
            raise AgentExecutionError(
                f"{self.name} CLI 执行失败（exit {process.returncode}）。{detail}"
            )
        return _truncate_text(stdout, self._settings.agent_cli_max_output_chars)

    def _command_args(
        self,
        executable: str,
        workspace: Path,
        input_data: AgentRunInput,
    ) -> list[str]:
        prompt = _build_cli_prompt(
            system_prompt=self._system_prompt,
            user_message=input_data.user_message,
            context=input_data.context,
        )
        if self.backend_id == CODEX_CLI_BACKEND_ID:
            return [
                executable,
                "exec",
                "--cd",
                str(workspace),
                "--sandbox",
                "workspace-write",
                "--skip-git-repo-check",
                "--ephemeral",
                "--ignore-user-config",
                "--ignore-rules",
                "--color",
                "never",
                prompt,
            ]
        if self.backend_id == CLAUDE_CODE_CLI_BACKEND_ID:
            args = [
                executable,
                "--print",
                "--output-format",
                "text",
                "--no-session-persistence",
                "--permission-mode",
                "acceptEdits",
                "--system-prompt",
                self._system_prompt,
                prompt,
            ]
            if self._settings.anthropic_api_key:
                args.insert(1, "--bare")
            return args
        raise AgentExecutionError(f"Unsupported CLI backend: {self.backend_id}")


def _build_cli_prompt(
    *,
    system_prompt: str,
    user_message: str,
    context: dict[str, object],
) -> str:
    user_request = context.get("user_request") or user_message
    instruction = context.get("instruction")
    parts = [
        system_prompt,
        "",
        "You are running in a temporary copy of an AgentHub workspace.",
        "If the task asks for code, edit files inside the current working directory only.",
        "Do not say that changes were applied to the real workspace; AgentHub will present diffs.",
        "",
        f"User request:\n{user_request}",
    ]
    if isinstance(instruction, str) and instruction.strip():
        parts.append(f"Agent instruction:\n{instruction}")
    return "\n".join(parts)


def _safe_cli_env(settings: Settings) -> dict[str, str]:
    allowed_prefixes = ("CODEX_", "CLAUDE_", "ANTHROPIC_", "OPENAI_")
    allowed_names = {"HOME", "PATH", "SHELL", "TMPDIR", "USER", "LANG", "LC_ALL"}
    env: dict[str, str] = {}
    for key, value in os.environ.items():
        if key in allowed_names or key.startswith(allowed_prefixes):
            env[key] = value
    if settings.openai_api_key:
        env.setdefault("OPENAI_API_KEY", settings.openai_api_key)
    if settings.anthropic_api_key:
        env.setdefault("ANTHROPIC_API_KEY", settings.anthropic_api_key)
    return env


def _snapshot_workspace(root: Path) -> dict[str, FileSnapshot]:
    snapshot: dict[str, FileSnapshot] = {}
    if not root.exists():
        return snapshot
    for path in root.rglob("*"):
        if not path.is_file() or _should_skip(path, root):
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if len(data) > _MAX_FILE_BYTES or b"\x00" in data:
            continue
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        snapshot[path.relative_to(root).as_posix()] = FileSnapshot(content=content)
    return snapshot


def _should_skip(path: Path, root: Path) -> bool:
    relative_parts = path.relative_to(root).parts
    return any(part in _SKIP_DIRS for part in relative_parts)


def _artifacts_from_snapshots(
    *,
    before: dict[str, FileSnapshot],
    after: dict[str, FileSnapshot],
    workspace_id: str,
    agent_id: str,
    backend_id: str,
) -> list[Artifact]:
    artifacts: list[Artifact] = []
    changed_paths = sorted(
        path for path in set(before) | set(after) if before.get(path) != after.get(path)
    )
    for path in changed_paths:
        old = before.get(path, FileSnapshot(content="")).content
        new = after.get(path, FileSnapshot(content="")).content
        language = _language_for_path(path)
        artifacts.append(
            Artifact(
                id=f"artifact-{agent_id}-code-{_slug_path(path)}",
                type="code",
                title=path,
                data={
                    "filename": path,
                    "language": language,
                    "content": new,
                    "workspace_id": workspace_id,
                    "source_backend": backend_id,
                },
            )
        )
        diff = create_unified_diff(old, new, path)
        if diff.strip():
            artifacts.append(
                Artifact(
                    id=f"artifact-{agent_id}-diff-{_slug_path(path)}",
                    type="diff",
                    title=f"Diff for {path}",
                    data={
                        "filename": path,
                        "diff": diff,
                        "workspace_id": workspace_id,
                        "source_backend": backend_id,
                    },
                )
            )
    return artifacts


def _language_for_path(path: str) -> str:
    suffix = Path(path).suffix.lower().lstrip(".")
    return {
        "js": "javascript",
        "jsx": "jsx",
        "ts": "typescript",
        "tsx": "tsx",
        "py": "python",
        "html": "html",
        "css": "css",
        "md": "markdown",
        "json": "json",
    }.get(suffix, suffix or "text")


def _slug_path(path: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", path).strip("-") or "file"


def _clean_output(value: str) -> str:
    return _ANSI_RE.sub("", value).strip()


def _truncate_text(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    return value[:max_chars].rstrip() + "\n\n[output truncated]"
