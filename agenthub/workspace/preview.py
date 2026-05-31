from pydantic import BaseModel


class PreviewInfo(BaseModel):
    workspace_id: str
    status: str = "not_started"
    url: str | None = None
