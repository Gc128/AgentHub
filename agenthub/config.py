from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    app_env: str = "development"
    log_level: str = "INFO"
    persistence_backend: Literal["memory", "sqlite"] = "sqlite"
    database_url: str = "sqlite:///./agenthub.db"
    workspace_root: Path = Field(default=Path("./workspaces"))
    use_mock_agents: bool = False
    agent_provider: str = "openai-compatible"
    agent_model: str = "gpt-4o-mini"
    agent_base_url: str = "https://api.openai.com/v1"
    agent_request_timeout_seconds: float = 30.0
    agent_response_format: Literal["auto", "text", "json_object"] = "json_object"
    agent_thinking: Literal["auto", "enabled", "disabled"] = "auto"
    agent_max_tokens: int | None = None
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None

    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
