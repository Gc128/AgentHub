from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class ConversationMemorySummary(BaseModel):
    facts: list[str] = Field(default_factory=list)
    requirements: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    promoted_changes: list[str] = Field(default_factory=list)


class MemorySummaryRecordSchema(BaseModel):
    conversation_id: str
    up_to_message_id: str
    summary: ConversationMemorySummary
    status: Literal["ready", "failed"] = "ready"
    error_message: str = ""
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
