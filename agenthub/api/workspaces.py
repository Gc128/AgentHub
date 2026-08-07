import logging
import mimetypes
import re
from html import escape
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import HTMLResponse, Response

from agenthub.api.deps import get_agent_service, get_change_set_service, get_workspace_service
from agenthub.config import get_settings
from agenthub.core.errors import ConflictError, NotFoundError
from agenthub.schemas.agent import AgentRunInput
from agenthub.schemas.change_set import (
    ChangeSet,
    ChangeSetActionResponse,
    ChangeSetRevertResponse,
)
from agenthub.schemas.workspace import (
    AppliedDiffRecord,
    ApplyDiffRequest,
    ApplyDiffResponse,
    RevertDiffResponse,
    WorkspaceFile,
    WorkspaceFileContent,
    WorkspaceFileDeleteResponse,
    WorkspaceFileWriteRequest,
    WorkspacePreviewResponse,
)
from agenthub.services.agent_service import AgentService
from agenthub.services.change_set_service import ChangeSetService
from agenthub.services.workspace_service import WorkspaceService

router = APIRouter()
logger = logging.getLogger(__name__)
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
    path: str = "index.html",
) -> HTMLResponse:
    try:
        preview_file = await service.get_file_content(workspace_id, path)
        asset_base_url = _preview_asset_base_url(request, workspace_id, preview_file.path)
        return HTMLResponse(
            _inject_preview_asset_base(preview_file.content, asset_base_url),
            headers=NO_STORE_HEADERS,
        )
    except NotFoundError:
        preview = await service.get_preview(workspace_id)
        status = escape(preview.status)
        safe_workspace_id = escape(workspace_id)
        safe_path = escape(path)
        return HTMLResponse(
            '<!doctype html><html><head><meta charset="utf-8">'
            "<style>body{font-family:Inter,system-ui,sans-serif;margin:0;"
            "padding:32px;background:#f6f3ed;color:#1f2926}"
            ".card{border:1px solid #d9d1c5;border-radius:12px;padding:24px;"
            "background:#fff;max-width:560px;margin:auto}"
            "code{background:#eef5f2;border-radius:6px;padding:2px 6px}</style>"
            f'</head><body><section class="card"><h1>{safe_workspace_id}</h1>'
            f"<p>Preview status: <code>{status}</code></p>"
            f"<p>当前 workspace 尚未生成 <code>{safe_path}</code>，先展示预览状态页。</p>"
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


@router.post(
    "/workspaces/{workspace_id}/apply-diff",
    response_model=ApplyDiffResponse,
    deprecated=True,
)
async def apply_diff(
    workspace_id: str,
    request_data: ApplyDiffRequest,
    request: Request,
    service: Annotated[WorkspaceService, Depends(get_workspace_service)],
) -> ApplyDiffResponse:
    if not get_settings().legacy_apply_diff_enabled:
        raise ConflictError(
            "legacy_apply_diff_disabled",
            "Direct Apply Diff is disabled. Validate a change set and promote it instead.",
        )
    preview_page_url = str(request.url_for("get_workspace_preview_page", workspace_id=workspace_id))
    return await service.apply_diff(
        workspace_id,
        request_data,
        preview_page_url=preview_page_url,
    )


@router.post(
    "/workspaces/{workspace_id}/applied-diffs/{record_id}/revert",
    response_model=RevertDiffResponse,
)
async def revert_applied_diff(
    workspace_id: str,
    record_id: str,
    request: Request,
    service: Annotated[WorkspaceService, Depends(get_workspace_service)],
) -> RevertDiffResponse:
    preview_page_url = str(request.url_for("get_workspace_preview_page", workspace_id=workspace_id))
    return await service.revert_applied_diff(
        workspace_id,
        record_id,
        preview_page_url=preview_page_url,
    )


@router.get("/workspaces/{workspace_id}/change-sets", response_model=list[ChangeSet])
async def list_change_sets(
    workspace_id: str,
    service: Annotated[ChangeSetService, Depends(get_change_set_service)],
) -> list[ChangeSet]:
    return await service.list(workspace_id)


@router.get(
    "/workspaces/{workspace_id}/change-sets/{change_set_id}",
    response_model=ChangeSet,
)
async def get_change_set(
    workspace_id: str,
    change_set_id: str,
    service: Annotated[ChangeSetService, Depends(get_change_set_service)],
) -> ChangeSet:
    return await service.get(workspace_id, change_set_id)


@router.post(
    "/workspaces/{workspace_id}/change-sets/{change_set_id}/promote",
    response_model=ChangeSetActionResponse,
)
async def promote_change_set(
    workspace_id: str,
    change_set_id: str,
    request: Request,
    service: Annotated[ChangeSetService, Depends(get_change_set_service)],
) -> ChangeSetActionResponse:
    preview_page_url = str(request.url_for("get_workspace_preview_page", workspace_id=workspace_id))
    return await service.promote(
        workspace_id,
        change_set_id,
        preview_page_url=preview_page_url,
    )


@router.post(
    "/workspaces/{workspace_id}/change-sets/{change_set_id}/reject",
    response_model=ChangeSetActionResponse,
)
async def reject_change_set(
    workspace_id: str,
    change_set_id: str,
    service: Annotated[ChangeSetService, Depends(get_change_set_service)],
) -> ChangeSetActionResponse:
    return await service.reject(workspace_id, change_set_id)


@router.post(
    "/workspaces/{workspace_id}/change-sets/{change_set_id}/revert",
    response_model=ChangeSetRevertResponse,
)
async def revert_change_set(
    workspace_id: str,
    change_set_id: str,
    service: Annotated[ChangeSetService, Depends(get_change_set_service)],
) -> ChangeSetRevertResponse:
    return await service.revert(workspace_id, change_set_id)


@router.post(
    "/workspaces/{workspace_id}/change-sets/{change_set_id}/reapply",
    response_model=ChangeSetActionResponse,
)
async def reapply_change_set(
    workspace_id: str,
    change_set_id: str,
    background_tasks: BackgroundTasks,
    service: Annotated[ChangeSetService, Depends(get_change_set_service)],
    agent_service: Annotated[AgentService, Depends(get_agent_service)],
) -> ChangeSetActionResponse:
    candidate = await service.prepare_reapply(workspace_id, change_set_id)
    background_tasks.add_task(
        _validate_existing_candidate,
        service,
        agent_service,
        AgentRunInput(
            conversation_id=candidate.conversation_id,
            workspace_id=workspace_id,
            user_message=(
                f"重新应用 Change Set {change_set_id}：创建新候选并执行静态安全检查与代码审查。"
            ),
        ),
        candidate.id,
        "reapply_validation_failed",
    )
    return ChangeSetActionResponse(
        change_set=candidate,
        message="Reapply candidate created; static inspection and Review are running.",
    )


@router.post(
    "/workspaces/{workspace_id}/change-sets/{change_set_id}/re-review",
    response_model=ChangeSetActionResponse,
    status_code=202,
)
async def re_review_change_set(
    workspace_id: str,
    change_set_id: str,
    background_tasks: BackgroundTasks,
    service: Annotated[ChangeSetService, Depends(get_change_set_service)],
    agent_service: Annotated[AgentService, Depends(get_agent_service)],
) -> ChangeSetActionResponse:
    candidate = await service.prepare_re_review(workspace_id, change_set_id)
    background_tasks.add_task(
        _validate_existing_candidate,
        service,
        agent_service,
        AgentRunInput(
            conversation_id=candidate.conversation_id,
            workspace_id=workspace_id,
            user_message=(
                f"重新审查 Change Set {change_set_id}：创建新候选并执行静态检查和代码审查。"
            ),
        ),
        candidate.id,
        "rereview_validation_failed",
    )
    return ChangeSetActionResponse(
        change_set=candidate,
        message="Re-review candidate created; static inspection and Review are running.",
    )


async def _validate_existing_candidate(
    service: ChangeSetService,
    agent_service: AgentService,
    input_data: AgentRunInput,
    change_set_id: str,
    error_code: str,
) -> None:
    try:
        await agent_service.validate_existing_change_set(input_data, change_set_id)
    except Exception:
        logger.error(
            "Unexpected review-only validation failure for change_set=%s workspace=%s",
            change_set_id,
            input_data.workspace_id,
        )
        await service.record_validation_error(
            input_data.workspace_id,
            change_set_id,
            kind="review",
            error_code=error_code,
            error_message="Unexpected error while validating the review-only candidate.",
        )


@router.get(
    "/workspaces/{workspace_id}/change-sets/{change_set_id}/preview-page",
    response_class=HTMLResponse,
)
async def get_change_set_preview_page(
    workspace_id: str,
    change_set_id: str,
    request: Request,
    service: Annotated[ChangeSetService, Depends(get_change_set_service)],
    path: str = "index.html",
) -> HTMLResponse:
    change_set = await service.get(workspace_id, change_set_id)
    content = service.get_preview_file_bytes(change_set, path).decode("utf-8")
    asset_base_url = _change_set_preview_asset_base_url(request, workspace_id, change_set_id, path)
    return HTMLResponse(
        _inject_preview_asset_base(content, asset_base_url),
        headers={
            **NO_STORE_HEADERS,
            "Content-Security-Policy": (
                "sandbox allow-scripts allow-forms allow-same-origin; "
                "default-src 'self' data: blob: 'unsafe-inline'; connect-src 'none'"
            ),
        },
    )


@router.get("/workspaces/{workspace_id}/change-sets/{change_set_id}/preview-assets/{path:path}")
async def get_change_set_preview_asset(
    workspace_id: str,
    change_set_id: str,
    path: str,
    service: Annotated[ChangeSetService, Depends(get_change_set_service)],
) -> Response:
    change_set = await service.get(workspace_id, change_set_id)
    return Response(
        content=service.get_preview_file_bytes(change_set, path),
        media_type=_media_type_for_path(path),
        headers=NO_STORE_HEADERS,
    )


@router.get("/workspaces/{workspace_id}/change-sets/{change_set_id}/screenshot")
async def get_change_set_screenshot(
    workspace_id: str,
    change_set_id: str,
    service: Annotated[ChangeSetService, Depends(get_change_set_service)],
) -> Response:
    await service.get(workspace_id, change_set_id)
    return Response(
        content=service.get_screenshot_bytes(change_set_id),
        media_type="image/png",
        headers=NO_STORE_HEADERS,
    )


def _preview_asset_base_url(request: Request, workspace_id: str, entry_path: str) -> str:
    placeholder = "__agenthub_asset__"
    entry_dir = entry_path.rsplit("/", 1)[0] if "/" in entry_path else ""
    placeholder_path = f"{entry_dir}/{placeholder}" if entry_dir else placeholder
    asset_url = str(
        request.url_for(
            "get_workspace_preview_asset",
            workspace_id=workspace_id,
            path=placeholder_path,
        )
    )
    return asset_url.rsplit(placeholder, 1)[0]


def _change_set_preview_asset_base_url(
    request: Request,
    workspace_id: str,
    change_set_id: str,
    entry_path: str,
) -> str:
    placeholder = "__agenthub_asset__"
    entry_dir = entry_path.rsplit("/", 1)[0] if "/" in entry_path else ""
    placeholder_path = f"{entry_dir}/{placeholder}" if entry_dir else placeholder
    asset_url = str(
        request.url_for(
            "get_change_set_preview_asset",
            workspace_id=workspace_id,
            change_set_id=change_set_id,
            path=placeholder_path,
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
