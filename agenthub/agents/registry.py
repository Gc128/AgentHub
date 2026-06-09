import json
import re

from agenthub.agents.base import AgentAdapter
from agenthub.agents.code_agent import CODE_AGENT_SYSTEM_PROMPT, CodeAgent
from agenthub.agents.mock_agent import MockAgent
from agenthub.agents.preview_agent import PREVIEW_AGENT_SYSTEM_PROMPT, PreviewAgent
from agenthub.agents.real_agent import RealAgent, RealAgentSchemaError
from agenthub.agents.review_agent import REVIEW_AGENT_SYSTEM_PROMPT, ReviewAgent
from agenthub.config import Settings
from agenthub.core.errors import NotFoundError
from agenthub.orchestrator.planner import (
    AGENT_CODE,
    AGENT_PREVIEW,
    AGENT_REVIEW,
    AgentTask,
    OrchestratorDecision,
    OrchestratorPlan,
    create_plan,
)
from agenthub.schemas.agent import AgentRunInput, AgentRunResult


class AgentRegistry:
    def __init__(self, adapters: list[AgentAdapter]) -> None:
        self._adapters = {adapter.id: adapter for adapter in adapters}

    def get(self, agent_id: str) -> AgentAdapter:
        adapter = self._adapters.get(agent_id)
        if adapter is None:
            raise NotFoundError("agent_not_found", f"Agent '{agent_id}' does not exist.")
        return adapter

    def list(self) -> list[AgentAdapter]:
        return list(self._adapters.values())


class OrchestratorAdapter:
    id = "orchestrator"
    name = "Orchestrator"
    capabilities = ["llm-planning", "routing", "summary"]

    def __init__(self, llm: RealAgent | None = None) -> None:
        self._llm = llm

    async def decide(self, input_data: AgentRunInput) -> OrchestratorDecision:
        if self._llm is None:
            plan = create_plan(input_data.user_message)
            if any(task.agent_id != self.id for task in plan.tasks):
                return OrchestratorDecision(
                    mode="plan",
                    content=_plan_content(plan),
                    plan=plan,
                )
            return OrchestratorDecision(
                mode="chat",
                content="你好，我是 AgentHub Orchestrator。请告诉我你想完成什么。",
            )
        llm_input = input_data.model_copy(
            update={
                "context": {
                    **input_data.context,
                    "agent_id": self.id,
                    "agent_role": "orchestrator",
                    "available_agents": [
                        "code-agent",
                        "review-agent",
                        "preview-agent",
                    ],
                }
            }
        )
        try:
            return await self._llm.run_structured(
                llm_input,
                OrchestratorDecision,
                schema_name="OrchestratorDecision",
            )
        except RealAgentSchemaError:
            recovered = await self._decide_with_relaxed_llm(llm_input)
            if recovered is not None:
                return recovered
            raise

    async def _decide_with_relaxed_llm(
        self,
        input_data: AgentRunInput,
    ) -> OrchestratorDecision | None:
        if self._llm is None:
            return None
        content = await self._llm.request_text(
            input_data.model_copy(
                update={
                    "user_message": _relaxed_orchestrator_prompt(input_data),
                    "context": {
                        **input_data.context,
                        "structured_output_recovery": True,
                    },
                }
            ),
            force_text=True,
        )
        return _decision_from_relaxed_orchestrator_text(content, input_data.user_message)

    async def run(self, input_data: AgentRunInput) -> AgentRunResult:
        decision = await self.decide(input_data)
        return AgentRunResult(
            agent_id=self.id,
            content=decision.content,
            artifacts=[],
            next_actions=decision.plan.agent_ids if decision.plan else [],
        )


def create_default_registry(settings: Settings | None = None) -> AgentRegistry:
    if settings is None or settings.use_mock_agents:
        return AgentRegistry(
            adapters=[
                MockAgent(),
                MockAgent(agent_id="orchestrator"),
                MockAgent(agent_id="code-agent"),
                MockAgent(agent_id="review-agent"),
                MockAgent(agent_id="preview-agent"),
            ]
        )

    return AgentRegistry(
        adapters=[
            OrchestratorAdapter(_real_agent("orchestrator", ORCHESTRATOR_SYSTEM_PROMPT, settings)),
            CodeAgent(
                _real_agent("code-agent", CODE_AGENT_SYSTEM_PROMPT, settings),
                workspace_root=settings.workspace_root,
                allow_fallbacks=settings.agent_allow_fallbacks,
            ),
            ReviewAgent(
                _real_agent("review-agent", REVIEW_AGENT_SYSTEM_PROMPT, settings),
                allow_fallbacks=settings.agent_allow_fallbacks,
            ),
            PreviewAgent(
                _real_agent("preview-agent", PREVIEW_AGENT_SYSTEM_PROMPT, settings),
                allow_fallbacks=settings.agent_allow_fallbacks,
            ),
        ]
    )


def _plan_content(plan: OrchestratorPlan) -> str:
    lines = [
        f"{index}. {task.agent_id}: {task.instruction}"
        for index, task in enumerate(plan.tasks, start=1)
        if task.agent_id != "orchestrator"
    ]
    return "## 任务拆解\n\n" + "\n".join(lines)


def _relaxed_orchestrator_prompt(input_data: AgentRunInput) -> str:
    user_request = input_data.context.get("user_request") or input_data.user_message
    return (
        "上一次结构化 JSON 决策无法被系统解析。请改用自然 Markdown 输出 AgentHub "
        "执行计划，不要输出 JSON。必须用独立行分别写出 code-agent、review-agent、"
        "preview-agent 的任务、依赖和预期产物；每个 instruction 要针对用户需求，"
        "不要复制整段原文。\n\n"
        f"用户需求：{user_request}"
    )


def _decision_from_relaxed_orchestrator_text(
    content: str,
    user_message: str,
) -> OrchestratorDecision | None:
    payload = _parse_json_object(content)
    if isinstance(payload, dict):
        try:
            return OrchestratorDecision.model_validate(payload)
        except Exception:
            pass

    tasks = _tasks_from_relaxed_orchestrator_text(content)
    if tasks:
        return OrchestratorDecision(
            mode="plan",
            content=content.strip(),
            plan=OrchestratorPlan(summary="LLM recovered orchestration plan", tasks=tasks),
        )

    if _looks_like_development_prompt(user_message):
        return None

    stripped = content.strip()
    if stripped.startswith(("{", "[")):
        return None
    if stripped:
        return OrchestratorDecision(mode="chat", content=stripped)
    return None


def _tasks_from_relaxed_orchestrator_text(content: str) -> list[AgentTask]:
    tasks: list[AgentTask] = []
    code_instruction = _extract_agent_instruction(content, AGENT_CODE)
    review_instruction = _extract_agent_instruction(content, AGENT_REVIEW)
    preview_instruction = _extract_agent_instruction(content, AGENT_PREVIEW)
    if code_instruction:
        tasks.append(
            AgentTask(
                task_id="task-code",
                agent_id=AGENT_CODE,
                instruction=code_instruction,
            )
        )
    if review_instruction:
        tasks.append(
            AgentTask(
                task_id="task-review",
                agent_id=AGENT_REVIEW,
                instruction=review_instruction,
                depends_on=["task-code"] if code_instruction else [],
            )
        )
    if preview_instruction:
        preview_dependencies: list[str] = []
        if review_instruction:
            preview_dependencies = ["task-review"]
        elif code_instruction:
            preview_dependencies = ["task-code"]
        tasks.append(
            AgentTask(
                task_id="task-preview",
                agent_id=AGENT_PREVIEW,
                instruction=preview_instruction,
                depends_on=preview_dependencies,
            )
        )
    return tasks


def _extract_agent_instruction(content: str, agent_id: str) -> str:
    alias = agent_id.replace("-", r"[-\s]?")
    pattern = re.compile(rf"(?i)(?:^|\n)\s*(?:[-*]|\d+[.)])?\s*.*\b{alias}\b.*")
    match = pattern.search(content)
    if match is None:
        return ""
    line = match.group(0).strip()
    line = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", line)
    line = re.sub(r"\s+", " ", line).strip()
    return line or f"{agent_id} 执行对应任务。"


def _parse_json_object(content: str) -> dict[str, object] | None:
    value = content.strip()
    if value.startswith("```"):
        lines = value.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        value = "\n".join(lines).strip()
    if not value.startswith("{"):
        return None
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _looks_like_development_prompt(user_message: str) -> bool:
    return any(task.agent_id != "orchestrator" for task in create_plan(user_message).tasks)


ORCHESTRATOR_SYSTEM_PROMPT = """
You are AgentHub Orchestrator.
Return only one JSON object matching OrchestratorDecision:
{"mode":"chat","content":"Markdown reply","plan":null}
or
{"mode":"plan","content":"Markdown task breakdown","plan":{"summary":"...","tasks":[]}}

Rules:
- Use mode=chat for greetings, casual conversation, or clarification.
- Use mode=plan for development work, bug fixing, UI implementation, review, or preview requests.
- Available child agents are exactly: code-agent, review-agent, preview-agent.
- Plan tasks must use stable task_id values when possible: task-code, task-review, task-preview.
- Do not copy the user's full request into each task instruction.
- Give each task a role-specific instruction, expected artifact, and dependency.
- Code tasks should explicitly tell Code Agent to implement the user's original requirements,
  including all requested fields, interactions, and data rules. Do not mention internal
  field names such as context.user_request in user-facing plan content.
- Code tasks should produce code and diff artifacts.
- Review tasks should inspect prior code/diff and produce findings plus risk_level.
- Preview tasks should verify preview_url/status and never claim a diff was applied.
- If a plan includes code-agent, include review-agent and preview-agent unless the user
  explicitly asks for only one agent.
""".strip()


def _real_agent(agent_id: str, system_prompt: str, settings: Settings) -> RealAgent:
    return RealAgent(
        agent_id=agent_id,
        provider=settings.agent_provider,
        model=settings.agent_model,
        api_key=settings.openai_api_key,
        base_url=settings.agent_base_url,
        timeout_seconds=settings.agent_request_timeout_seconds,
        response_format=settings.agent_response_format,
        thinking=settings.agent_thinking,
        max_tokens=settings.agent_max_tokens,
        system_prompt=system_prompt,
    )
