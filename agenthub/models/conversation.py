from datetime import datetime

from sqlmodel import Field, SQLModel


class ConversationRecord(SQLModel, table=True):
    id: str = Field(primary_key=True)
    title: str
    mode: str = "group"
    workspace_id: str
    created_at: datetime
    updated_at: datetime
