from agenthub.agents.base import AgentAdapter
from agenthub.agents.real_agent import RealAgentSchemaError
from agenthub.core.errors import AgentExecutionError
from agenthub.schemas.agent import AgentRunInput, AgentRunResult, ReviewReport
from agenthub.schemas.artifact import Artifact


class ReviewAgent:
    id = "review-agent"
    name = "Review Agent"
    capabilities = ["review", "quality", "risk"]

    def __init__(self, llm: AgentAdapter) -> None:
        self._llm = llm

    async def run(self, input_data: AgentRunInput) -> AgentRunResult:
        run_structured = getattr(self._llm, "run_structured", None)
        if not callable(run_structured):
            raise AgentExecutionError("Review Agent requires a structured model adapter.")
        llm_input = input_data.model_copy(
            update={
                "context": {
                    **input_data.context,
                    "agent_id": self.id,
                    "agent_role": "review",
                }
            }
        )
        try:
            report = await run_structured(
                llm_input,
                ReviewReport,
                schema_name="ReviewReport",
            )
        except RealAgentSchemaError as exc:
            raise AgentExecutionError(
                "Review Agent model output could not be parsed after one format repair."
            ) from exc
        return _agent_result_from_review_report(report, input_data.workspace_id)


def _agent_result_from_review_report(report: ReviewReport, workspace_id: str) -> AgentRunResult:
    finding_lines = [f"- [{item.severity}] {item.message}" for item in report.findings]
    content = report.summary.strip()
    if finding_lines:
        content += "\n\n" + "\n".join(finding_lines)
    return AgentRunResult(
        agent_id="review-agent",
        content=content,
        artifacts=[
            Artifact(
                id=f"artifact-review-{workspace_id}",
                type="file",
                title="Review report",
                data={
                    **report.model_dump(mode="json"),
                    "workspace_id": workspace_id,
                },
            )
        ],
        next_actions=["promote"] if report.verdict != "fail" else [],
    )


REVIEW_AGENT_SYSTEM_PROMPT = """
You are AgentHub Review Agent.
Return only one JSON object matching ReviewReport exactly:
{"verdict":"pass","risk_level":"low","summary":"...","findings":[],"covered_criteria":[]}

Rules:
- Review only the staged candidate files and acceptance criteria in context.
- Focus on correctness, user requirements, demo stability, workspace safety, and
  concrete code defects. Browser execution is not part of this workflow.
- Return file-level findings with severity, category, message, suggestion,
  criterion_id, evidence, path, and optional line.
- Use verdict=fail only when at least one finding has severity=blocker. High,
  warning, and info findings are non-blocking and require pass_with_warnings.
- Every blocker must reference a declared acceptance criterion, identify the exact
  candidate path, and quote concrete code evidence that demonstrates the violation.
- Do not use blocker for testing style, selector preference, missing extra coverage,
  a hypothetical runtime problem, or preferring one valid UI implementation.
- Native HTML validation and custom validation are both valid when they satisfy the
  requirement. Do not require implementation-specific error elements.
- Review every acceptance criterion and list its ID in covered_criteria. If the code
  cannot prove a runtime behavior, state the uncertainty as a warning rather than
  inventing a blocker.
- Deterministic static safety findings may be present in context.static_findings;
  account for them in the verdict but do not duplicate them in findings. The backend
  appends those authoritative findings to the final report.
- Do not invent applied changes, browser results, screenshots, or URLs.
""".strip()
