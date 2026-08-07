from __future__ import annotations

import builtins
import hashlib
import os
import shutil
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast
from urllib.parse import quote

from agenthub.core.errors import BadRequestError, ConflictError, NotFoundError
from agenthub.repositories.change_set_repo import ChangeSetRepository
from agenthub.repositories.workspace_repo import WorkspaceRepository
from agenthub.schemas.agent import PreviewCheck, PreviewReport, ReviewReport
from agenthub.schemas.artifact import Artifact
from agenthub.schemas.change_set import (
    ChangeSet,
    ChangeSetActionResponse,
    ChangeSetFile,
    ChangeSetRevertResponse,
    ValidationRun,
)
from agenthub.schemas.workspace import AppliedDiffRecord, WorkspaceFileContent
from agenthub.services.workspace_service import WorkspaceService
from agenthub.utils.ids import new_id
from agenthub.workspace.diff import create_unified_diff
from agenthub.workspace.manager import (
    WorkspacePathError,
    normalize_workspace_file_path,
    resolve_workspace_path,
)


class ChangeSetService:
    def __init__(
        self,
        repository: ChangeSetRepository,
        workspace_repository: WorkspaceRepository,
        workspace_service: WorkspaceService,
        *,
        workspace_root: Path,
        staging_root: Path,
        preview_artifact_root: Path,
        staging_ttl_hours: int = 24,
        preview_artifact_ttl_hours: int = 168,
    ) -> None:
        self._repository = repository
        self._workspace_repository = workspace_repository
        self._workspace_service = workspace_service
        self._workspace_root = workspace_root
        self._staging_root = staging_root
        self._preview_artifact_root = preview_artifact_root
        self._staging_ttl_seconds = staging_ttl_hours * 3600
        self._preview_artifact_ttl_seconds = preview_artifact_ttl_hours * 3600

    async def create_from_artifacts(
        self,
        *,
        conversation_id: str,
        workspace_id: str,
        artifacts: list[Artifact],
        source_message_id: str | None = None,
        parent_change_set_id: str | None = None,
        repair_count: int = 0,
        preview_checks: list[PreviewCheck] | None = None,
    ) -> ChangeSet:
        self.cleanup_expired_artifacts()
        generated_files = self._generated_files_from_artifacts(artifacts)
        if not generated_files:
            raise BadRequestError(
                "change_set_has_no_files",
                "Code Agent did not return any candidate files for validation.",
            )

        change_set_id = new_id("changeset")
        files: list[ChangeSetFile] = []
        for path, (operation, after_content) in generated_files.items():
            canonical_path = self._canonical_file_path(workspace_id, path)
            before_exists = canonical_path.exists()
            if before_exists and not canonical_path.is_file():
                raise BadRequestError(
                    "invalid_workspace_path", f"Workspace path '{path}' is not a file."
                )
            before_content = canonical_path.read_text(encoding="utf-8") if before_exists else ""
            files.append(
                ChangeSetFile(
                    id=new_id("changefile"),
                    change_set_id=change_set_id,
                    path=path,
                    operation=operation,
                    before_exists=before_exists,
                    before_sha256=_sha256_text(before_content),
                    before_content=before_content,
                    after_content=after_content,
                    after_sha256=_sha256_text(after_content or ""),
                    diff=create_unified_diff(before_content, after_content or "", path),
                )
            )

        base_snapshot_sha256 = _snapshot_sha256(files)
        now = datetime.now(UTC)
        change_set = ChangeSet(
            id=change_set_id,
            conversation_id=conversation_id,
            workspace_id=workspace_id,
            source_message_id=source_message_id,
            parent_change_set_id=parent_change_set_id,
            status="generated",
            base_snapshot_sha256=base_snapshot_sha256,
            repair_count=repair_count,
            preview_checks=preview_checks or [],
            files=files,
            created_at=now,
            updated_at=now,
        )
        await self._repository.save(change_set)
        try:
            return await self.stage(change_set)
        except Exception:
            await self._repository.save(
                change_set.model_copy(update={"status": "failed", "updated_at": datetime.now(UTC)})
            )
            self._remove_staging_dir(change_set.id)
            raise

    async def stage(self, change_set: ChangeSet) -> ChangeSet:
        staging = change_set.model_copy(
            update={"status": "staging", "updated_at": datetime.now(UTC)}
        )
        await self._repository.save(staging)
        source = self._workspace_dir(change_set.workspace_id)
        target = self.staging_dir(change_set.id)
        if target.exists():
            shutil.rmtree(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.exists():
            self._reject_symlinks(source)
            shutil.copytree(source, target)
        else:
            target.mkdir(parents=True)

        for file_record in change_set.files:
            target_file = self._staged_file_path(change_set.id, file_record.path)
            if file_record.operation == "delete":
                if target_file.exists():
                    target_file.unlink()
                continue
            if file_record.after_content is None:
                raise BadRequestError(
                    "invalid_candidate_file",
                    f"Candidate file '{file_record.path}' has no content.",
                )
            target_file.parent.mkdir(parents=True, exist_ok=True)
            target_file.write_text(file_record.after_content, encoding="utf-8")

        entry_path = self._select_entry_path(target, change_set.files)
        staged = staging.model_copy(
            update={
                "status": "validating",
                "entry_path": entry_path,
                "updated_at": datetime.now(UTC),
            }
        )
        await self._repository.save(staged)
        return staged

    async def get(self, workspace_id: str, change_set_id: str) -> ChangeSet:
        return await self._repository.get(workspace_id, change_set_id)

    async def list(self, workspace_id: str) -> list[ChangeSet]:
        return await self._repository.list_by_workspace(workspace_id)

    def workspace_entry_path(self, workspace_id: str) -> str | None:
        return self._select_workspace_entry(workspace_id)

    async def set_review_report(
        self, workspace_id: str, change_set_id: str, report: ReviewReport
    ) -> ChangeSet:
        change_set = await self.get(workspace_id, change_set_id)
        validation = self._completed_validation(
            change_set,
            kind="review",
            status="passed" if report.verdict != "fail" else "failed",
            report=report.model_dump(mode="json"),
        )
        updated = change_set.model_copy(
            update={
                "review_report": report,
                "validations": self._replace_validation(change_set, validation),
                "updated_at": datetime.now(UTC),
            }
        )
        return await self._repository.save(self._recompute_validation_status(updated))

    async def set_preview_report(
        self, workspace_id: str, change_set_id: str, report: PreviewReport
    ) -> ChangeSet:
        change_set = await self.get(workspace_id, change_set_id)
        validation = self._completed_validation(
            change_set,
            kind="preview",
            status="passed" if report.status == "pass" else "failed",
            report=report.model_dump(mode="json"),
        )
        updated = change_set.model_copy(
            update={
                "preview_report": report,
                "validations": self._replace_validation(change_set, validation),
                "updated_at": datetime.now(UTC),
            }
        )
        return await self._repository.save(self._recompute_validation_status(updated))

    async def start_validation(
        self,
        workspace_id: str,
        change_set_id: str,
        *,
        kind: Literal["review", "preview"],
    ) -> ChangeSet:
        change_set = await self.get(workspace_id, change_set_id)
        validation = ValidationRun(
            id=new_id("validation"),
            change_set_id=change_set_id,
            kind=kind,
            attempt=change_set.repair_count + 1,
            status="running",
        )
        updated = change_set.model_copy(
            update={
                "status": "validating",
                "validations": [*change_set.validations, validation],
                "updated_at": datetime.now(UTC),
            }
        )
        return await self._repository.save(updated)

    async def mark_failed(
        self, workspace_id: str, change_set_id: str, *, needs_fix: bool = False
    ) -> ChangeSet:
        change_set = await self.get(workspace_id, change_set_id)
        status = "needs_fix" if needs_fix and change_set.repair_count == 0 else "failed"
        updated = change_set.model_copy(update={"status": status, "updated_at": datetime.now(UTC)})
        return await self._repository.save(updated)

    async def record_validation_error(
        self,
        workspace_id: str,
        change_set_id: str,
        *,
        kind: Literal["review", "preview"],
        error_code: str,
        error_message: str,
    ) -> ChangeSet:
        change_set = await self.get(workspace_id, change_set_id)
        validation = self._completed_validation(
            change_set,
            kind=kind,
            status="failed",
            error_code=error_code,
            error_message=error_message,
        )
        updated = change_set.model_copy(
            update={
                "status": "failed",
                "validations": self._replace_validation(change_set, validation),
                "updated_at": datetime.now(UTC),
            }
        )
        return await self._repository.save(updated)

    async def promote(
        self,
        workspace_id: str,
        change_set_id: str,
        *,
        preview_page_url: str,
    ) -> ChangeSetActionResponse:
        change_set = await self.get(workspace_id, change_set_id)
        if change_set.status != "ready":
            raise ConflictError(
                "change_set_not_ready",
                "Only a statically inspected and Review-ready change set can be promoted.",
            )
        await self.assert_candidate_integrity(workspace_id, change_set_id)
        promoting = change_set.model_copy(
            update={"status": "promoting", "updated_at": datetime.now(UTC)}
        )
        await self._repository.save(promoting)

        for file_record in change_set.files:
            canonical = self._canonical_file_path(workspace_id, file_record.path)
            exists = canonical.exists()
            current = (
                canonical.read_text(encoding="utf-8") if exists and canonical.is_file() else ""
            )
            if (
                exists != file_record.before_exists
                or _sha256_text(current) != file_record.before_sha256
            ):
                conflicted = promoting.model_copy(
                    update={"status": "conflicted", "updated_at": datetime.now(UTC)}
                )
                await self._repository.save(conflicted)
                raise ConflictError(
                    "workspace_conflict",
                    f"Workspace file '{file_record.path}' changed after validation.",
                )

        applied: list[ChangeSetFile] = []
        try:
            for file_record in change_set.files:
                self._apply_candidate_file(workspace_id, file_record, change_set.id)
                applied.append(file_record)
        except Exception:
            for file_record in reversed(applied):
                self._restore_before_snapshot(workspace_id, file_record, change_set.id)
            failed = promoting.model_copy(
                update={"status": "failed", "updated_at": datetime.now(UTC)}
            )
            await self._repository.save(failed)
            raise

        promoted_at = datetime.now(UTC)
        for file_record in change_set.files:
            await self._persist_promoted_file(workspace_id, change_set.id, file_record, promoted_at)

        preview_url = (
            f"{preview_page_url}?path={quote(change_set.entry_path)}"
            if change_set.entry_path
            else None
        )
        await self._workspace_service.set_preview(
            workspace_id,
            "ready" if change_set.entry_path else "not_started",
            preview_url,
            entry_path=change_set.entry_path,
            preserve_entry_path=False,
            preserve_preview_url=False,
        )
        promoted = promoting.model_copy(
            update={
                "status": "promoted",
                "promoted_at": promoted_at,
                "updated_at": promoted_at,
            }
        )
        await self._repository.save(promoted)
        self._remove_staging_dir(change_set.id)
        return ChangeSetActionResponse(change_set=promoted, message="Change set promoted.")

    async def assert_candidate_integrity(
        self,
        workspace_id: str,
        change_set_id: str,
    ) -> None:
        change_set = await self.get(workspace_id, change_set_id)
        for file_record in change_set.files:
            staged_path = self._staged_file_path(change_set.id, file_record.path)
            if file_record.operation == "delete":
                valid = not staged_path.exists()
            else:
                valid = (
                    staged_path.is_file()
                    and not staged_path.is_symlink()
                    and _sha256_text(staged_path.read_text(encoding="utf-8"))
                    == file_record.after_sha256
                )
            if valid:
                continue
            failed = change_set.model_copy(
                update={"status": "failed", "updated_at": datetime.now(UTC)}
            )
            await self._repository.save(failed)
            raise ConflictError(
                "candidate_snapshot_conflict",
                f"Staged candidate file '{file_record.path}' no longer matches its validated hash.",
            )

    async def reject(self, workspace_id: str, change_set_id: str) -> ChangeSetActionResponse:
        change_set = await self.get(workspace_id, change_set_id)
        if change_set.status == "promoted":
            raise ConflictError(
                "change_set_already_promoted",
                "Promoted changes cannot be rejected.",
            )
        rejected = change_set.model_copy(
            update={"status": "rejected", "updated_at": datetime.now(UTC)}
        )
        await self._repository.save(rejected)
        self._remove_staging_dir(change_set.id)
        return ChangeSetActionResponse(change_set=rejected, message="Change set rejected.")

    async def revert(self, workspace_id: str, change_set_id: str) -> ChangeSetRevertResponse:
        change_set = await self.get(workspace_id, change_set_id)
        if change_set.status != "promoted":
            raise ConflictError(
                "change_set_not_promoted", "Only a promoted change set can be reverted."
            )
        for file_record in change_set.files:
            canonical = self._canonical_file_path(workspace_id, file_record.path)
            current = canonical.read_text(encoding="utf-8") if canonical.exists() else ""
            expected = file_record.after_content or ""
            if _sha256_text(current) != _sha256_text(expected):
                raise ConflictError(
                    "change_set_revert_conflict",
                    f"Workspace file '{file_record.path}' changed after promotion.",
                )
        for file_record in reversed(change_set.files):
            self._restore_before_snapshot(workspace_id, file_record, change_set.id)
            if file_record.before_exists:
                await self._workspace_repository.save_file(
                    WorkspaceFileContent(
                        workspace_id=workspace_id,
                        path=file_record.path,
                        content=file_record.before_content,
                        updated_at=datetime.now(UTC),
                    )
                )
            else:
                await self._workspace_repository.delete_file(workspace_id, file_record.path)
        reverted_at = datetime.now(UTC)
        records = await self._workspace_repository.list_applied_diffs(workspace_id)
        for record in records:
            if record.change_set_id == change_set_id and record.reverted_at is None:
                await self._workspace_repository.save_applied_diff(
                    record.model_copy(update={"reverted_at": reverted_at})
                )
        entry_path = self._select_workspace_entry(workspace_id)
        current_preview = await self._workspace_service.get_preview(workspace_id)
        await self._workspace_service.set_preview(
            workspace_id,
            "ready" if entry_path else "not_started",
            current_preview.preview_url if entry_path else None,
            entry_path=entry_path,
            preserve_entry_path=False,
            preserve_preview_url=False,
        )
        return ChangeSetRevertResponse(
            change_set_id=change_set_id,
            workspace_id=workspace_id,
            reverted_paths=[item.path for item in change_set.files],
            reverted_at=reverted_at,
        )

    async def prepare_reapply(
        self,
        workspace_id: str,
        change_set_id: str,
    ) -> ChangeSet:
        """Create a new isolated candidate from a fully reverted change set."""
        original = await self.get(workspace_id, change_set_id)
        if original.status != "promoted":
            raise ConflictError(
                "change_set_not_promoted",
                "Only a previously promoted change set can be reapplied.",
            )
        applied_records = [
            record
            for record in await self._workspace_repository.list_applied_diffs(workspace_id)
            if record.change_set_id == change_set_id
        ]
        if not applied_records or any(record.reverted_at is None for record in applied_records):
            raise ConflictError(
                "change_set_not_reverted",
                "Reapply is available only after the entire change set has been reverted.",
            )

        for file_record in original.files:
            canonical = self._canonical_file_path(workspace_id, file_record.path)
            exists = canonical.exists()
            current = canonical.read_text(encoding="utf-8") if exists else ""
            if (
                exists != file_record.before_exists
                or _sha256_text(current) != file_record.before_sha256
            ):
                raise ConflictError(
                    "workspace_conflict",
                    f"Workspace file '{file_record.path}' changed after revert.",
                )

        operations = [
            {
                "path": file_record.path,
                "operation": file_record.operation,
                "content": file_record.after_content,
            }
            for file_record in original.files
        ]
        artifact = Artifact(
            id=f"artifact-reapply-{original.id}",
            type="file",
            title="Reapply candidate manifest",
            data={
                "kind": "candidate_manifest",
                "operations": operations,
                "file_count": len(operations),
            },
        )
        return await self.create_from_artifacts(
            conversation_id=original.conversation_id,
            workspace_id=workspace_id,
            artifacts=[artifact],
            source_message_id=original.source_message_id,
            parent_change_set_id=original.id,
            preview_checks=[],
        )

    async def prepare_re_review(
        self,
        workspace_id: str,
        change_set_id: str,
    ) -> ChangeSet:
        """Clone an immutable failed candidate into a fresh review-only Change Set."""

        original = await self.get(workspace_id, change_set_id)
        if original.status != "failed":
            raise ConflictError(
                "change_set_not_failed",
                "Only a failed change set can be submitted for a fresh code review.",
            )
        operations: list[dict[str, object]] = []
        for file_record in original.files:
            if file_record.operation == "upsert" and file_record.after_content is None:
                raise ConflictError(
                    "candidate_snapshot_incomplete",
                    f"Candidate file '{file_record.path}' has no immutable after snapshot.",
                )
            operations.append(
                {
                    "path": file_record.path,
                    "operation": file_record.operation,
                    "content": file_record.after_content,
                }
            )
        if not operations:
            raise ConflictError(
                "candidate_snapshot_incomplete",
                "The failed change set does not contain any candidate files.",
            )
        artifact = Artifact(
            id=f"artifact-rereview-{original.id}",
            type="file",
            title="Re-review candidate manifest",
            data={
                "kind": "candidate_manifest",
                "operations": operations,
                "file_count": len(operations),
            },
        )
        return await self.create_from_artifacts(
            conversation_id=original.conversation_id,
            workspace_id=workspace_id,
            artifacts=[artifact],
            source_message_id=original.source_message_id,
            parent_change_set_id=original.id,
            repair_count=0,
            preview_checks=[],
        )

    def get_staged_file_bytes(self, change_set_id: str, path: str) -> bytes:
        file_path = self._staged_file_path(change_set_id, path)
        if not file_path.exists() or not file_path.is_file():
            raise NotFoundError("preview_file_not_found", "Preview file does not exist.")
        return file_path.read_bytes()

    def get_preview_file_bytes(self, change_set: ChangeSet, path: str) -> bytes:
        """Read the exact candidate snapshot that static inspection and Review used.

        Active candidates are served from staging. Terminal snapshots may outlive
        their staging directory, so their preview falls back to immutable
        ``after_content`` instead of the mutable formal workspace.
        """
        try:
            return self.get_staged_file_bytes(change_set.id, path)
        except NotFoundError:
            if self.staging_dir(change_set.id).exists() or change_set.status not in {
                "promoted",
                "failed",
                "rejected",
                "conflicted",
            }:
                raise

        try:
            normalized_path = normalize_workspace_file_path(path)
        except WorkspacePathError as exc:
            raise BadRequestError("invalid_workspace_path", str(exc)) from exc

        file_record = next(
            (item for item in change_set.files if item.path == normalized_path),
            None,
        )
        if (
            file_record is None
            or file_record.operation != "upsert"
            or file_record.after_content is None
        ):
            raise NotFoundError("preview_file_not_found", "Preview file does not exist.")
        if _sha256_text(file_record.after_content) != file_record.after_sha256:
            raise ConflictError(
                "candidate_snapshot_conflict",
                f"Stored candidate file '{normalized_path}' no longer matches its validated hash.",
            )
        return file_record.after_content.encode("utf-8")

    def get_screenshot_bytes(self, change_set_id: str) -> bytes:
        path = self.screenshot_file(change_set_id)
        if not path.exists():
            raise NotFoundError(
                "preview_screenshot_not_found",
                "Preview screenshot does not exist.",
            )
        return path.read_bytes()

    def staging_dir(self, change_set_id: str) -> Path:
        try:
            return resolve_workspace_path(self._staging_root, change_set_id)
        except WorkspacePathError as exc:
            raise BadRequestError("invalid_change_set_id", str(exc)) from exc

    def screenshot_file(self, change_set_id: str) -> Path:
        try:
            directory = resolve_workspace_path(self._preview_artifact_root, change_set_id)
            return resolve_workspace_path(directory, "screenshot.png")
        except WorkspacePathError as exc:
            raise BadRequestError("invalid_change_set_id", str(exc)) from exc

    def _generated_files_from_artifacts(
        self, artifacts: Sequence[Artifact]
    ) -> dict[str, tuple[Literal["upsert", "delete"], str | None]]:
        generated: dict[str, tuple[Literal["upsert", "delete"], str | None]] = {}
        for artifact in artifacts:
            candidates: list[object] = []
            if artifact.type == "code":
                candidates = [
                    {
                        "path": artifact.data.get("filename"),
                        "operation": "upsert",
                        "content": artifact.data.get("content"),
                    }
                ]
            elif isinstance(artifact.data.get("operations"), list):
                candidates = list(artifact.data["operations"])
            for candidate in candidates:
                if not isinstance(candidate, dict):
                    continue
                path = candidate.get("path")
                operation = candidate.get("operation", "upsert")
                content = candidate.get("content")
                if not isinstance(path, str) or operation not in {"upsert", "delete"}:
                    continue
                if operation == "upsert" and not isinstance(content, str):
                    continue
                try:
                    normalized = normalize_workspace_file_path(path)
                except WorkspacePathError as exc:
                    raise BadRequestError("invalid_workspace_path", str(exc)) from exc
                generated[normalized] = (
                    cast(Literal["upsert", "delete"], operation),
                    content if isinstance(content, str) else None,
                )
        return generated

    def _workspace_dir(self, workspace_id: str) -> Path:
        try:
            return resolve_workspace_path(self._workspace_root, workspace_id)
        except WorkspacePathError as exc:
            raise BadRequestError("invalid_workspace_id", str(exc)) from exc

    def _canonical_file_path(self, workspace_id: str, path: str) -> Path:
        try:
            return resolve_workspace_path(self._workspace_dir(workspace_id), path)
        except WorkspacePathError as exc:
            raise BadRequestError("invalid_workspace_path", str(exc)) from exc

    def _staged_file_path(self, change_set_id: str, path: str) -> Path:
        try:
            normalized = normalize_workspace_file_path(path)
            return resolve_workspace_path(self.staging_dir(change_set_id), normalized)
        except WorkspacePathError as exc:
            raise BadRequestError("invalid_workspace_path", str(exc)) from exc

    def _select_entry_path(self, staging_dir: Path, files: Sequence[ChangeSetFile]) -> str | None:
        if (staging_dir / "index.html").is_file():
            return "index.html"
        candidates = sorted(
            item.path
            for item in files
            if item.operation == "upsert" and item.path.lower().endswith((".html", ".htm"))
        )
        return candidates[0] if candidates else None

    def _select_workspace_entry(self, workspace_id: str) -> str | None:
        workspace_dir = self._workspace_dir(workspace_id)
        if (workspace_dir / "index.html").is_file():
            return "index.html"
        if not workspace_dir.exists():
            return None
        candidates = sorted(
            path.relative_to(workspace_dir).as_posix()
            for path in workspace_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in {".html", ".htm"}
        )
        return candidates[0] if candidates else None

    def _recompute_validation_status(self, change_set: ChangeSet) -> ChangeSet:
        review = change_set.review_report
        if review is None:
            return change_set.model_copy(update={"status": "validating"})
        if review.verdict in {"pass", "pass_with_warnings"}:
            return change_set.model_copy(update={"status": "ready"})
        return change_set.model_copy(
            update={"status": "needs_fix" if change_set.repair_count == 0 else "failed"}
        )

    def _completed_validation(
        self,
        change_set: ChangeSet,
        *,
        kind: Literal["review", "preview"],
        status: Literal["passed", "failed"],
        report: dict[str, object] | None = None,
        error_code: str = "",
        error_message: str = "",
    ) -> ValidationRun:
        running = next(
            (
                item
                for item in reversed(change_set.validations)
                if item.kind == kind and item.status == "running"
            ),
            None,
        )
        if running is None:
            running = ValidationRun(
                id=new_id("validation"),
                change_set_id=change_set.id,
                kind=kind,
                attempt=change_set.repair_count + 1,
                status="running",
            )
        return running.model_copy(
            update={
                "status": status,
                "report": report or {},
                "error_code": error_code,
                "error_message": error_message,
                "completed_at": datetime.now(UTC),
            }
        )

    def _replace_validation(
        self,
        change_set: ChangeSet,
        validation: ValidationRun,
    ) -> builtins.list[ValidationRun]:
        return [
            *(item for item in change_set.validations if item.id != validation.id),
            validation,
        ]

    def _apply_candidate_file(
        self, workspace_id: str, file_record: ChangeSetFile, change_set_id: str
    ) -> None:
        target = self._canonical_file_path(workspace_id, file_record.path)
        if file_record.operation == "delete":
            if target.exists():
                target.unlink()
            return
        if file_record.after_content is None:
            raise BadRequestError("invalid_candidate_file", "Candidate content is missing.")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{change_set_id}.tmp")
        temporary.write_text(file_record.after_content, encoding="utf-8")
        os.replace(temporary, target)

    def _restore_before_snapshot(
        self, workspace_id: str, file_record: ChangeSetFile, change_set_id: str
    ) -> None:
        target = self._canonical_file_path(workspace_id, file_record.path)
        if not file_record.before_exists:
            if target.exists():
                target.unlink()
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{change_set_id}.rollback.tmp")
        temporary.write_text(file_record.before_content, encoding="utf-8")
        os.replace(temporary, target)

    async def _persist_promoted_file(
        self,
        workspace_id: str,
        change_set_id: str,
        file_record: ChangeSetFile,
        applied_at: datetime,
    ) -> None:
        if file_record.operation == "delete":
            await self._workspace_repository.delete_file(workspace_id, file_record.path)
        else:
            await self._workspace_repository.save_file(
                WorkspaceFileContent(
                    workspace_id=workspace_id,
                    path=file_record.path,
                    content=file_record.after_content or "",
                    updated_at=applied_at,
                )
            )
        await self._workspace_repository.save_applied_diff(
            AppliedDiffRecord(
                id=new_id("apply"),
                workspace_id=workspace_id,
                artifact_id=f"change-set-{change_set_id}-{file_record.id}",
                diff=file_record.diff,
                path=file_record.path,
                before_content=file_record.before_content,
                after_content=file_record.after_content,
                before_exists=file_record.before_exists,
                change_set_id=change_set_id,
                applied_at=applied_at,
            )
        )

    def _remove_staging_dir(self, change_set_id: str) -> None:
        target = self.staging_dir(change_set_id)
        if target.exists():
            shutil.rmtree(target)

    def cleanup_expired_artifacts(self, now_timestamp: float | None = None) -> None:
        now = now_timestamp if now_timestamp is not None else datetime.now(UTC).timestamp()
        for root, ttl_seconds in (
            (self._staging_root, self._staging_ttl_seconds),
            (self._preview_artifact_root, self._preview_artifact_ttl_seconds),
        ):
            if not root.exists():
                continue
            for child in root.iterdir():
                if not child.is_dir() or now - child.stat().st_mtime <= ttl_seconds:
                    continue
                shutil.rmtree(child)

    def _reject_symlinks(self, source: Path) -> None:
        if any(path.is_symlink() for path in source.rglob("*")):
            raise BadRequestError(
                "workspace_symlink_not_supported",
                "Symlinks are not allowed in a preview workspace.",
            )


def _sha256_text(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _snapshot_sha256(files: list[ChangeSetFile]) -> str:
    digest = hashlib.sha256()
    for file_record in sorted(files, key=lambda item: item.path):
        digest.update(file_record.path.encode("utf-8"))
        digest.update(file_record.before_sha256.encode("ascii"))
        digest.update(b"1" if file_record.before_exists else b"0")
    return digest.hexdigest()
