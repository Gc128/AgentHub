from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class Conversation(BaseModel):
    id: str
    title: str
    mode: Literal["single", "group"] = "group"
    agent_ids: list[str] = Field(default_factory=list)
    workspace_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
