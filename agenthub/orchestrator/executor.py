"""
agenthub/orchestrator/executor.py

Orchestrator 任务执行引擎。

核心职责：
  execute_plan()：
    - 接受一个 OrchestratorPlan，依序遍历其 AgentTask 列表。
    - 为每个任务构造 AgentRunInput，调用注入的 AgentAdapter.run()。
    - 汇总所有子 Agent 返回的 Artifact 并返回。
    - 单任务失败时：记录错误，默认继续执行后续任务（fail_fast=False）。

不做的事：
  - 不实现具体的 AgentAdapter（由成员 B 负责）。
  - 不直接访问数据库。
  - 不集成 FastAPI 路由。

并发说明：
  当前实现为串行顺序执行（Serial）。
  顺序选择依据：MVP 阶段 depends_on 语义需要前置任务的产物可供后置任务使用，
  串行最简单且最容易调试。并行调度留给后续迭代（见模块末尾注释）。
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from agenthub.agents.base import (
    AgentAdapter,
    AgentRunInput,
    AgentRunResult,
    Artifact,
    Message,
)
from agenthub.agents.registry import AgentRegistry
from agenthub.orchestrator.planner import AgentTask, OrchestratorPlan, create_plan

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 执行结果数据结构
# ---------------------------------------------------------------------------


@dataclass
class TaskOutcome:
    """单个任务的执行结果，供调用方审计和调试使用。"""

    task_id: str
    agent_id: str
    success: bool
    result: AgentRunResult | None = None
    error: str = ""
    artifacts: list[Artifact] = field(default_factory=list)


@dataclass
class ExecutionReport:
    """execute_plan() 的完整执行报告。"""

    plan_summary: str
    outcomes: list[TaskOutcome] = field(default_factory=list)
    # 汇总所有成功任务的 Artifact（即 execute_plan 的主要返回值）
    artifacts: list[Artifact] = field(default_factory=list)

    @property
    def failed_tasks(self) -> list[TaskOutcome]:
        return [o for o in self.outcomes if not o.success]

    @property
    def succeeded_tasks(self) -> list[TaskOutcome]:
        return [o for o in self.outcomes if o.success]


class OrchestratorExecutor:
    """面向 AgentService 的 Orchestrator 执行器。

    它使用 `create_plan()` 拆解用户消息，再通过 AgentRegistry 依次调用子 Agent。
    现阶段仍保持串行执行，方便 Demo 链路稳定展示完整 artifact。
    """

    def __init__(self, registry: AgentRegistry) -> None:
        self._registry = registry

    async def run(self, input_data: AgentRunInput) -> AgentRunResult:
        plan = create_plan(input_data.user_message)
        child_results: list[AgentRunResult] = []

        for task in plan.tasks:
            agent = self._registry.get(task.agent_id)
            child_input = input_data.model_copy(
                update={
                    "context": {
                        **input_data.context,
                        "agent_id": task.agent_id,
                        "task_id": task.task_id,
                        "instruction": task.instruction,
                    }
                }
            )
            child_results.append(await agent.run(child_input))

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
            next_actions=plan.agent_ids,
        )


# ---------------------------------------------------------------------------
# 核心执行函数
# ---------------------------------------------------------------------------


async def execute_plan(
    plan: OrchestratorPlan,
    conversation_id: str,
    workspace_id: str,
    agent_service: AgentAdapter,
    *,
    history: list[Message] | None = None,
    context: dict[str, Any] | None = None,
    fail_fast: bool = False,
    task_timeout: float = 60.0,
) -> list[Artifact]:
    """遍历计划中的所有子任务，依次调用 Agent，汇总返回 Artifact 列表。

    Args:
        plan:             由 Orchestrator 构建的执行计划。
        conversation_id:  当前会话 ID，透传给 AgentRunInput。
        workspace_id:     工作区 ID，透传给 AgentRunInput。
        agent_service:    满足 AgentAdapter Protocol 的 Agent 实现（依赖注入）。
        history:          会话历史消息，可选；默认为空列表。
        context:          额外上下文键值对，可选；默认为空字典。
        fail_fast:        True = 第一个任务失败即中断并抛出异常；
                          False（默认）= 记录错误后继续执行后续任务。
        task_timeout:     单个任务的超时秒数，默认 60 秒。

    Returns:
        所有成功任务产出的 Artifact 列表（按任务顺序排列）。

    Raises:
        ExecutionError:   fail_fast=True 且某任务失败时抛出。
        ValueError:       plan.tasks 为空（由 OrchestratorPlan 校验保证，此处防御）。

    Implementation notes:
        - 当前为串行执行：任务 N 完成后才开始任务 N+1。
        - 前置任务的产物通过 context["prior_artifacts"] 传递给后续任务，
          使后置任务能感知前置产物（不做复杂 depends_on 调度，MVP 够用）。
        - 每次 Agent 调用都设置 asyncio.timeout，避免挂起整个引擎。
    """
    if not plan.tasks:
        return []

    report = ExecutionReport(plan_summary=plan.summary)
    all_artifacts: list[Artifact] = []
    hist = list(history or [])
    ctx = dict(context or {})

    logger.info(
        "execute_plan started | conversation=%s workspace=%s tasks=%d summary=%r",
        conversation_id,
        workspace_id,
        len(plan.tasks),
        plan.summary,
    )

    for task in plan.tasks:
        outcome = await _execute_task(
            task=task,
            conversation_id=conversation_id,
            workspace_id=workspace_id,
            agent_service=agent_service,
            history=hist,
            context={**ctx, "prior_artifacts": [a.model_dump() for a in all_artifacts]},
            task_timeout=task_timeout,
        )
        report.outcomes.append(outcome)

        if outcome.success and outcome.result is not None:
            # 汇总产物
            all_artifacts.extend(outcome.artifacts)
            report.artifacts.extend(outcome.artifacts)

            # 将 Agent 回复追加到历史，供后续任务感知上下文
            hist.append(
                Message(
                    id=str(uuid.uuid4()),
                    conversation_id=conversation_id,
                    role="agent",
                    sender_id=task.agent_id,
                    content=outcome.result.content,
                    artifacts=outcome.artifacts,
                )
            )
            logger.info(
                "Task %r succeeded | agent=%s artifacts=%d",
                task.task_id,
                task.agent_id,
                len(outcome.artifacts),
            )
        else:
            logger.warning(
                "Task %r failed | agent=%s error=%s",
                task.task_id,
                task.agent_id,
                outcome.error,
            )
            if fail_fast:
                raise ExecutionError(
                    f"Task {task.task_id!r} (agent={task.agent_id!r}) failed: {outcome.error}",
                    report=report,
                )

    logger.info(
        "execute_plan finished | succeeded=%d failed=%d total_artifacts=%d",
        len(report.succeeded_tasks),
        len(report.failed_tasks),
        len(all_artifacts),
    )
    return all_artifacts


# ---------------------------------------------------------------------------
# 单任务执行（内部辅助）
# ---------------------------------------------------------------------------


async def _execute_task(
    task: AgentTask,
    conversation_id: str,
    workspace_id: str,
    agent_service: AgentAdapter,
    history: list[Message],
    context: dict[str, Any],
    task_timeout: float,
) -> TaskOutcome:
    """执行单个 AgentTask，返回 TaskOutcome（永不抛出，错误记录在 outcome.error）。

    所有异常（超时、Agent 内部错误、网络错误）都被捕获并记录，
    让调用方（execute_plan）根据 fail_fast 策略决定如何处理。
    """
    run_input = AgentRunInput(
        conversation_id=conversation_id,
        workspace_id=workspace_id,
        user_message=task.instruction,
        history=history,
        context=context,
    )

    logger.debug(
        "Executing task %r | agent=%s instruction=%r",
        task.task_id,
        task.agent_id,
        task.instruction[:80],
    )

    try:
        async with asyncio.timeout(task_timeout):
            result: AgentRunResult = await agent_service.run(run_input)
    except TimeoutError:
        error_msg = f"Task timed out after {task_timeout}s"
        logger.error("Task %r timeout | agent=%s", task.task_id, task.agent_id)
        return TaskOutcome(
            task_id=task.task_id,
            agent_id=task.agent_id,
            success=False,
            error=error_msg,
        )
    except Exception as exc:  # noqa: BLE001
        error_msg = f"{type(exc).__name__}: {exc}"
        logger.exception("Task %r raised exception | agent=%s", task.task_id, task.agent_id)
        return TaskOutcome(
            task_id=task.task_id,
            agent_id=task.agent_id,
            success=False,
            error=error_msg,
        )

    return TaskOutcome(
        task_id=task.task_id,
        agent_id=task.agent_id,
        success=True,
        result=result,
        artifacts=list(result.artifacts),
    )


# ---------------------------------------------------------------------------
# ExecutionError（fail_fast 模式下抛出）
# ---------------------------------------------------------------------------


class ExecutionError(RuntimeError):
    """execute_plan 在 fail_fast=True 且任务失败时抛出。

    附带完整的 ExecutionReport 便于调用方审计已完成的任务。
    """

    def __init__(self, message: str, *, report: ExecutionReport) -> None:
        super().__init__(message)
        self.report = report


async def execute_agent(agent_id: str, input_data: AgentRunInput) -> AgentRunResult:
    """使用默认 AgentRegistry 执行单个 Agent。

    这是一个轻量便捷入口，供后续 API 或脚本在没有显式注入 service 时调用。
    """
    from agenthub.agents.registry import create_default_registry

    registry = create_default_registry()
    return await registry.get(agent_id).run(input_data)


# ---------------------------------------------------------------------------
# 并行调度（留存注释，供后续迭代参考）
# ---------------------------------------------------------------------------
# 当 depends_on 语义成熟后，可将串行执行改为基于拓扑排序的并行调度：
#
#   1. 构建 DAG：{task_id: set(depends_on)}
#   2. 用 Kahn 算法找出每一"层"（入度为 0 的节点）
#   3. 同层任务用 asyncio.gather() 并发执行
#   4. 每层结束后更新入度，进入下一层
#
# 参考实现骨架：
#   async def execute_plan_parallel(plan, ...) -> list[Artifact]:
#       layers = topological_sort(plan.tasks)
#       for layer in layers:
#           results = await asyncio.gather(
#               *[_execute_task(t, ...) for t in layer],
#               return_exceptions=True,
#           )
#           ...
