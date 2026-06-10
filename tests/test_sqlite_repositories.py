import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from agenthub.core.errors import NotFoundError
from agenthub.repositories.sqlite import (
    SqliteConversationRepository,
    SqliteCustomAgentRepository,
    SqliteMessageRepository,
    SqliteWorkspaceRepository,
)
from agenthub.schemas.artifact import Artifact
from agenthub.schemas.conversation import Conversation
from agenthub.schemas.custom_agent import CustomAgent
from agenthub.schemas.message import Message
from agenthub.schemas.workspace import (
    AppliedDiffRecord,
    WorkspaceFileContent,
    WorkspacePreviewResponse,
)


def sqlite_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'agenthub-test.db'}"


@pytest.mark.asyncio
async def test_sqlite_conversation_repository_persists_agent_ids_and_pin(
    tmp_path: Path,
) -> None:
    repository = SqliteConversationRepository(sqlite_url(tmp_path))
    now = datetime.now(UTC)
    conversation = Conversation(
        id="conv_sqlite",
        title="SQLite Demo",
        mode="group",
        agent_ids=["orchestrator", "code-agent"],
        is_pinned=True,
        workspace_id="ws_sqlite",
        created_at=now,
        updated_at=now,
    )

    await repository.save(conversation)

    fetched = await repository.get("conv_sqlite")
    assert fetched.agent_ids == ["orchestrator", "code-agent"]
    assert fetched.is_pinned is True
    assert fetched.status == "active"
    assert [item.id for item in await repository.list()] == ["conv_sqlite"]

    archived = fetched.model_copy(update={"status": "archived"})
    await repository.save(archived)
    assert await repository.list() == []
    assert [item.id for item in await repository.list(status="archived")] == ["conv_sqlite"]
    assert [item.id for item in await repository.list(status="all")] == ["conv_sqlite"]

    await repository.delete("conv_sqlite")
    assert await repository.exists("conv_sqlite") is False


@pytest.mark.asyncio
async def test_sqlite_message_repository_persists_artifacts(tmp_path: Path) -> None:
    repository = SqliteMessageRepository(sqlite_url(tmp_path))
    now = datetime.now(UTC)
    message = Message(
        id="msg_sqlite",
        conversation_id="conv_sqlite",
        role="agent",
        sender_id="code-agent",
        content="generated",
        artifacts=[
            Artifact(
                id="artifact_sqlite",
                type="code",
                title="Code",
                data={"filename": "src/App.tsx"},
            )
        ],
        reply_to_id="msg_parent",
        regenerated_from_id="msg_user",
        is_context_pinned=True,
        created_at=now,
    )

    await repository.save(message)

    messages = await repository.list_by_conversation("conv_sqlite")
    assert messages == [message]
    assert await repository.get("conv_sqlite", "msg_sqlite") == message
    assert await repository.list_pinned_by_conversation("conv_sqlite") == [message]

    unpinned = message.model_copy(update={"is_context_pinned": False})
    await repository.save(unpinned)
    assert await repository.list_by_conversation("conv_sqlite") == [unpinned]
    assert await repository.list_pinned_by_conversation("conv_sqlite") == []

    await repository.delete_by_conversation("conv_sqlite")
    assert await repository.list_by_conversation("conv_sqlite") == []


@pytest.mark.asyncio
async def test_sqlite_custom_agent_repository_persists_agents(tmp_path: Path) -> None:
    database_url = sqlite_url(tmp_path)
    repository = SqliteCustomAgentRepository(database_url)
    now = datetime.now(UTC)
    agent = CustomAgent(
        id="custom-agent-sqlite",
        name="需求澄清 Agent",
        description="clarify",
        system_prompt="提出三个澄清问题。",
        backend_id="codex-cli",
        capabilities=["clarify", "product"],
        is_enabled=True,
        created_at=now,
        updated_at=now,
    )

    await repository.save(agent)

    fetched = await repository.get(agent.id)
    assert fetched == agent
    assert await repository.list_enabled() == [agent]

    disabled = agent.model_copy(update={"is_enabled": False})
    await repository.save(disabled)
    reloaded_repository = SqliteCustomAgentRepository(database_url)
    assert await reloaded_repository.list() == [disabled]
    assert await reloaded_repository.list_enabled() == []

    await reloaded_repository.delete(agent.id)
    assert await reloaded_repository.list() == []


@pytest.mark.asyncio
async def test_sqlite_workspace_repository_persists_preview_files_and_diffs(
    tmp_path: Path,
) -> None:
    repository = SqliteWorkspaceRepository(sqlite_url(tmp_path))
    now = datetime.now(UTC)

    await repository.save_preview(
        WorkspacePreviewResponse(
            workspace_id="ws_sqlite",
            status="ready",
            preview_url="http://example.test/preview",
            entry_path="todo.html",
        )
    )
    preview = await repository.get_preview("ws_sqlite")
    assert preview.preview_url == "http://example.test/preview"
    assert preview.entry_path == "todo.html"

    file_record = WorkspaceFileContent(
        workspace_id="ws_sqlite",
        path="src/App.tsx",
        content="export default null\n",
        updated_at=now,
    )
    await repository.save_file(file_record)

    assert await repository.get_file("ws_sqlite", "src/App.tsx") == file_record
    assert await repository.get_file_content_or_empty("ws_sqlite", "src/App.tsx") == (
        "export default null\n"
    )
    assert [item.path for item in await repository.list_files("ws_sqlite")] == ["src/App.tsx"]

    await repository.delete_file("ws_sqlite", "src/App.tsx")
    assert await repository.list_files("ws_sqlite") == []
    with pytest.raises(NotFoundError, match="Workspace file does not exist"):
        await repository.get_file("ws_sqlite", "src/App.tsx")

    diff_record = AppliedDiffRecord(
        id="apply_sqlite",
        workspace_id="ws_sqlite",
        artifact_id="artifact_diff",
        diff="--- a/src/App.tsx\n+++ b/src/App.tsx\n",
        path="src/App.tsx",
        applied_at=now,
    )
    await repository.save_applied_diff(diff_record)

    assert await repository.list_applied_diffs("ws_sqlite") == [diff_record]


@pytest.mark.asyncio
async def test_sqlite_workspace_repository_migrates_preview_entry_path(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "agenthub-test.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "CREATE TABLE workspacepreviewrecord ("
            "workspace_id VARCHAR NOT NULL, "
            "status VARCHAR NOT NULL, "
            "preview_url VARCHAR, "
            "PRIMARY KEY (workspace_id))"
        )
        connection.execute(
            "INSERT INTO workspacepreviewrecord "
            "(workspace_id, status, preview_url) VALUES (?, ?, ?)",
            ("ws_old", "ready", "http://example.test/old"),
        )

    repository = SqliteWorkspaceRepository(f"sqlite:///{database_path}")

    preview = await repository.get_preview("ws_old")
    assert preview.preview_url == "http://example.test/old"
    assert preview.entry_path is None

    await repository.save_preview(
        WorkspacePreviewResponse(
            workspace_id="ws_old",
            status="ready",
            preview_url="http://example.test/new",
            entry_path="todo.html",
        )
    )
    assert (await repository.get_preview("ws_old")).entry_path == "todo.html"
