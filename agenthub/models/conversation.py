from datetime import datetime

from sqlmodel import Field, SQLModel


class ConversationRecord(SQLModel, table=True):
    id: str = Field(primary_key=True)
    title: str
    mode: str = "group"
    # 是否置顶；加索引方便后续真实列表接口按置顶优先排序。
    is_pinned: bool = Field(default=False, index=True)
    workspace_id: str
    created_at: datetime
    updated_at: datetime
