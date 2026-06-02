from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter

from agenthub.schemas.conversation import (
    Conversation,
    ConversationDeleteResult,
    ConversationUpdate,
)

router = APIRouter()


def infer_mode(agent_ids: list[str]) -> Literal["single", "group"]:
    # 会话模式由成员数量推导，避免单聊/群聊和 agent_ids 产生不一致。
    return "group" if len(agent_ids) > 1 else "single"


@router.get("/conversations")
async def list_conversations() -> list[dict[str, str]]:
    return []


@router.patch("/conversations/{conversation_id}")
async def update_conversation(
    conversation_id: str,
    payload: ConversationUpdate,
) -> Conversation:
    # 当前后端还没有持久化层实现；这里返回 Conversation 形状，确保接口契约和前端 client/mock 对齐。
    timestamp = datetime.now(UTC)
    agent_ids = payload.agent_ids or ["orchestrator"]
    return Conversation(
        id=conversation_id,
        title=payload.title or "Untitled Conversation",
        mode=(infer_mode(agent_ids) if payload.agent_ids is not None else payload.mode or "group"),
        agent_ids=agent_ids,
        is_pinned=payload.is_pinned if payload.is_pinned is not None else False,
        workspace_id=f"ws_{conversation_id}",
        created_at=timestamp,
        updated_at=timestamp,
    )


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str) -> ConversationDeleteResult:
    # 当前后端还没有真实删除逻辑；前端 mock 会先完成端到端体验。
    return ConversationDeleteResult(id=conversation_id, deleted=True)
