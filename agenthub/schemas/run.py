from typing import Literal

from pydantic import BaseModel

AgentErrorCategory = Literal[
    "configuration",
    "transport",
    "schema",
    "validation",
    "workspace",
]


class AgentRunError(BaseModel):
    code: str
    category: AgentErrorCategory
    message: str
    retryable: bool = False
    run_id: str
    task_id: str | None = None
    agent_id: str
