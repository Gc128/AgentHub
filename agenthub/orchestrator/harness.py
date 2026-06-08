from typing import Literal

from pydantic import BaseModel, Field

HarnessStatus = Literal["started", "succeeded", "failed", "retrying", "skipped"]


class VerificationResult(BaseModel):
    ok: bool
    message: str
    issues: list[str] = Field(default_factory=list)


class StepRun(BaseModel):
    task_id: str
    agent_id: str
    attempt: int
    status: HarnessStatus
    verification: VerificationResult | None = None
    error: str = ""


class ExecutionReport(BaseModel):
    plan_summary: str
    steps: list[StepRun] = Field(default_factory=list)
    succeeded: bool = True
