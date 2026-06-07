import mimetypes
import re
from html import escape
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response

from agenthub.api.deps import get_workspace_service
from agenthub.core.errors import NotFoundError
from agenthub.schemas.workspace import (
    AppliedDiffRecord,
    ApplyDiffRequest,
    ApplyDiffResponse,
    WorkspaceFile,
    WorkspaceFileContent,
    WorkspaceFileDeleteResponse,
    WorkspaceFileWriteRequest,
    WorkspacePreviewResponse,
)
from agenthub.services.workspace_service import WorkspaceService

router = APIRouter()
NO_STORE_HEADERS = {"Cache-Control": "no-store"}


@router.get("/workspaces/{workspace_id}/preview", response_model=WorkspacePreviewResponse)
async def get_workspace_preview(
    workspace_id: str,
    service: Annotated[WorkspaceService, Depends(get_workspace_service)],
) -> WorkspacePreviewResponse:
    return await service.get_preview(workspace_id)


@router.get("/workspaces/{workspace_id}/preview-page", response_class=HTMLResponse)
async def get_workspace_preview_page(
    workspace_id: str,
    request: Request,
    service: Annotated[WorkspaceService, Depends(get_workspace_service)],
) -> HTMLResponse:
    try:
        index_file = await service.get_file_content(workspace_id, "index.html")
        asset_base_url = _preview_asset_base_url(request, workspace_id)
        return HTMLResponse(
            _inject_preview_asset_base(index_file.content, asset_base_url),
            headers=NO_STORE_HEADERS,
        )
    except NotFoundError:
        preview = await service.get_preview(workspace_id)
        status = escape(preview.status)
        safe_workspace_id = escape(workspace_id)
        return HTMLResponse(
            '<!doctype html><html><head><meta charset="utf-8">'
            "<style>body{font-family:Inter,system-ui,sans-serif;margin:0;"
            "padding:32px;background:#f6f3ed;color:#1f2926}"
            ".card{border:1px solid #d9d1c5;border-radius:12px;padding:24px;"
            "background:#fff;max-width:560px;margin:auto}"
            "code{background:#eef5f2;border-radius:6px;padding:2px 6px}</style>"
            f'</head><body><section class="card"><h1>{safe_workspace_id}</h1>'
            f"<p>Preview status: <code>{status}</code></p>"
            "<p>当前 workspace 尚未生成 index.html，先展示预览状态页。</p>"
            "</section></body></html>",
            headers=NO_STORE_HEADERS,
        )


@router.get("/workspaces/{workspace_id}/preview-assets/{path:path}")
async def get_workspace_preview_asset(
    workspace_id: str,
    path: str,
    service: Annotated[WorkspaceService, Depends(get_workspace_service)],
) -> Response:
    content = await service.get_file_bytes(workspace_id, path)
    media_type = _media_type_for_path(path)
    return Response(content=content, media_type=media_type, headers=NO_STORE_HEADERS)


@router.get("/workspaces/{workspace_id}/files", response_model=list[WorkspaceFile])
async def list_workspace_files(
    workspace_id: str,
    service: Annotated[WorkspaceService, Depends(get_workspace_service)],
) -> list[WorkspaceFile]:
    return await service.list_files(workspace_id)


@router.get("/workspaces/{workspace_id}/files/content", response_model=WorkspaceFileContent)
async def get_workspace_file_content(
    workspace_id: str,
    path: str,
    service: Annotated[WorkspaceService, Depends(get_workspace_service)],
) -> WorkspaceFileContent:
    return await service.get_file_content(workspace_id, path)


@router.post(
    "/workspaces/{workspace_id}/files",
    response_model=WorkspaceFileContent,
    status_code=201,
)
async def write_workspace_file(
    workspace_id: str,
    request: WorkspaceFileWriteRequest,
    service: Annotated[WorkspaceService, Depends(get_workspace_service)],
) -> WorkspaceFileContent:
    return await service.write_file(workspace_id, request)


@router.delete("/workspaces/{workspace_id}/files", response_model=WorkspaceFileDeleteResponse)
async def delete_workspace_file(
    workspace_id: str,
    path: str,
    service: Annotated[WorkspaceService, Depends(get_workspace_service)],
) -> WorkspaceFileDeleteResponse:
    return await service.delete_file(workspace_id, path)


@router.get("/workspaces/{workspace_id}/applied-diffs", response_model=list[AppliedDiffRecord])
async def list_applied_diffs(
    workspace_id: str,
    service: Annotated[WorkspaceService, Depends(get_workspace_service)],
) -> list[AppliedDiffRecord]:
    return await service.list_applied_diffs(workspace_id)


@router.post("/workspaces/{workspace_id}/apply-diff", response_model=ApplyDiffResponse)
async def apply_diff(
    workspace_id: str,
    request_data: ApplyDiffRequest,
    request: Request,
    service: Annotated[WorkspaceService, Depends(get_workspace_service)],
) -> ApplyDiffResponse:
    preview_url = str(request.url_for("get_workspace_preview_page", workspace_id=workspace_id))
    return await service.apply_diff(workspace_id, request_data, preview_url=preview_url)


def _preview_asset_base_url(request: Request, workspace_id: str) -> str:
    placeholder = "__agenthub_asset__"
    asset_url = str(
        request.url_for(
            "get_workspace_preview_asset",
            workspace_id=workspace_id,
            path=placeholder,
        )
    )
    return asset_url.rsplit(placeholder, 1)[0]


def _inject_preview_asset_base(html: str, asset_base_url: str) -> str:
    if re.search(r"<base\b", html, flags=re.IGNORECASE):
        return html

    base_tag = f'<base href="{escape(asset_base_url, quote=True)}">'
    head_match = re.search(r"<head\b[^>]*>", html, flags=re.IGNORECASE)
    if head_match:
        return html[: head_match.end()] + base_tag + html[head_match.end() :]
    return base_tag + html


def _media_type_for_path(path: str) -> str:
    media_type, _encoding = mimetypes.guess_type(path)
    if path.lower().endswith(".js"):
        return "text/javascript"
    return media_type or "application/octet-stream"
