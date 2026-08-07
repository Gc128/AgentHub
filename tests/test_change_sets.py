from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from agenthub.core.errors import ConflictError
from agenthub.repositories.change_set_repo import ChangeSetRepository
from agenthub.repositories.workspace_repo import WorkspaceRepository
from agenthub.schemas.agent import (
    BrowserStep,
    ReviewReport,
)
from agenthub.schemas.artifact import Artifact
from agenthub.schemas.workspace import WorkspaceFileWriteRequest
from agenthub.services.change_set_service import ChangeSetService
from agenthub.services.workspace_service import WorkspaceService


def build_service(tmp_path: Path) -> tuple[ChangeSetService, WorkspaceService]:
    workspace_repository = WorkspaceRepository()
    workspace_service = WorkspaceService(workspace_repository, tmp_path / "workspaces")
    return (
        ChangeSetService(
            ChangeSetRepository(),
            workspace_repository,
            workspace_service,
            workspace_root=tmp_path / "workspaces",
            staging_root=tmp_path / ".agenthub" / "staging",
            preview_artifact_root=tmp_path / ".agenthub" / "preview-artifacts",
        ),
        workspace_service,
    )


def code_artifact(path: str, content: str) -> Artifact:
    return Artifact(
        id=f"code-{path}",
        type="code",
        title=path,
        data={"filename": path, "content": content, "language": "html"},
    )


def passing_review() -> ReviewReport:
    return ReviewReport(
        verdict="pass",
        risk_level="low",
        summary="Candidate matches the acceptance criteria.",
        findings=[],
        covered_criteria=["criterion-primary-flow"],
    )


@pytest.mark.asyncio
async def test_candidate_stays_isolated_until_promote_and_reverts_as_group(
    tmp_path: Path,
) -> None:
    service, workspace_service = build_service(tmp_path)
    workspace_id = "ws-isolated"
    original = "<!doctype html><h1>Original</h1>"
    candidate = "<!doctype html><h1>Candidate</h1>"
    await workspace_service.write_file(
        workspace_id,
        WorkspaceFileWriteRequest(path="index.html", content=original),
    )

    change_set = await service.create_from_artifacts(
        conversation_id="conv-1",
        workspace_id=workspace_id,
        artifacts=[code_artifact("index.html", candidate)],
    )

    canonical = tmp_path / "workspaces" / workspace_id / "index.html"
    staged = service.staging_dir(change_set.id) / "index.html"
    assert canonical.read_text(encoding="utf-8") == original
    assert staged.read_text(encoding="utf-8") == candidate
    assert change_set.files[0].diff.startswith("--- a/index.html")

    ready = await service.set_review_report(workspace_id, change_set.id, passing_review())
    assert ready.status == "ready"
    assert ready.preview_report is None

    promoted = await service.promote(
        workspace_id,
        change_set.id,
        preview_page_url="http://127.0.0.1:8000/api/workspaces/ws-isolated/preview-page",
    )
    assert promoted.change_set.status == "promoted"
    assert canonical.read_text(encoding="utf-8") == candidate
    assert not service.staging_dir(change_set.id).exists()
    assert service.get_preview_file_bytes(promoted.change_set, "index.html") == (
        candidate.encode("utf-8")
    )
    records = await workspace_service.list_applied_diffs(workspace_id)
    assert {record.change_set_id for record in records} == {change_set.id}

    reverted = await service.revert(workspace_id, change_set.id)
    assert reverted.reverted_paths == ["index.html"]
    assert canonical.read_text(encoding="utf-8") == original

    reapply = await service.prepare_reapply(workspace_id, change_set.id)
    assert reapply.parent_change_set_id == change_set.id
    assert reapply.id != change_set.id
    assert reapply.status == "validating"
    assert canonical.read_text(encoding="utf-8") == original
    assert (service.staging_dir(reapply.id) / "index.html").read_text(encoding="utf-8") == candidate

    reapply_ready = await service.set_review_report(
        workspace_id,
        reapply.id,
        passing_review(),
    )
    assert reapply_ready.status == "ready"
    await service.promote(
        workspace_id,
        reapply.id,
        preview_page_url="http://127.0.0.1:8000/api/workspaces/ws-isolated/preview-page",
    )
    assert canonical.read_text(encoding="utf-8") == candidate


@pytest.mark.asyncio
async def test_failed_snapshot_can_create_immutable_review_only_child(tmp_path: Path) -> None:
    service, _ = build_service(tmp_path)
    original = await service.create_from_artifacts(
        conversation_id="conv-rereview",
        workspace_id="ws-rereview",
        artifacts=[code_artifact("index.html", "<!doctype html><main>candidate</main>")],
    )
    failed = await service.mark_failed("ws-rereview", original.id)
    assert failed.status == "failed"

    child = await service.prepare_re_review("ws-rereview", original.id)

    assert child.id != original.id
    assert child.parent_change_set_id == original.id
    assert child.status == "validating"
    assert child.preview_checks == []
    assert child.files[0].after_content == original.files[0].after_content
    assert (service.staging_dir(child.id) / "index.html").read_text(encoding="utf-8") == (
        "<!doctype html><main>candidate</main>"
    )
    assert (await service.get("ws-rereview", original.id)).status == "failed"


@pytest.mark.asyncio
async def test_promote_detects_workspace_conflict_without_overwrite(tmp_path: Path) -> None:
    service, workspace_service = build_service(tmp_path)
    workspace_id = "ws-conflict"
    await workspace_service.write_file(
        workspace_id,
        WorkspaceFileWriteRequest(path="index.html", content="base"),
    )
    change_set = await service.create_from_artifacts(
        conversation_id="conv-1",
        workspace_id=workspace_id,
        artifacts=[code_artifact("index.html", "candidate")],
    )
    await service.set_review_report(workspace_id, change_set.id, passing_review())
    await workspace_service.write_file(
        workspace_id,
        WorkspaceFileWriteRequest(path="index.html", content="concurrent edit"),
    )

    with pytest.raises(ConflictError, match="changed after validation"):
        await service.promote(
            workspace_id,
            change_set.id,
            preview_page_url="http://127.0.0.1:8000/preview-page",
        )

    assert (tmp_path / "workspaces" / workspace_id / "index.html").read_text(
        encoding="utf-8"
    ) == "concurrent edit"
    assert (await service.get(workspace_id, change_set.id)).status == "conflicted"


@pytest.mark.asyncio
async def test_promote_rejects_a_tampered_staging_snapshot(tmp_path: Path) -> None:
    service, workspace_service = build_service(tmp_path)
    workspace_id = "ws-candidate-integrity"
    await workspace_service.write_file(
        workspace_id,
        WorkspaceFileWriteRequest(path="index.html", content="formal"),
    )
    change_set = await service.create_from_artifacts(
        conversation_id="conv-1",
        workspace_id=workspace_id,
        artifacts=[code_artifact("index.html", "reviewed candidate")],
    )
    await service.set_review_report(workspace_id, change_set.id, passing_review())
    (service.staging_dir(change_set.id) / "index.html").write_text(
        "tampered after validation",
        encoding="utf-8",
    )

    with pytest.raises(ConflictError, match="validated hash"):
        await service.promote(
            workspace_id,
            change_set.id,
            preview_page_url="http://127.0.0.1:8000/preview-page",
        )

    formal = tmp_path / "workspaces" / workspace_id / "index.html"
    assert formal.read_text(encoding="utf-8") == "formal"
    assert (await service.get(workspace_id, change_set.id)).status == "failed"


@pytest.mark.asyncio
async def test_multi_file_promote_rolls_back_when_a_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, workspace_service = build_service(tmp_path)
    workspace_id = "ws-rollback"
    originals = {"index.html": "original html", "styles.css": "original css"}
    for path, content in originals.items():
        await workspace_service.write_file(
            workspace_id,
            WorkspaceFileWriteRequest(path=path, content=content),
        )
    change_set = await service.create_from_artifacts(
        conversation_id="conv-1",
        workspace_id=workspace_id,
        artifacts=[
            code_artifact("index.html", "candidate html"),
            code_artifact("styles.css", "candidate css"),
        ],
    )
    await service.set_review_report(workspace_id, change_set.id, passing_review())

    original_apply = service._apply_candidate_file
    calls = 0

    def fail_second_write(workspace: str, file_record: object, change_set_id: str) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated atomic write failure")
        original_apply(workspace, file_record, change_set_id)  # type: ignore[arg-type]

    monkeypatch.setattr(service, "_apply_candidate_file", fail_second_write)

    with pytest.raises(OSError, match="simulated atomic write failure"):
        await service.promote(
            workspace_id,
            change_set.id,
            preview_page_url="http://127.0.0.1:8000/preview-page",
        )

    for path, content in originals.items():
        assert (tmp_path / "workspaces" / workspace_id / path).read_text() == content
    assert (await service.get(workspace_id, change_set.id)).status == "failed"
    assert await workspace_service.list_applied_diffs(workspace_id) == []


def test_browser_step_schema_rejects_non_whitelisted_or_incomplete_actions() -> None:
    with pytest.raises(ValidationError):
        BrowserStep(action="click")
    with pytest.raises(ValidationError):
        BrowserStep.model_validate({"action": "evaluate", "value": "alert(1)"})
    with pytest.raises(ValidationError):
        BrowserStep(action="assert_count", selector="li")
    with pytest.raises(ValidationError):
        BrowserStep(action="assert_min_count", selector="li")
