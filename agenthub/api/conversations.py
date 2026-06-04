from typing import Annotated

from fastapi import APIRouter, Depends

from agenthub.api.deps import get_conversation_service, get_message_service
from agenthub.schemas.conversation import (
    Conversation,
    ConversationCreate,
    ConversationDeleteResult,
    ConversationUpdate,
)
from agenthub.services.conversation_service import ConversationService
from agenthub.services.message_service import MessageService

router = APIRouter()


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


@router.delete("/conversations/{conversation_id}", response_model=ConversationDeleteResult)
async def delete_conversation(
    conversation_id: str,
    conversation_service: Annotated[ConversationService, Depends(get_conversation_service)],
    message_service: Annotated[MessageService, Depends(get_message_service)],
) -> ConversationDeleteResult:
    result = await conversation_service.delete_conversation(conversation_id)
    await message_service.delete_messages_for_conversation(conversation_id)
    return result
