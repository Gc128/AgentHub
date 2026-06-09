from datetime import datetime

from sqlmodel import Field, SQLModel


class CustomAgentRecord(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str = Field(index=True)
    description: str = ""
    system_prompt: str
    capabilities_json: str = "[]"
    is_enabled: bool = Field(default=True, index=True)
    created_at: datetime
    updated_at: datetime
