from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class CustomAgent(BaseModel):
    id: str
    name: str
    description: str = ""
    system_prompt: str
    backend_id: str = "openai-compatible"
    capabilities: list[str] = Field(default_factory=list)
    is_enabled: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(from_attributes=True)


class CustomAgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=240)
    system_prompt: str = Field(min_length=1, max_length=8000)
    backend_id: str = Field(default="openai-compatible", max_length=80)
    capabilities: list[str] = Field(default_factory=list, max_length=12)
    is_enabled: bool = True


class CustomAgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=240)
    system_prompt: str | None = Field(default=None, min_length=1, max_length=8000)
    backend_id: str | None = Field(default=None, max_length=80)
    capabilities: list[str] | None = Field(default=None, max_length=12)
    is_enabled: bool | None = None


class CustomAgentDeleteResult(BaseModel):
    id: str
    deleted: bool


class CustomAgentTestRequest(BaseModel):
    message: str = Field(default="你好，请介绍一下你能做什么。", min_length=1)
