from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from agenthub.schemas.agent import PreviewCheck, PreviewReport, ReviewReport

ChangeSetStatus = Literal[
    "generated",
    "staging",
    "validating",
    "needs_fix",
    "ready",
    "promoting",
    "promoted",
    "failed",
    "rejected",
    "conflicted",
]
ValidationKind = Literal["review", "preview"]
ValidationStatus = Literal["pending", "running", "passed", "failed"]


class ChangeSetFile(BaseModel):
    id: str
    change_set_id: str
    path: str
    operation: Literal["upsert", "delete"] = "upsert"
    before_exists: bool = False
    before_sha256: str
    before_content: str = ""
    after_content: str | None = None
    after_sha256: str
    diff: str = ""


class ValidationRun(BaseModel):
    id: str
    change_set_id: str
    kind: ValidationKind
    attempt: int = Field(default=1, ge=1)
    status: ValidationStatus = "pending"
    report: dict[str, object] = Field(default_factory=dict)
    error_code: str = ""
    error_message: str = ""
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None


class ChangeSet(BaseModel):
    id: str
    conversation_id: str
    workspace_id: str
    source_message_id: str | None = None
    parent_change_set_id: str | None = None
    status: ChangeSetStatus = "generated"
    base_snapshot_sha256: str
    repair_count: int = Field(default=0, ge=0, le=1)
    entry_path: str | None = None
    preview_checks: list[PreviewCheck] = Field(default_factory=list)
    review_report: ReviewReport | None = None
    preview_report: PreviewReport | None = None
    files: list[ChangeSetFile] = Field(default_factory=list)
    validations: list[ValidationRun] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    promoted_at: datetime | None = None


class ChangeSetActionResponse(BaseModel):
    change_set: ChangeSet
    message: str


class ChangeSetRevertResponse(BaseModel):
    change_set_id: str
    workspace_id: str
    reverted_paths: list[str]
    reverted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
