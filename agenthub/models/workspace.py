from datetime import datetime

from sqlmodel import Field, SQLModel


class WorkspaceRecord(SQLModel, table=True):
    id: str = Field(primary_key=True)
    root_path: str
    created_at: datetime


class WorkspacePreviewRecord(SQLModel, table=True):
    workspace_id: str = Field(primary_key=True)
    status: str
    preview_url: str | None = None
    entry_path: str | None = None


class WorkspaceFileRecord(SQLModel, table=True):
    id: str = Field(primary_key=True)
    workspace_id: str = Field(index=True)
    path: str = Field(index=True)
    content: str
    updated_at: datetime


class AppliedDiffRecordRow(SQLModel, table=True):
    id: str = Field(primary_key=True)
    workspace_id: str = Field(index=True)
    artifact_id: str
    diff: str
    path: str | None = None
    before_content: str | None = None
    after_content: str | None = None
    before_exists: bool = True
    change_set_id: str | None = Field(default=None, index=True)
    reverted_at: datetime | None = None
    applied_at: datetime
