from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field, model_validator

from agenthub.schemas.artifact import Artifact
from agenthub.schemas.message import Message
from agenthub.schemas.run import AgentRunError


class Agent(BaseModel):
    id: str
    name: str
    role: Literal["orchestrator", "code", "review", "preview", "custom"]
    description: str
    capabilities: list[str] = Field(default_factory=list)
    adapter_type: Literal["mock", "codex", "claude", "opencode", "custom"] = "mock"


class AgentRuntimeInfo(BaseModel):
    agent_mode: Literal["mock", "real"]
    provider: str
    model: str
    base_url_host: str
    api_key_configured: bool


class AgentRunInput(BaseModel):
    conversation_id: str
    workspace_id: str
    user_message: str
    history: list[Message] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)


class AgentRunResult(BaseModel):
    agent_id: str
    content: str
    artifacts: list[Artifact] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    error: AgentRunError | None = None


class AcceptanceCriterion(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=500)


GeneratedFileOperation = Literal["upsert", "delete"]


class GeneratedFile(BaseModel):
    path: str = Field(min_length=1, max_length=500)
    operation: GeneratedFileOperation = "upsert"
    content: str | None = None

    @model_validator(mode="after")
    def validate_operation_content(self) -> GeneratedFile:
        if self.operation == "upsert" and self.content is None:
            raise ValueError("upsert requires complete file content")
        if self.operation == "delete" and self.content is not None:
            raise ValueError("delete requires content=null")
        return self


BrowserAction = Literal[
    "fill",
    "click",
    "select",
    "reload",
    "assert_visible",
    "assert_text",
    "assert_count",
    "assert_min_count",
    "assert_invalid",
    "assert_local_storage",
]


class BrowserStep(BaseModel):
    action: BrowserAction
    selector: str | None = Field(default=None, max_length=500)
    value: str | None = Field(default=None, max_length=2000)
    expected: str | None = Field(default=None, max_length=2000)
    count: int | None = Field(default=None, ge=0, le=10000)
    storage_key: str | None = Field(default=None, max_length=200)
    comparison: Literal["contains", "exact"] = "contains"

    @model_validator(mode="after")
    def validate_action_arguments(self) -> BrowserStep:
        if self.action == "reload":
            return self
        if self.action == "assert_local_storage":
            if not self.storage_key:
                raise ValueError("assert_local_storage requires storage_key")
            return self
        if not self.selector:
            raise ValueError(f"{self.action} requires selector")
        if self.action in {"assert_count", "assert_min_count"} and self.count is None:
            raise ValueError(f"{self.action} requires count")
        if self.action in {"fill", "select"} and self.value is None:
            raise ValueError(f"{self.action} requires value")
        if self.action == "assert_text" and self.expected is None:
            raise ValueError("assert_text requires expected")
        return self


class PreviewCheck(BaseModel):
    criterion_id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    steps: list[BrowserStep] = Field(default_factory=list, max_length=20)


class CodeGenerationResult(BaseModel):
    summary: str = Field(min_length=1)
    files: list[GeneratedFile] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def validate_unique_paths(self) -> CodeGenerationResult:
        paths = [item.path for item in self.files]
        if len(paths) != len(set(paths)):
            raise ValueError("candidate file paths must be unique")
        return self


ReviewVerdict = Literal["pass", "pass_with_warnings", "fail"]
RiskLevel = Literal["low", "medium", "high"]
FindingSeverity = Literal["info", "warning", "high", "blocker"]


class ReviewFinding(BaseModel):
    severity: FindingSeverity
    category: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=1000)
    suggestion: str = Field(default="", max_length=1000)
    criterion_id: str | None = Field(default=None, max_length=80)
    evidence: str | None = Field(default=None, max_length=2000)
    path: str | None = Field(default=None, max_length=500)
    line: int | None = Field(default=None, ge=1)


class ReviewReport(BaseModel):
    verdict: ReviewVerdict
    risk_level: RiskLevel
    summary: str = Field(min_length=1)
    findings: list[ReviewFinding] = Field(default_factory=list, max_length=100)
    covered_criteria: list[str] = Field(default_factory=list)


class PreviewCheckResult(BaseModel):
    criterion_id: str
    name: str
    status: Literal["passed", "failed"]
    duration_ms: int = Field(default=0, ge=0)
    error: str = ""


class PreviewReport(BaseModel):
    status: Literal["pass", "fail"]
    entry_path: str
    preview_path: str
    screenshot_path: str | None = None
    checks: list[PreviewCheckResult] = Field(default_factory=list)
    console_errors: list[str] = Field(default_factory=list)
    page_errors: list[str] = Field(default_factory=list)
    failed_requests: list[str] = Field(default_factory=list)


class AgentAdapter(Protocol):
    id: str
    name: str
    capabilities: list[str]

    async def run(self, input_data: AgentRunInput) -> AgentRunResult: ...


class StreamingAgentAdapter(AgentAdapter, Protocol):
    async def stream(self, input_data: AgentRunInput) -> AsyncIterator[str]: ...
