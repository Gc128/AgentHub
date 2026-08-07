from datetime import datetime

from sqlmodel import Field, SQLModel


class ChangeSetRecord(SQLModel, table=True):
    id: str = Field(primary_key=True)
    conversation_id: str = Field(index=True)
    workspace_id: str = Field(index=True)
    source_message_id: str | None = Field(default=None, index=True)
    parent_change_set_id: str | None = Field(default=None, index=True)
    status: str = Field(default="generated", index=True)
    base_snapshot_sha256: str
    repair_count: int = 0
    entry_path: str | None = None
    preview_checks_json: str = "[]"
    review_report_json: str | None = None
    preview_report_json: str | None = None
    created_at: datetime
    updated_at: datetime
    promoted_at: datetime | None = None


class ChangeSetFileRecord(SQLModel, table=True):
    id: str = Field(primary_key=True)
    change_set_id: str = Field(index=True)
    path: str = Field(index=True)
    operation: str = "upsert"
    before_exists: bool = False
    before_sha256: str
    before_content: str = ""
    after_content: str | None = None
    after_sha256: str
    diff: str = ""


class ValidationRunRecord(SQLModel, table=True):
    id: str = Field(primary_key=True)
    change_set_id: str = Field(index=True)
    kind: str = Field(index=True)
    attempt: int = 1
    status: str = Field(default="pending", index=True)
    report_json: str = "{}"
    error_code: str = ""
    error_message: str = ""
    started_at: datetime
    completed_at: datetime | None = None
