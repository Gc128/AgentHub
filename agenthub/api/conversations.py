from typing import Annotated

from fastapi import APIRouter, Depends

from agenthub.api.deps import get_conversation_service
from agenthub.schemas.conversation import Conversation, ConversationCreate, ConversationUpdate
from agenthub.services.conversation_service import ConversationService

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
