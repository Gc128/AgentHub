from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agenthub.schemas.artifact import Artifact


class Message(BaseModel):
    id: str
    conversation_id: str
    role: Literal["user", "agent", "system"]
    sender_id: str
    content: str
    artifacts: list[Artifact] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(from_attributes=True)


class MessageCreate(BaseModel):
    content: str = Field(min_length=1)
    sender_id: str = "user"
    artifacts: list[Artifact] = Field(default_factory=list)
    run_agent: bool = True


class MessageSendResponse(BaseModel):
    user_message: Message
    agent_messages: list[Message] = Field(default_factory=list)
