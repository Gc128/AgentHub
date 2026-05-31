from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from agenthub.schemas.artifact import Artifact


class Message(BaseModel):
    id: str
    conversation_id: str
    role: Literal["user", "agent", "system"]
    sender_id: str
    content: str
    artifacts: list[Artifact] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
