from __future__ import annotations

from pathlib import Path

import pytest

from agenthub.repositories.change_set_repo import ChangeSetRepository
from agenthub.repositories.workspace_repo import WorkspaceRepository
from agenthub.schemas.artifact import Artifact
from agenthub.services.change_set_service import ChangeSetService
from agenthub.services.static_review import StaticCandidateInspector
from agenthub.services.workspace_service import WorkspaceService


def build_service(tmp_path: Path) -> ChangeSetService:
    workspace_repository = WorkspaceRepository()
    workspace_service = WorkspaceService(workspace_repository, tmp_path / "workspaces")
    return ChangeSetService(
        ChangeSetRepository(),
        workspace_repository,
        workspace_service,
        workspace_root=tmp_path / "workspaces",
        staging_root=tmp_path / ".agenthub" / "staging",
        preview_artifact_root=tmp_path / ".agenthub" / "preview-artifacts",
    )


def code_artifact(path: str, content: str) -> Artifact:
    return Artifact(
        id=f"artifact-{path}",
        type="code",
        title=path,
        data={"filename": path, "content": content},
    )


@pytest.mark.asyncio
async def test_static_inspector_accepts_self_contained_local_assets(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    change_set = await service.create_from_artifacts(
        conversation_id="conv-static-pass",
        workspace_id="ws-static-pass",
        artifacts=[
            code_artifact(
                "index.html",
                "<!doctype html><link rel='stylesheet' href='styles.css'>"
                "<main>Ready</main><script src='script.js'></script>",
            ),
            code_artifact("styles.css", "main { background: url('./dot.svg'); }"),
            code_artifact("script.js", "document.body.dataset.ready = 'true';"),
            code_artifact("dot.svg", "<svg xmlns='http://www.w3.org/2000/svg'></svg>"),
        ],
    )

    findings = StaticCandidateInspector().inspect(
        change_set,
        service.staging_dir(change_set.id),
    )

    assert findings == []


@pytest.mark.asyncio
async def test_static_inspector_blocks_only_deterministic_resource_violations(
    tmp_path: Path,
) -> None:
    service = build_service(tmp_path)
    change_set = await service.create_from_artifacts(
        conversation_id="conv-static-fail",
        workspace_id="ws-static-fail",
        artifacts=[
            code_artifact(
                "index.html",
                "<!doctype html><link rel='stylesheet' href='missing.css'>"
                "<script src='https://example.com/app.js'></script>",
            )
        ],
    )

    findings = StaticCandidateInspector().inspect(
        change_set,
        service.staging_dir(change_set.id),
    )

    assert {finding.category for finding in findings} == {
        "static_external_resource",
        "static_missing_local_resource",
    }
    assert all(finding.severity == "blocker" for finding in findings)
    assert all(finding.path == "index.html" for finding in findings)
    assert all(finding.evidence for finding in findings)


@pytest.mark.asyncio
async def test_static_inspector_does_not_treat_navigation_as_a_resource(
    tmp_path: Path,
) -> None:
    service = build_service(tmp_path)
    change_set = await service.create_from_artifacts(
        conversation_id="conv-static-navigation",
        workspace_id="ws-static-navigation",
        artifacts=[
            code_artifact(
                "index.html",
                "<!doctype html><a href='https://example.com/help'>帮助</a>"
                "<form action='/submit'><button>提交</button></form>",
            )
        ],
    )

    findings = StaticCandidateInspector().inspect(
        change_set,
        service.staging_dir(change_set.id),
    )

    assert findings == []
