from datetime import datetime

from sqlmodel import Field, SQLModel


class MessageRecord(SQLModel, table=True):
    id: str = Field(primary_key=True)
    conversation_id: str = Field(index=True)
    role: str
    sender_id: str
    content: str
    artifacts_json: str = "[]"
    created_at: datetime
