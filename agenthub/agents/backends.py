from __future__ import annotations

from pathlib import Path
from shutil import which
from typing import cast

from agenthub.config import Settings
from agenthub.schemas.agent import AgentBackend, AgentBackendType

OPENAI_COMPATIBLE_BACKEND_ID = "openai-compatible"
CODEX_CLI_BACKEND_ID = "codex-cli"
CLAUDE_CODE_CLI_BACKEND_ID = "claude-code-cli"

KNOWN_BACKEND_IDS = frozenset(
    {
        OPENAI_COMPATIBLE_BACKEND_ID,
        CODEX_CLI_BACKEND_ID,
        CLAUDE_CODE_CLI_BACKEND_ID,
    }
)


def list_agent_backends(settings: Settings) -> list[AgentBackend]:
    return [
        AgentBackend(
            id=OPENAI_COMPATIBLE_BACKEND_ID,
            name="OpenAI-compatible LLM",
            type="openai-compatible",
            description="当前 AgentHub 默认 HTTP LLM 后端。",
            configured=bool(settings.openai_api_key),
            available=bool(settings.openai_api_key),
            model=settings.agent_model,
            capabilities=["chat", "structured-output", "code"],
            unavailable_reason=None if settings.openai_api_key else "OPENAI_API_KEY 未配置。",
        ),
        _cli_backend(
            backend_id=CODEX_CLI_BACKEND_ID,
            name="Codex",
            description="通过 codex exec 在临时 workspace 副本中运行。",
            command=settings.codex_cli_path,
        ),
        _cli_backend(
            backend_id=CLAUDE_CODE_CLI_BACKEND_ID,
            name="Claude Code CLI",
            description="通过 claude --print 在临时 workspace 副本中运行。",
            command=settings.claude_code_cli_path,
        ),
    ]


def backend_exists(backend_id: str) -> bool:
    return backend_id in KNOWN_BACKEND_IDS


def cli_command_for_backend(settings: Settings, backend_id: str) -> str:
    if backend_id == CODEX_CLI_BACKEND_ID:
        return settings.codex_cli_path
    if backend_id == CLAUDE_CODE_CLI_BACKEND_ID:
        return settings.claude_code_cli_path
    raise ValueError(f"Backend {backend_id!r} is not a CLI backend.")


def resolve_cli_executable(command: str) -> str | None:
    if not command.strip():
        return None
    command_path = Path(command)
    if command_path.parent != Path("."):
        return str(command_path) if command_path.exists() else None
    return which(command)


def _cli_backend(
    *,
    backend_id: str,
    name: str,
    description: str,
    command: str,
) -> AgentBackend:
    resolved = resolve_cli_executable(command)
    return AgentBackend(
        id=backend_id,
        name=name,
        type=cast(AgentBackendType, backend_id),
        description=description,
        configured=bool(command.strip()),
        available=resolved is not None,
        command=command,
        capabilities=["chat", "code", "workspace-diff"],
        unavailable_reason=None if resolved is not None else f"未找到命令：{command}",
    )
