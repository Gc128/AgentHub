from agenthub.core.errors import NotFoundError
from agenthub.schemas.workspace import (
    AppliedDiffRecord,
    WorkspaceFileContent,
    WorkspacePreviewResponse,
)


class WorkspaceRepository:
    def __init__(self) -> None:
        self._previews: dict[str, WorkspacePreviewResponse] = {}
        self._files: dict[str, dict[str, WorkspaceFileContent]] = {}
        self._applied_diffs: dict[str, list[AppliedDiffRecord]] = {}

    async def get_preview(self, workspace_id: str) -> WorkspacePreviewResponse:
        return self._previews.get(
            workspace_id,
            WorkspacePreviewResponse(workspace_id=workspace_id, status="not_started"),
        )

    async def save_preview(
        self,
        preview: WorkspacePreviewResponse,
    ) -> WorkspacePreviewResponse:
        self._previews[preview.workspace_id] = preview
        return preview

    async def list_files(self, workspace_id: str) -> list[WorkspaceFileContent]:
        files = self._files.get(workspace_id, {})
        return sorted(files.values(), key=lambda item: item.path)

    async def get_file(self, workspace_id: str, path: str) -> WorkspaceFileContent:
        file_record = self._files.get(workspace_id, {}).get(path)
        if file_record is None:
            raise NotFoundError("workspace_file_not_found", "Workspace file does not exist.")
        return file_record

    async def get_file_content_or_empty(self, workspace_id: str, path: str) -> str:
        file_record = self._files.get(workspace_id, {}).get(path)
        return file_record.content if file_record is not None else ""

    async def save_file(self, file_record: WorkspaceFileContent) -> WorkspaceFileContent:
        files = self._files.setdefault(file_record.workspace_id, {})
        files[file_record.path] = file_record
        return file_record

    async def delete_file(self, workspace_id: str, path: str) -> None:
        files = self._files.get(workspace_id)
        if files is not None:
            files.pop(path, None)

    async def list_applied_diffs(self, workspace_id: str) -> list[AppliedDiffRecord]:
        return list(self._applied_diffs.get(workspace_id, []))

    async def save_applied_diff(self, record: AppliedDiffRecord) -> AppliedDiffRecord:
        records = self._applied_diffs.setdefault(record.workspace_id, [])
        records.append(record)
        return record
