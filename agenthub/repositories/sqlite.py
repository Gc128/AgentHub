import json
from datetime import UTC, datetime
from typing import Literal, cast

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine, select

from agenthub.core.errors import NotFoundError
from agenthub.models.conversation import ConversationRecord
from agenthub.models.message import MessageRecord
from agenthub.models.workspace import (
    AppliedDiffRecordRow,
    WorkspaceFileRecord,
    WorkspacePreviewRecord,
)
from agenthub.repositories.conversation_repo import (
    ConversationRepository,
    ConversationStatusFilter,
)
from agenthub.repositories.message_repo import MessageRepository
from agenthub.repositories.workspace_repo import WorkspaceRepository
from agenthub.schemas.artifact import Artifact
from agenthub.schemas.conversation import Conversation
from agenthub.schemas.message import Message
from agenthub.schemas.workspace import (
    AppliedDiffRecord,
    WorkspaceFileContent,
    WorkspacePreviewResponse,
)


class _SqliteRepositoryMixin:
    def __init__(self, database_url: str) -> None:
        self._engine = create_engine(database_url)
        SQLModel.metadata.create_all(self._engine)
        _ensure_conversation_columns(self._engine)
        _ensure_message_columns(self._engine)
        _ensure_workspace_preview_columns(self._engine)
        _ensure_applied_diff_columns(self._engine)


def _ensure_conversation_columns(engine: Engine) -> None:
    if not engine.url.get_backend_name().startswith("sqlite"):
        return

    with engine.begin() as connection:
        columns = connection.execute(text("PRAGMA table_info(conversationrecord)")).mappings()
        column_names = {str(column["name"]) for column in columns}
        if column_names and "status" not in column_names:
            connection.execute(
                text("ALTER TABLE conversationrecord ADD COLUMN status VARCHAR DEFAULT 'active'")
            )


def _ensure_message_columns(engine: Engine) -> None:
    if not engine.url.get_backend_name().startswith("sqlite"):
        return

    with engine.begin() as connection:
        columns = connection.execute(text("PRAGMA table_info(messagerecord)")).mappings()
        column_names = {str(column["name"]) for column in columns}
        if not column_names:
            return
        if "reply_to_id" not in column_names:
            connection.execute(text("ALTER TABLE messagerecord ADD COLUMN reply_to_id VARCHAR"))
        if "regenerated_from_id" not in column_names:
            connection.execute(
                text("ALTER TABLE messagerecord ADD COLUMN regenerated_from_id VARCHAR")
            )
        if "is_context_pinned" not in column_names:
            connection.execute(
                text("ALTER TABLE messagerecord ADD COLUMN is_context_pinned BOOLEAN DEFAULT 0")
            )
        if "deleted_at" not in column_names:
            connection.execute(text("ALTER TABLE messagerecord ADD COLUMN deleted_at DATETIME"))


def _ensure_workspace_preview_columns(engine: Engine) -> None:
    if not engine.url.get_backend_name().startswith("sqlite"):
        return

    with engine.begin() as connection:
        columns = connection.execute(text("PRAGMA table_info(workspacepreviewrecord)")).mappings()
        column_names = {str(column["name"]) for column in columns}
        if column_names and "entry_path" not in column_names:
            connection.execute(
                text("ALTER TABLE workspacepreviewrecord ADD COLUMN entry_path VARCHAR")
            )


def _ensure_applied_diff_columns(engine: Engine) -> None:
    if not engine.url.get_backend_name().startswith("sqlite"):
        return

    with engine.begin() as connection:
        columns = connection.execute(text("PRAGMA table_info(applieddiffrecordrow)")).mappings()
        column_names = {str(column["name"]) for column in columns}
        if not column_names:
            return
        if "before_content" not in column_names:
            connection.execute(
                text("ALTER TABLE applieddiffrecordrow ADD COLUMN before_content VARCHAR")
            )
        if "after_content" not in column_names:
            connection.execute(
                text("ALTER TABLE applieddiffrecordrow ADD COLUMN after_content VARCHAR")
            )
        if "before_exists" not in column_names:
            connection.execute(
                text("ALTER TABLE applieddiffrecordrow ADD COLUMN before_exists BOOLEAN DEFAULT 1")
            )
        if "reverted_at" not in column_names:
            connection.execute(
                text("ALTER TABLE applieddiffrecordrow ADD COLUMN reverted_at DATETIME")
            )


class SqliteConversationRepository(_SqliteRepositoryMixin, ConversationRepository):
    async def list(self, status: ConversationStatusFilter = "active") -> list[Conversation]:
        with Session(self._engine) as session:
            statement = select(ConversationRecord)
            if status != "all":
                statement = statement.where(ConversationRecord.status == status)
            records = session.exec(statement).all()
            conversations = [_conversation_from_record(record) for record in records]
            return sorted(conversations, key=lambda item: item.updated_at, reverse=True)

    async def get(self, conversation_id: str) -> Conversation:
        with Session(self._engine) as session:
            record = session.get(ConversationRecord, conversation_id)
            if record is None:
                raise NotFoundError("conversation_not_found", "Conversation does not exist.")
            return _conversation_from_record(record)

    async def save(self, conversation: Conversation) -> Conversation:
        with Session(self._engine) as session:
            session.merge(_conversation_to_record(conversation))
            session.commit()
            return conversation

    async def delete(self, conversation_id: str) -> None:
        with Session(self._engine) as session:
            record = session.get(ConversationRecord, conversation_id)
            if record is None:
                raise NotFoundError("conversation_not_found", "Conversation does not exist.")
            session.delete(record)
            session.commit()

    async def exists(self, conversation_id: str) -> bool:
        with Session(self._engine) as session:
            return session.get(ConversationRecord, conversation_id) is not None


class SqliteMessageRepository(_SqliteRepositoryMixin, MessageRepository):
    async def list_by_conversation(self, conversation_id: str) -> list[Message]:
        with Session(self._engine) as session:
            records = session.exec(
                select(MessageRecord).where(MessageRecord.conversation_id == conversation_id)
            ).all()
            messages = [_message_from_record(record) for record in records]
            return sorted(messages, key=lambda item: item.created_at)

    async def list_pinned_by_conversation(self, conversation_id: str) -> list[Message]:
        with Session(self._engine) as session:
            records = session.exec(
                select(MessageRecord).where(
                    MessageRecord.conversation_id == conversation_id,
                    MessageRecord.is_context_pinned == True,  # noqa: E712
                )
            ).all()
            messages = [_message_from_record(record) for record in records]
            active_messages = [message for message in messages if message.deleted_at is None]
            return sorted(active_messages, key=lambda item: item.created_at)

    async def get(self, conversation_id: str, message_id: str) -> Message:
        with Session(self._engine) as session:
            record = session.get(MessageRecord, message_id)
            if record is None or record.conversation_id != conversation_id:
                raise NotFoundError("message_not_found", "Message does not exist.")
            return _message_from_record(record)

    async def save(self, message: Message) -> Message:
        with Session(self._engine) as session:
            session.merge(_message_to_record(message))
            session.commit()
            return message

    async def delete_by_conversation(self, conversation_id: str) -> None:
        with Session(self._engine) as session:
            records = session.exec(
                select(MessageRecord).where(MessageRecord.conversation_id == conversation_id)
            ).all()
            for record in records:
                session.delete(record)
            session.commit()


class SqliteWorkspaceRepository(_SqliteRepositoryMixin, WorkspaceRepository):
    async def get_preview(self, workspace_id: str) -> WorkspacePreviewResponse:
        with Session(self._engine) as session:
            record = session.get(WorkspacePreviewRecord, workspace_id)
            if record is None:
                return WorkspacePreviewResponse(workspace_id=workspace_id, status="not_started")
            return WorkspacePreviewResponse(
                workspace_id=record.workspace_id,
                status=record.status,
                preview_url=record.preview_url,
                entry_path=record.entry_path,
            )

    async def save_preview(
        self,
        preview: WorkspacePreviewResponse,
    ) -> WorkspacePreviewResponse:
        with Session(self._engine) as session:
            session.merge(
                WorkspacePreviewRecord(
                    workspace_id=preview.workspace_id,
                    status=preview.status,
                    preview_url=preview.preview_url,
                    entry_path=preview.entry_path,
                )
            )
            session.commit()
            return preview

    async def list_files(self, workspace_id: str) -> list[WorkspaceFileContent]:
        with Session(self._engine) as session:
            records = session.exec(
                select(WorkspaceFileRecord)
                .where(WorkspaceFileRecord.workspace_id == workspace_id)
                .order_by(WorkspaceFileRecord.path)
            ).all()
            return [_workspace_file_from_record(record) for record in records]

    async def get_file(self, workspace_id: str, path: str) -> WorkspaceFileContent:
        with Session(self._engine) as session:
            record = session.get(WorkspaceFileRecord, _workspace_file_id(workspace_id, path))
            if record is None:
                raise NotFoundError("workspace_file_not_found", "Workspace file does not exist.")
            return _workspace_file_from_record(record)

    async def get_file_content_or_empty(self, workspace_id: str, path: str) -> str:
        with Session(self._engine) as session:
            record = session.get(WorkspaceFileRecord, _workspace_file_id(workspace_id, path))
            return record.content if record is not None else ""

    async def save_file(self, file_record: WorkspaceFileContent) -> WorkspaceFileContent:
        with Session(self._engine) as session:
            session.merge(_workspace_file_to_record(file_record))
            session.commit()
            return file_record

    async def delete_file(self, workspace_id: str, path: str) -> None:
        with Session(self._engine) as session:
            record = session.get(WorkspaceFileRecord, _workspace_file_id(workspace_id, path))
            if record is not None:
                session.delete(record)
                session.commit()

    async def list_applied_diffs(self, workspace_id: str) -> list[AppliedDiffRecord]:
        with Session(self._engine) as session:
            records = session.exec(
                select(AppliedDiffRecordRow).where(
                    AppliedDiffRecordRow.workspace_id == workspace_id
                )
            ).all()
            applied_diffs = [_applied_diff_from_record(record) for record in records]
            return sorted(applied_diffs, key=lambda item: item.applied_at)

    async def save_applied_diff(self, record: AppliedDiffRecord) -> AppliedDiffRecord:
        with Session(self._engine) as session:
            session.merge(_applied_diff_to_record(record))
            session.commit()
            return record


def _conversation_to_record(conversation: Conversation) -> ConversationRecord:
    return ConversationRecord(
        id=conversation.id,
        title=conversation.title,
        mode=conversation.mode,
        agent_ids_json=json.dumps(conversation.agent_ids),
        status=conversation.status,
        is_pinned=conversation.is_pinned,
        workspace_id=conversation.workspace_id,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


def _conversation_from_record(record: ConversationRecord) -> Conversation:
    agent_ids = json.loads(record.agent_ids_json)
    return Conversation(
        id=record.id,
        title=record.title,
        mode=cast(Literal["single", "group"], record.mode),
        agent_ids=[str(agent_id) for agent_id in agent_ids] if isinstance(agent_ids, list) else [],
        status=cast(Literal["active", "archived"], record.status or "active"),
        is_pinned=record.is_pinned,
        workspace_id=record.workspace_id,
        created_at=_ensure_utc(record.created_at),
        updated_at=_ensure_utc(record.updated_at),
    )


def _message_to_record(message: Message) -> MessageRecord:
    return MessageRecord(
        id=message.id,
        conversation_id=message.conversation_id,
        role=message.role,
        sender_id=message.sender_id,
        content=message.content,
        artifacts_json=json.dumps(
            [artifact.model_dump(mode="json") for artifact in message.artifacts],
            ensure_ascii=False,
        ),
        reply_to_id=message.reply_to_id,
        regenerated_from_id=message.regenerated_from_id,
        is_context_pinned=message.is_context_pinned,
        deleted_at=message.deleted_at,
        created_at=message.created_at,
    )


def _message_from_record(record: MessageRecord) -> Message:
    artifacts_payload = json.loads(record.artifacts_json)
    artifacts = (
        [Artifact.model_validate(item) for item in artifacts_payload]
        if isinstance(artifacts_payload, list)
        else []
    )
    return Message(
        id=record.id,
        conversation_id=record.conversation_id,
        role=cast(Literal["user", "agent", "system"], record.role),
        sender_id=record.sender_id,
        content=record.content,
        artifacts=artifacts,
        reply_to_id=record.reply_to_id,
        regenerated_from_id=record.regenerated_from_id,
        is_context_pinned=record.is_context_pinned,
        deleted_at=_ensure_utc(record.deleted_at) if record.deleted_at else None,
        created_at=_ensure_utc(record.created_at),
    )


def _workspace_file_id(workspace_id: str, path: str) -> str:
    return f"{workspace_id}:{path}"


def _workspace_file_to_record(file_record: WorkspaceFileContent) -> WorkspaceFileRecord:
    return WorkspaceFileRecord(
        id=_workspace_file_id(file_record.workspace_id, file_record.path),
        workspace_id=file_record.workspace_id,
        path=file_record.path,
        content=file_record.content,
        updated_at=file_record.updated_at,
    )


def _workspace_file_from_record(record: WorkspaceFileRecord) -> WorkspaceFileContent:
    return WorkspaceFileContent(
        workspace_id=record.workspace_id,
        path=record.path,
        content=record.content,
        updated_at=_ensure_utc(record.updated_at),
    )


def _applied_diff_to_record(record: AppliedDiffRecord) -> AppliedDiffRecordRow:
    return AppliedDiffRecordRow(
        id=record.id,
        workspace_id=record.workspace_id,
        artifact_id=record.artifact_id,
        diff=record.diff,
        path=record.path,
        before_content=record.before_content,
        after_content=record.after_content,
        before_exists=record.before_exists,
        reverted_at=record.reverted_at,
        applied_at=record.applied_at,
    )


def _applied_diff_from_record(record: AppliedDiffRecordRow) -> AppliedDiffRecord:
    return AppliedDiffRecord(
        id=record.id,
        workspace_id=record.workspace_id,
        artifact_id=record.artifact_id,
        diff=record.diff,
        path=record.path,
        before_content=record.before_content,
        after_content=record.after_content,
        before_exists=record.before_exists,
        reverted_at=_ensure_utc(record.reverted_at) if record.reverted_at else None,
        applied_at=_ensure_utc(record.applied_at),
    )


def _ensure_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value
