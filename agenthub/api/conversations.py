from typing import Annotated

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends

from agenthub.api.deps import get_conversation_service
from agenthub.schemas.conversation import Conversation, ConversationCreate, ConversationUpdate
from agenthub.services.conversation_service import ConversationService

from agenthub.schemas.conversation import (
    Conversation,
    ConversationDeleteResult,
    ConversationUpdate,
)

router = APIRouter()


def infer_mode(agent_ids: list[str]) -> Literal["single", "group"]:
    # 会话模式由成员数量推导，避免单聊/群聊和 agent_ids 产生不一致。
    return "group" if len(agent_ids) > 1 else "single"


@router.get("/conversations", response_model=list[Conversation])
async def list_conversations(
    service: Annotated[ConversationService, Depends(get_conversation_service)],
) -> list[Conversation]:
    return await service.list_conversations()


@router.post("/conversations", response_model=Conversation, status_code=201)
async def create_conversation(
    request: ConversationCreate,
    service: Annotated[ConversationService, Depends(get_conversation_service)],
) -> Conversation:
    return await service.create_conversation(request)


@router.get("/conversations/{conversation_id}", response_model=Conversation)
async def get_conversation(
    conversation_id: str,
    service: Annotated[ConversationService, Depends(get_conversation_service)],
) -> Conversation:
    return await service.get_conversation(conversation_id)


@router.patch("/conversations/{conversation_id}", response_model=Conversation)
async def update_conversation(
    conversation_id: str,
    request: ConversationUpdate,
    service: Annotated[ConversationService, Depends(get_conversation_service)],
) -> Conversation:
    return await service.update_conversation(conversation_id, request)
