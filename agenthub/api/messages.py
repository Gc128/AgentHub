from typing import Annotated

from fastapi import APIRouter, Depends

from agenthub.api.deps import get_message_service
from agenthub.schemas.message import Message, MessageCreate, MessageSendResponse
from agenthub.services.message_service import MessageService

router = APIRouter()


@router.get("/conversations/{conversation_id}/messages", response_model=list[Message])
async def list_messages(
    conversation_id: str,
    service: Annotated[MessageService, Depends(get_message_service)],
) -> list[Message]:
    return await service.list_messages(conversation_id)


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=Message,
    status_code=201,
)
async def create_message(
    conversation_id: str,
    request: MessageCreate,
    service: Annotated[MessageService, Depends(get_message_service)],
) -> Message:
    return await service.create_message(conversation_id, request)


@router.post(
    "/conversations/{conversation_id}/messages/run",
    response_model=MessageSendResponse,
    status_code=201,
)
async def send_message_with_agent(
    conversation_id: str,
    request: MessageCreate,
    service: Annotated[MessageService, Depends(get_message_service)],
) -> MessageSendResponse:
    return await service.send_message(conversation_id, request)
