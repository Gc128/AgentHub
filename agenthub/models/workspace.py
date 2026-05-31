from datetime import datetime

from sqlmodel import Field, SQLModel


class WorkspaceRecord(SQLModel, table=True):
    id: str = Field(primary_key=True)
    root_path: str
    created_at: datetime
