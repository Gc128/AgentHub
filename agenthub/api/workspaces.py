from fastapi import APIRouter

from agenthub.schemas.workspace import WorkspacePreviewResponse

router = APIRouter()


@router.get("/workspaces/{workspace_id}/preview", response_model=WorkspacePreviewResponse)
async def get_workspace_preview(workspace_id: str) -> WorkspacePreviewResponse:
    return WorkspacePreviewResponse(workspace_id=workspace_id, status="not_started")
