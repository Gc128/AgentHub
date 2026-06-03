from agenthub.agents.registry import AgentRegistry
from agenthub.orchestrator.planner import create_plan
from agenthub.schemas.agent import AgentRunInput, AgentRunResult
from agenthub.schemas.artifact import Artifact


class OrchestratorExecutor:
    def __init__(self, registry: AgentRegistry) -> None:
        self._registry = registry

    async def run(self, input_data: AgentRunInput) -> AgentRunResult:
        plan = create_plan(input_data.user_message)
        child_results: list[AgentRunResult] = []
        for task in plan.tasks:
            agent = self._registry.get(task.agent_id)
            result = await agent.run(
                input_data.model_copy(
                    update={
                        "context": {
                            **input_data.context,
                            "agent_id": task.agent_id,
                            "task_id": task.task_id,
                            "instruction": task.instruction,
                        }
                    }
                )
            )
            child_results.append(result)

        artifacts = [
            Artifact(
                id="artifact-orchestrator-plan",
                type="file",
                title="Orchestrator task plan",
                data=plan.model_dump(mode="json"),
            )
        ]
        for result in child_results:
            artifacts.extend(result.artifacts)

        summary_lines = [f"- {task.agent_id}: {task.instruction}" for task in plan.tasks]
        return AgentRunResult(
            agent_id="orchestrator",
            content="Orchestrator completed the plan:\n" + "\n".join(summary_lines),
            artifacts=artifacts,
            next_actions=["apply-diff", "preview"],
        )


async def execute_agent(agent_id: str, input_data: AgentRunInput) -> AgentRunResult:
    from agenthub.agents.registry import create_default_registry

    registry = create_default_registry()
    return await registry.get(agent_id).run(input_data)
