from agenthub.agents.base import AgentAdapter
from agenthub.agents.code_agent import CODE_AGENT_SYSTEM_PROMPT, CodeAgent
from agenthub.agents.mock_agent import MockAgent
from agenthub.agents.preview_agent import PREVIEW_AGENT_SYSTEM_PROMPT, PreviewAgent
from agenthub.agents.real_agent import RealAgent
from agenthub.agents.review_agent import REVIEW_AGENT_SYSTEM_PROMPT, ReviewAgent
from agenthub.config import Settings
from agenthub.core.errors import NotFoundError
from agenthub.orchestrator.planner import create_plan
from agenthub.schemas.agent import AgentRunInput, AgentRunResult
from agenthub.schemas.artifact import Artifact


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
    capabilities = ["task-planning", "routing", "summary"]

    async def run(self, input_data: AgentRunInput) -> AgentRunResult:
        plan = create_plan(input_data.user_message)
        return AgentRunResult(
            agent_id=self.id,
            content="## 任务拆解\n\n"
            + "\n".join(
                f"{index}. {task.agent_id}: {task.instruction}"
                for index, task in enumerate(plan.tasks, start=1)
            ),
            artifacts=[
                Artifact(
                    id="artifact-orchestrator-plan",
                    type="file",
                    title="Orchestrator task plan",
                    data={**plan.model_dump(mode="json"), "agent_ids": plan.agent_ids},
                )
            ],
            next_actions=plan.agent_ids,
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
            OrchestratorAdapter(),
            CodeAgent(
                _real_agent("code-agent", CODE_AGENT_SYSTEM_PROMPT, settings),
                workspace_root=settings.workspace_root,
            ),
            ReviewAgent(_real_agent("review-agent", REVIEW_AGENT_SYSTEM_PROMPT, settings)),
            PreviewAgent(_real_agent("preview-agent", PREVIEW_AGENT_SYSTEM_PROMPT, settings)),
        ]
    )


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
