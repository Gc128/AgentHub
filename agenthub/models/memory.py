from datetime import datetime

from sqlmodel import Field, SQLModel


class MemorySummaryRecord(SQLModel, table=True):
    conversation_id: str = Field(primary_key=True)
    up_to_message_id: str
    summary_json: str
    status: str = Field(default="ready", index=True)
    error_message: str = ""
    updated_at: datetime
