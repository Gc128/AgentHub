from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class Conversation(BaseModel):
    id: str
    title: str
    mode: Literal["single", "group"] = "group"
    agent_ids: list[str] = Field(default_factory=list)
    # 是否置顶；前端会用它把重要会话固定在列表顶部。
    is_pinned: bool = False
    workspace_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ConversationUpdate(BaseModel):
    # 会话标题可选更新；未传时后端不应修改原值。
    title: str | None = None
    # 会话模式可选更新；用于后续编辑单聊/群聊。
    mode: Literal["single", "group"] | None = None
    # Agent 列表可选更新；用于后续调整会话参与者。
    agent_ids: list[str] | None = None
    # 置顶状态可选更新；本轮前端只使用这个字段。
    is_pinned: bool | None = None


class ConversationDeleteResult(BaseModel):
    # 被删除的会话 ID，方便前端确认当前操作目标。
    id: str
    # 删除是否成功；真实后端可在失败时返回非 2xx 或 deleted=false。
    deleted: bool
