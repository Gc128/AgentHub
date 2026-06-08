from agenthub.agents.base import AgentAdapter
from agenthub.agents.code_agent import CODE_AGENT_SYSTEM_PROMPT, CodeAgent
from agenthub.agents.mock_agent import MockAgent
from agenthub.agents.preview_agent import PREVIEW_AGENT_SYSTEM_PROMPT, PreviewAgent
from agenthub.agents.real_agent import RealAgent
from agenthub.agents.review_agent import REVIEW_AGENT_SYSTEM_PROMPT, ReviewAgent
from agenthub.config import Settings
from agenthub.core.errors import NotFoundError
from agenthub.orchestrator.planner import OrchestratorDecision, OrchestratorPlan, create_plan
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
        return await self._llm.run_structured(
            input_data.model_copy(
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
            ),
            OrchestratorDecision,
            schema_name="OrchestratorDecision",
        )

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
- Code tasks should explicitly tell Code Agent to implement the original user requirements
  from context.user_request, including all requested fields, interactions, and data rules.
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
