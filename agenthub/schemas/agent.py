from collections.abc import AsyncIterator
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from agenthub.schemas.artifact import Artifact
from agenthub.schemas.message import Message

AgentBackendType = Literal["mock", "openai-compatible", "codex-cli", "claude-code-cli"]


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


class AgentBackend(BaseModel):
    id: str
    name: str
    type: AgentBackendType
    description: str
    configured: bool
    available: bool
    command: str | None = None
    model: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    unavailable_reason: str | None = None


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


class AgentAdapter(Protocol):
    id: str
    name: str
    capabilities: list[str]

    async def run(self, input_data: AgentRunInput) -> AgentRunResult: ...


class StreamingAgentAdapter(AgentAdapter, Protocol):
    async def stream(self, input_data: AgentRunInput) -> AsyncIterator[str]: ...
