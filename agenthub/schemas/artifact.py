from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ArtifactType = Literal["code", "diff", "preview", "file", "deploy", "change_set"]


class Artifact(BaseModel):
    id: str
    type: ArtifactType
    title: str
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
