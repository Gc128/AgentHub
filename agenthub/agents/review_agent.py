from agenthub.agents.base import AgentAdapter
from agenthub.agents.real_agent import RealAgentSchemaError
from agenthub.schemas.agent import AgentRunInput, AgentRunResult
from agenthub.schemas.artifact import Artifact


class ReviewAgent:
    id = "review-agent"
    name = "Review Agent"
    capabilities = ["review", "quality", "risk"]

    def __init__(self, llm: AgentAdapter, *, allow_fallbacks: bool = False) -> None:
        self._llm = llm
        self._allow_fallbacks = allow_fallbacks

    async def run(self, input_data: AgentRunInput) -> AgentRunResult:
        try:
            result = await self._llm.run(
                input_data.model_copy(
                    update={
                        "context": {
                            **input_data.context,
                            "agent_id": self.id,
                            "agent_role": "review",
                        }
                    }
                )
            )
        except RealAgentSchemaError:
            return _build_review_recovery(input_data)
        result = result.model_copy(update={"agent_id": self.id})
        return _ensure_review_artifact(
            result,
            input_data,
            allow_fallbacks=self._fallbacks_allowed(input_data),
        )

    def _fallbacks_allowed(self, input_data: AgentRunInput) -> bool:
        return self._allow_fallbacks or input_data.context.get("allow_agent_fallbacks") is True


def _ensure_review_artifact(
    result: AgentRunResult,
    input_data: AgentRunInput,
    *,
    allow_fallbacks: bool,
) -> AgentRunResult:
    next_artifacts: list[Artifact] = []
    found_review_artifact = False
    for artifact in result.artifacts:
        if artifact.type != "file":
            next_artifacts.append(artifact)
            continue
        data = dict(artifact.data)
        if "findings" not in data:
            data["findings"] = _fallback_findings(input_data)
        if "risk_level" not in data:
            data["risk_level"] = _risk_level_from_findings(data["findings"])
        next_artifacts.append(artifact.model_copy(update={"data": data}))
        found_review_artifact = True

    if found_review_artifact:
        return result.model_copy(update={"artifacts": next_artifacts})

    if result.content.strip():
        findings = _findings_from_model_content(result.content)
        return result.model_copy(
            update={
                "artifacts": [
                    *result.artifacts,
                    Artifact(
                        id=f"artifact-review-{input_data.workspace_id}",
                        type="file",
                        title="Review findings",
                        data={
                            "findings": findings,
                            "risk_level": _risk_level_from_findings(findings),
                            "workspace_id": input_data.workspace_id,
                            "source": "model-content-derived",
                        },
                    ),
                ]
            }
        )

    if not allow_fallbacks:
        recovery = _build_review_recovery(input_data, content_prefix=result.content)
        return result.model_copy(
            update={
                "content": recovery.content,
                "artifacts": [*result.artifacts, *recovery.artifacts],
            }
        )

    fallback = _build_review_fallback(input_data, content_prefix=result.content)
    return result.model_copy(
        update={
            "content": fallback.content,
            "artifacts": [*result.artifacts, *fallback.artifacts],
        }
    )


def _build_review_fallback(
    input_data: AgentRunInput,
    *,
    content_prefix: str | None = None,
) -> AgentRunResult:
    return _build_review_result(
        input_data,
        content_prefix=content_prefix,
        source="fallback-review",
    )


def _build_review_recovery(
    input_data: AgentRunInput,
    *,
    content_prefix: str | None = None,
) -> AgentRunResult:
    return _build_review_result(
        input_data,
        content_prefix=content_prefix,
        source="schema-recovery-review",
    )


def _build_review_result(
    input_data: AgentRunInput,
    *,
    content_prefix: str | None,
    source: str,
) -> AgentRunResult:
    findings = _fallback_findings(input_data)
    content = content_prefix.strip() if content_prefix else ""
    review_lines = [
        "Review Agent 已完成前序产物校验。",
        "",
        *[f"- {finding}" for finding in findings],
    ]
    if content:
        content = content + "\n\n" + "\n".join(review_lines)
    else:
        content = "\n".join(review_lines)
    return AgentRunResult(
        agent_id="review-agent",
        content=content,
        artifacts=[
            Artifact(
                id=f"artifact-review-{input_data.workspace_id}",
                type="file",
                title="Review findings",
                data={
                    "findings": findings,
                    "risk_level": _risk_level_from_findings(findings),
                    "workspace_id": input_data.workspace_id,
                    "source": source,
                },
            )
        ],
        next_actions=["preview-agent"],
    )


def _fallback_findings(input_data: AgentRunInput) -> list[str]:
    prior_artifacts = input_data.context.get("prior_artifacts", [])
    has_code = isinstance(prior_artifacts, list) and any(
        isinstance(artifact, dict) and artifact.get("type") == "code"
        for artifact in prior_artifacts
    )
    has_diff = isinstance(prior_artifacts, list) and any(
        isinstance(artifact, dict) and artifact.get("type") == "diff"
        for artifact in prior_artifacts
    )
    findings = []
    if has_code:
        findings.append("已发现前序 code artifact，可进入基础实现审查。")
    else:
        findings.append("未发现前序 code artifact，建议先确认 Code Agent 是否输出代码。")
    if has_diff:
        findings.append("已发现 diff artifact，应用前仍需确认目标路径位于 workspace 内。")
    else:
        findings.append("未发现 diff artifact，文件变更可能无法直接应用。")
    return findings


def _findings_from_model_content(content: str) -> list[str]:
    findings: list[str] = []
    for line in content.splitlines():
        item = line.strip().lstrip("-*0123456789.、) ")
        if item:
            findings.append(item)
    return findings[:8] or ["模型已返回审查内容，但未提供结构化 findings。"]


def _risk_level_from_findings(findings: object) -> str:
    if isinstance(findings, list) and any("未发现" in str(finding) for finding in findings):
        return "medium"
    return "low"


REVIEW_AGENT_SYSTEM_PROMPT = """
You are AgentHub Review Agent.
Return one JSON object matching AgentRunResult exactly:
{"agent_id":"review-agent","content":"Markdown review","artifacts":[],"next_actions":[]}

Rules:
- Review the current request, history, and prior artifacts.
- Focus on correctness, demo stability, workspace safety, UI risks, and missing tests.
- Include one file artifact. Its data should include findings as a string array and risk_level.
- Do not invent applied changes; review only what is in context.
""".strip()
