from pydantic import BaseModel, Field


class AgentTask(BaseModel):
    task_id: str
    agent_id: str
    instruction: str
    depends_on: list[str] = Field(default_factory=list)


class OrchestratorPlan(BaseModel):
    summary: str
    tasks: list[AgentTask] = Field(default_factory=list)


def create_plan(user_message: str) -> OrchestratorPlan:
    lowered = user_message.lower()
    tasks: list[AgentTask] = []

    if any(keyword in user_message for keyword in ["写", "实现", "生成", "页面", "组件"]):
        tasks.append(AgentTask(task_id="task-code", agent_id="code-agent", instruction=user_message))
    if any(keyword in lowered for keyword in ["review", "bug"]) or any(
        keyword in user_message for keyword in ["检查", "优化", "问题"]
    ):
        tasks.append(AgentTask(task_id="task-review", agent_id="review-agent", instruction=user_message))
    if any(keyword in user_message for keyword in ["预览", "效果", "页面展示"]):
        tasks.append(AgentTask(task_id="task-preview", agent_id="preview-agent", instruction=user_message))

    if not tasks:
        tasks.append(AgentTask(task_id="task-default", agent_id="orchestrator", instruction=user_message))

    return OrchestratorPlan(summary="Rule-based MVP plan", tasks=tasks)
