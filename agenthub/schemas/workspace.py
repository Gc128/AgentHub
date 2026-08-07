from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

WorkspacePreviewStatus = Literal["not_started", "running", "ready", "error"]


class WorkspacePreviewResponse(BaseModel):
    workspace_id: str
    status: WorkspacePreviewStatus
    preview_url: str | None = None
    entry_path: str | None = None


class WorkspaceFile(BaseModel):
    path: str
    updated_at: datetime | None = None


class WorkspaceFileContent(BaseModel):
    workspace_id: str
    path: str
    content: str
    updated_at: datetime


class WorkspaceFileWriteRequest(BaseModel):
    path: str = Field(min_length=1)
    content: str = ""


class WorkspaceFileDeleteResponse(BaseModel):
    workspace_id: str
    path: str
    deleted: bool
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ApplyDiffRequest(BaseModel):
    artifact_id: str = Field(min_length=1)
    diff: str = Field(min_length=1)


class ApplyDiffResponse(BaseModel):
    workspace_id: str
    status: WorkspacePreviewStatus
    applied_artifact_id: str
    path: str
    preview_url: str | None = None
    entry_path: str | None = None
    applied_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RevertDiffResponse(BaseModel):
    workspace_id: str
    reverted_record_id: str
    path: str
    status: WorkspacePreviewStatus
    preview_url: str | None = None
    entry_path: str | None = None
    reverted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AppliedDiffRecord(BaseModel):
    id: str
    workspace_id: str
    artifact_id: str
    diff: str
    path: str | None = None
    before_content: str | None = None
    after_content: str | None = None
    before_exists: bool = True
    change_set_id: str | None = None
    reverted_at: datetime | None = None
    applied_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
