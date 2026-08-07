from datetime import datetime

from sqlmodel import Field, SQLModel


class MessageRecord(SQLModel, table=True):
    id: str = Field(primary_key=True)
    conversation_id: str = Field(index=True)
    role: str
    sender_id: str
    content: str
    artifacts_json: str = "[]"
    reply_to_id: str | None = Field(default=None, index=True)
    regenerated_from_id: str | None = Field(default=None, index=True)
    is_context_pinned: bool = Field(default=False, index=True)
    deleted_at: datetime | None = Field(default=None, index=True)
    status: str = Field(default="completed", index=True)
    error_json: str | None = None
    created_at: datetime
