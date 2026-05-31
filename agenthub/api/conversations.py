from fastapi import APIRouter

router = APIRouter()


@router.get("/conversations")
async def list_conversations() -> list[dict[str, str]]:
    return []
