from fastapi import APIRouter

router = APIRouter()


@router.get("/conversations/{conversation_id}/messages")
async def list_messages(conversation_id: str) -> list[dict[str, str]]:
    return []
