from pydantic import BaseModel


class WorkspacePreviewResponse(BaseModel):
    workspace_id: str
    status: str
    url: str | None = None
