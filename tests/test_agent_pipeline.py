from __future__ import annotations

from pathlib import Path

import pytest

from agenthub.agents.registry import AgentRegistry
from agenthub.orchestrator.planner import AgentTask, OrchestratorDecision, OrchestratorPlan
from agenthub.repositories.change_set_repo import ChangeSetRepository
from agenthub.repositories.workspace_repo import WorkspaceRepository
from agenthub.schemas.agent import AcceptanceCriterion, AgentRunInput, AgentRunResult
from agenthub.schemas.artifact import Artifact
from agenthub.services.agent_service import AgentService
from agenthub.services.change_set_service import ChangeSetService
from agenthub.services.workspace_service import WorkspaceService


class PlanningOrchestrator:
    id = "orchestrator"
    name = "Orchestrator"
    capabilities = ["planning"]

    async def decide(self, input_data: AgentRunInput) -> OrchestratorDecision:
        del input_data
        return OrchestratorDecision(
            mode="plan",
            content="Review the candidate.",
            plan=OrchestratorPlan(
                summary="test",
                tasks=[
                    AgentTask(task_id="task-code", agent_id="code-agent", instruction="code"),
                    AgentTask(
                        task_id="task-review",
                        agent_id="review-agent",
                        instruction="review",
                        depends_on=["task-code"],
                    ),
                ],
                acceptance_criteria=[
                    AcceptanceCriterion(
                        id="criterion-1",
                        description="The requested page is implemented.",
                    )
                ],
            ),
        )

    async def run(self, input_data: AgentRunInput) -> AgentRunResult:
        decision = await self.decide(input_data)
        return AgentRunResult(agent_id=self.id, content=decision.content)


class CountingCodeAgent:
    id = "code-agent"
    name = "Code Agent"
    capabilities = ["code"]

    def __init__(self) -> None:
        self.calls = 0

    async def run(self, input_data: AgentRunInput) -> AgentRunResult:
        del input_data
        self.calls += 1
        return AgentRunResult(
            agent_id=self.id,
            content=f"candidate {self.calls}",
            artifacts=[
                Artifact(
                    id=f"code-{self.calls}",
                    type="code",
                    title="index.html",
                    data={
                        "filename": "index.html",
                        "content": f"<!doctype html><h1>attempt {self.calls}</h1>",
                    },
                )
            ],
        )


class PassingReviewAgent:
    id = "review-agent"
    name = "Review Agent"
    capabilities = ["review"]

    async def run(self, input_data: AgentRunInput) -> AgentRunResult:
        criterion_ids = [
            item["id"]
            for item in input_data.context.get("acceptance_criteria", [])
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        ]
        return AgentRunResult(
            agent_id=self.id,
            content="Review passed.",
            artifacts=[
                Artifact(
                    id="review-pass",
                    type="file",
                    title="ReviewReport",
                    data={
                        "verdict": "pass",
                        "risk_level": "low",
                        "summary": "The candidate implements the requested page.",
                        "findings": [],
                        "covered_criteria": criterion_ids,
                    },
                )
            ],
        )


class EvidenceBlockerReviewAgent:
    id = "review-agent"
    name = "Review Agent"
    capabilities = ["review"]

    async def run(self, input_data: AgentRunInput) -> AgentRunResult:
        criterion_id = input_data.context["acceptance_criteria"][0]["id"]
        return AgentRunResult(
            agent_id=self.id,
            content="Review found a concrete blocker.",
            artifacts=[
                Artifact(
                    id="review-fail",
                    type="file",
                    title="ReviewReport",
                    data={
                        "verdict": "fail",
                        "risk_level": "high",
                        "summary": "The primary requirement is absent.",
                        "findings": [
                            {
                                "severity": "blocker",
                                "category": "behavior",
                                "criterion_id": criterion_id,
                                "path": "index.html",
                                "evidence": "The candidate only contains a heading.",
                                "message": "The required primary behavior is missing.",
                                "suggestion": "Implement the requested behavior.",
                            }
                        ],
                        "covered_criteria": [criterion_id],
                    },
                )
            ],
        )


class UnsupportedBlockerReviewAgent:
    id = "review-agent"
    name = "Review Agent"
    capabilities = ["review"]

    async def run(self, input_data: AgentRunInput) -> AgentRunResult:
        criterion_ids = [item["id"] for item in input_data.context["acceptance_criteria"]]
        return AgentRunResult(
            agent_id=self.id,
            content="A hypothetical selector concern remains.",
            artifacts=[
                Artifact(
                    id="review-warning",
                    type="file",
                    title="ReviewReport",
                    data={
                        "verdict": "fail",
                        "risk_level": "high",
                        "summary": "The implementation is complete.",
                        "findings": [
                            {
                                "severity": "blocker",
                                "category": "ui_selector",
                                "message": "A selector might be repeated.",
                                "suggestion": "Consider scoping it.",
                            }
                        ],
                        "covered_criteria": criterion_ids,
                    },
                )
            ],
        )


class PlaceholderPreviewAgent:
    id = "preview-agent"
    name = "Preview Agent"
    capabilities = ["preview"]

    async def run(self, input_data: AgentRunInput) -> AgentRunResult:
        del input_data
        raise AssertionError("The model Preview Agent must never run.")


def build_services(
    tmp_path: Path,
    review_agent: object,
) -> tuple[AgentService, ChangeSetService, CountingCodeAgent]:
    workspace_repository = WorkspaceRepository()
    workspace_service = WorkspaceService(workspace_repository, tmp_path / "workspaces")
    change_set_service = ChangeSetService(
        ChangeSetRepository(),
        workspace_repository,
        workspace_service,
        workspace_root=tmp_path / "workspaces",
        staging_root=tmp_path / ".agenthub" / "staging",
        preview_artifact_root=tmp_path / ".agenthub" / "preview-artifacts",
    )
    code_agent = CountingCodeAgent()
    service = AgentService(
        AgentRegistry(
            [PlanningOrchestrator(), code_agent, review_agent, PlaceholderPreviewAgent()]
        ),
        change_set_service=change_set_service,
    )
    return service, change_set_service, code_agent


@pytest.mark.asyncio
async def test_review_pass_reaches_ready_without_preview_report(tmp_path: Path) -> None:
    service, change_set_service, code_agent = build_services(tmp_path, PassingReviewAgent())

    results = await service.run_for_message(
        AgentRunInput(
            conversation_id="conv-pass",
            workspace_id="ws-pass",
            user_message="@Orchestrator build a page",
        )
    )

    assert [result.agent_id for result in results] == [
        "orchestrator",
        "code-agent",
        "review-agent",
    ]
    assert code_agent.calls == 1
    [change_set] = await change_set_service.list("ws-pass")
    assert change_set.status == "ready"
    assert change_set.review_report is not None
    assert change_set.preview_report is None
    assert [(item.kind, item.status) for item in change_set.validations] == [("review", "passed")]
    assert not (tmp_path / "workspaces" / "ws-pass" / "index.html").exists()


@pytest.mark.asyncio
async def test_unsupported_blocker_is_warning_and_does_not_trigger_repair(
    tmp_path: Path,
) -> None:
    service, change_set_service, code_agent = build_services(
        tmp_path,
        UnsupportedBlockerReviewAgent(),
    )

    results = await service.run_for_message(
        AgentRunInput(
            conversation_id="conv-warning",
            workspace_id="ws-warning",
            user_message="@Orchestrator build a page",
        )
    )

    assert code_agent.calls == 1
    review_result = next(item for item in results if item.agent_id == "review-agent")
    review_artifact = next(item for item in review_result.artifacts if item.type == "file")
    assert review_artifact.data["verdict"] == "pass_with_warnings"
    [change_set] = await change_set_service.list("ws-warning")
    assert change_set.status == "ready"


@pytest.mark.asyncio
async def test_evidenced_review_blocker_repairs_once_then_stops(tmp_path: Path) -> None:
    service, change_set_service, code_agent = build_services(
        tmp_path,
        EvidenceBlockerReviewAgent(),
    )

    results = await service.run_for_message(
        AgentRunInput(
            conversation_id="conv-fail",
            workspace_id="ws-fail",
            user_message="@CodeAgent build a page",
        )
    )

    assert [result.agent_id for result in results] == [
        "code-agent",
        "review-agent",
        "code-agent",
        "review-agent",
    ]
    assert code_agent.calls == 2
    change_sets = await change_set_service.list("ws-fail")
    assert {item.repair_count for item in change_sets} == {0, 1}
    repaired = next(item for item in change_sets if item.repair_count == 1)
    assert repaired.status == "failed"
    assert repaired.preview_report is None
    assert [(item.kind, item.status) for item in repaired.validations] == [("review", "failed")]
    assert not (tmp_path / "workspaces" / "ws-fail" / "index.html").exists()


@pytest.mark.asyncio
async def test_explicit_preview_returns_manual_link_without_changing_status(
    tmp_path: Path,
) -> None:
    service, change_set_service, _ = build_services(tmp_path, PassingReviewAgent())
    await service.run_for_message(
        AgentRunInput(
            conversation_id="conv-preview",
            workspace_id="ws-preview",
            user_message="@CodeAgent build a page",
        )
    )
    [before] = await change_set_service.list("ws-preview")
    assert before.status == "ready"

    [result] = await service.run_for_message(
        AgentRunInput(
            conversation_id="conv-preview",
            workspace_id="ws-preview",
            user_message="@PreviewAgent open the candidate preview",
        )
    )

    artifact = result.artifacts[0]
    assert artifact.type == "preview"
    assert artifact.data == {
        "preview_status": "available",
        "scope": "candidate",
        "workspace_id": "ws-preview",
        "change_set_id": before.id,
        "entry_path": "index.html",
    }
    after = await change_set_service.get("ws-preview", before.id)
    assert after.status == "ready"
    assert after.preview_report is None
