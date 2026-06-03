from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Conversation(BaseModel):
    id: str
    title: str
    mode: Literal["single", "group"] = "group"
    agent_ids: list[str] = Field(default_factory=list)
    workspace_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(from_attributes=True)


class ConversationCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    mode: Literal["single", "group"] = "group"
    agent_ids: list[str] = Field(default_factory=lambda: ["orchestrator"])
    workspace_id: str | None = None


class ConversationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    agent_ids: list[str] | None = None
