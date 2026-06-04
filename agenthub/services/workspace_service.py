import os
from datetime import UTC, datetime
from pathlib import Path

from agenthub.core.errors import BadRequestError
from agenthub.repositories.workspace_repo import WorkspaceRepository
from agenthub.schemas.workspace import (
    AppliedDiffRecord,
    ApplyDiffRequest,
    ApplyDiffResponse,
    WorkspaceFile,
    WorkspaceFileContent,
    WorkspaceFileWriteRequest,
    WorkspacePreviewResponse,
)
from agenthub.utils.ids import new_id
from agenthub.workspace.diff import DiffApplyError
from agenthub.workspace.diff import apply_diff as apply_workspace_diff
from agenthub.workspace.manager import (
    WorkspacePathError,
    normalize_workspace_file_path,
    resolve_workspace_path,
)


class WorkspaceService:
    def __init__(
        self,
        repository: WorkspaceRepository,
        workspace_root: Path = Path("./workspaces"),
    ) -> None:
        self._repository = repository
        self._workspace_root = workspace_root

    async def get_preview(self, workspace_id: str) -> WorkspacePreviewResponse:
        return await self._repository.get_preview(workspace_id)

    async def set_preview(
        self,
        workspace_id: str,
        status: str,
        preview_url: str | None = None,
    ) -> WorkspacePreviewResponse:
        current = await self._repository.get_preview(workspace_id)
        return await self._repository.save_preview(
            WorkspacePreviewResponse(
                workspace_id=workspace_id,
                status=status,
                preview_url=preview_url if preview_url is not None else current.preview_url,
            )
        )

    async def list_files(self, workspace_id: str) -> list[WorkspaceFile]:
        workspace_dir = self._workspace_dir(workspace_id)
        if not workspace_dir.exists():
            return []
        files = [
            WorkspaceFile(
                path=file_path.relative_to(workspace_dir).as_posix(),
                updated_at=datetime.fromtimestamp(file_path.stat().st_mtime, UTC),
            )
            for file_path in workspace_dir.rglob("*")
            if file_path.is_file()
        ]
        return sorted(files, key=lambda item: item.path)

    async def get_file_content(self, workspace_id: str, path: str) -> WorkspaceFileContent:
        normalized_path = self._normalize_path(path)
        file_path = self._file_path(workspace_id, normalized_path)
        if not file_path.exists():
            return await self._repository.get_file(workspace_id, normalized_path)
        return WorkspaceFileContent(
            workspace_id=workspace_id,
            path=normalized_path,
            content=file_path.read_text(encoding="utf-8"),
            updated_at=datetime.fromtimestamp(file_path.stat().st_mtime, UTC),
        )

    async def write_file(
        self,
        workspace_id: str,
        request: WorkspaceFileWriteRequest,
    ) -> WorkspaceFileContent:
        timestamp = datetime.now(UTC)
        normalized_path = self._normalize_path(request.path)
        file_record = WorkspaceFileContent(
            workspace_id=workspace_id,
            path=normalized_path,
            content=request.content,
            updated_at=timestamp,
        )
        self._write_file_to_disk(workspace_id, normalized_path, request.content, timestamp)
        return await self._repository.save_file(file_record)

    async def list_applied_diffs(self, workspace_id: str) -> list[AppliedDiffRecord]:
        return await self._repository.list_applied_diffs(workspace_id)

    async def apply_diff(
        self,
        workspace_id: str,
        request: ApplyDiffRequest,
        *,
        preview_url: str,
    ) -> ApplyDiffResponse:
        target_path = self._extract_diff_target_path(request.diff)
        old_content = self._read_file_content_or_empty(workspace_id, target_path)
        try:
            new_content = apply_workspace_diff(old_content, request.diff)
        except DiffApplyError as exc:
            raise BadRequestError("diff_apply_failed", str(exc)) from exc

        applied_at = datetime.now(UTC)
        self._write_file_to_disk(workspace_id, target_path, new_content, applied_at)
        await self._repository.save_file(
            WorkspaceFileContent(
                workspace_id=workspace_id,
                path=target_path,
                content=new_content,
                updated_at=applied_at,
            )
        )
        await self._repository.save_applied_diff(
            AppliedDiffRecord(
                id=new_id("apply"),
                workspace_id=workspace_id,
                artifact_id=request.artifact_id,
                diff=request.diff,
                path=target_path,
                applied_at=applied_at,
            )
        )
        await self.set_preview(workspace_id, "ready", preview_url)
        return ApplyDiffResponse(
            workspace_id=workspace_id,
            status="ready",
            applied_artifact_id=request.artifact_id,
            path=target_path,
            applied_at=applied_at,
        )

    def _extract_diff_target_path(self, diff_text: str) -> str:
        for line in diff_text.splitlines():
            if line.startswith("+++ "):
                target = line[4:].strip()
                if target == "/dev/null":
                    raise BadRequestError("unsupported_diff", "当前 Demo 暂不支持删除文件 Diff")
                return self._normalize_path(target)
        raise BadRequestError("invalid_diff", "Diff 缺少目标文件头")

    def _normalize_path(self, path: str) -> str:
        try:
            return normalize_workspace_file_path(path)
        except WorkspacePathError as exc:
            raise BadRequestError("invalid_workspace_path", str(exc)) from exc

    def _workspace_dir(self, workspace_id: str) -> Path:
        try:
            return resolve_workspace_path(self._workspace_root, workspace_id)
        except WorkspacePathError as exc:
            raise BadRequestError("invalid_workspace_id", str(exc)) from exc

    def _file_path(self, workspace_id: str, path: str) -> Path:
        workspace_dir = self._workspace_dir(workspace_id)
        try:
            return resolve_workspace_path(workspace_dir, path)
        except WorkspacePathError as exc:
            raise BadRequestError("invalid_workspace_path", str(exc)) from exc

    def _write_file_to_disk(
        self,
        workspace_id: str,
        path: str,
        content: str,
        updated_at: datetime,
    ) -> None:
        file_path = self._file_path(workspace_id, path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        timestamp = updated_at.timestamp()
        os.utime(file_path, (timestamp, timestamp))

    def _read_file_content_or_empty(self, workspace_id: str, path: str) -> str:
        file_path = self._file_path(workspace_id, path)
        return file_path.read_text(encoding="utf-8") if file_path.exists() else ""
