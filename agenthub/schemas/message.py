from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agenthub.schemas.artifact import Artifact
from agenthub.schemas.run import AgentRunError


class Message(BaseModel):
    id: str
    conversation_id: str
    role: Literal["user", "agent", "system"]
    sender_id: str
    content: str
    artifacts: list[Artifact] = Field(default_factory=list)
    reply_to_id: str | None = None
    regenerated_from_id: str | None = None
    is_context_pinned: bool = False
    deleted_at: datetime | None = None
    status: Literal["streaming", "completed", "failed"] = "completed"
    error: AgentRunError | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(from_attributes=True)


class MessageCreate(BaseModel):
    content: str = Field(min_length=1)
    sender_id: str = "user"
    artifacts: list[Artifact] = Field(default_factory=list)
    reply_to_id: str | None = None
    run_agent: bool = True


class MessageSendResponse(BaseModel):
    user_message: Message
    agent_messages: list[Message] = Field(default_factory=list)
