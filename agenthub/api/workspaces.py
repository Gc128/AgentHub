from fastapi import APIRouter

router = APIRouter()


@router.get("/workspaces/{workspace_id}/preview")
async def get_workspace_preview(workspace_id: str) -> dict[str, str]:
    return {"workspace_id": workspace_id, "status": "not_started"}
