"""
agenthub/orchestrator/planner.py

Orchestrator 核心数据模型与基础路由规则。

职责：
- AgentTask：单个子任务的结构化描述（Pydantic v2）
- OrchestratorPlan：完整任务计划（Pydantic v2）
- route_task：基于关键词规则，将用户消息路由到对应 agent_id

本模块不调用任何 LLM API，不执行异步任务，不集成 FastAPI。
"""

from __future__ import annotations

import re
import uuid
from typing import Annotated

from pydantic import BaseModel, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Agent ID 常量
# ---------------------------------------------------------------------------

AGENT_CODE = "code-agent"
AGENT_REVIEW = "review-agent"
AGENT_PREVIEW = "preview-agent"
AGENT_ORCHESTRATOR = "orchestrator"

# 所有合法的 agent_id（未来扩展在此维护）
KNOWN_AGENT_IDS: frozenset[str] = frozenset(
    {AGENT_CODE, AGENT_REVIEW, AGENT_PREVIEW, AGENT_ORCHESTRATOR}
)


# ---------------------------------------------------------------------------
# Pydantic 模型
# ---------------------------------------------------------------------------


class AgentTask(BaseModel):
    """单个子任务的结构化描述。

    Attributes:
        task_id:     任务唯一标识符（默认自动生成 UUID4）。
        agent_id:    执行本任务的 agent 名称，必须是 KNOWN_AGENT_IDS 之一。
        instruction: 发送给 agent 的具体指令，不可为空白字符串。
        depends_on:  本任务依赖的其他任务 task_id 列表（默认为空）。
                     依赖任务必须在同一 Plan 内存在（由 OrchestratorPlan 校验）。
    """

    task_id: Annotated[str, Field(default_factory=lambda: str(uuid.uuid4()))]
    agent_id: str
    instruction: Annotated[str, Field(min_length=1)]
    depends_on: list[str] = Field(default_factory=list)

    @field_validator("agent_id")
    @classmethod
    def validate_agent_id(cls, v: str) -> str:
        v = v.strip()
        if v not in KNOWN_AGENT_IDS:
            raise ValueError(
                f"agent_id {v!r} is not recognised. Valid values: {sorted(KNOWN_AGENT_IDS)}"
            )
        return v

    @field_validator("instruction")
    @classmethod
    def validate_instruction_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("instruction must not be blank")
        return v

    model_config = {"frozen": True}  # 任务创建后不应被修改


class OrchestratorPlan(BaseModel):
    """一次 Orchestrator 拆解产生的完整任务计划。

    Attributes:
        summary:  面向用户的计划摘要说明（可为空字符串）。
        tasks:    有序的子任务列表；列表不可为空。
    """

    summary: str = ""
    tasks: Annotated[list[AgentTask], Field(min_length=1)]

    @model_validator(mode="after")
    def validate_dependency_references(self) -> OrchestratorPlan:
        """校验所有 depends_on 引用的 task_id 都在本 Plan 内存在。"""
        known_ids = {t.task_id for t in self.tasks}
        for task in self.tasks:
            for dep in task.depends_on:
                if dep not in known_ids:
                    raise ValueError(
                        f"Task {task.task_id!r} depends on unknown task_id {dep!r}. "
                        f"Known IDs in this plan: {sorted(known_ids)}"
                    )
        return self

    @property
    def agent_ids(self) -> list[str]:
        """返回本 Plan 涉及的所有 agent_id（保持出现顺序，去重）。"""
        seen: set[str] = set()
        result: list[str] = []
        for task in self.tasks:
            if task.agent_id not in seen:
                seen.add(task.agent_id)
                result.append(task.agent_id)
        return result


# ---------------------------------------------------------------------------
# 路由规则
# ---------------------------------------------------------------------------

# 每条规则：(agent_id, 关键词正则)
# 规则按列表顺序优先匹配，第一条命中即返回。
#
# 顺序选择依据：
#   preview 词（预览/效果/render）比 review/code 词更明确，放最前；
#   review 词（检查/bug/fix）放中间；
#   code 词（写/实现/生成/页面/组件）兜底。
#   "页面" 等词在 preview 场景下通常伴随 "预览"，preview 先命中。
#
# 正则注意：
#   - `\bcode\b` 防止 "code" 出现在 "decode/encode" 中误触
#   - `preview` 必须整词匹配以防止被 `review` 正则的 `view` 子串误吸收
#   - 对中文关键词无需 \b（中文无单词边界），直接匹配子串即可
_ROUTING_RULES: list[tuple[str, re.Pattern[str]]] = [
    (
        AGENT_PREVIEW,
        re.compile(
            r"预览|效果|展示|显示|preview|display|render|\bview\b|visualize",
            re.IGNORECASE | re.UNICODE,
        ),
    ),
    (
        AGENT_REVIEW,
        re.compile(
            r"检查|优化|bug|错误|问题|改进|修复|分析|审查|\breview\b|check|fix|optimize|improve|analyze|inspect|debug",
            re.IGNORECASE | re.UNICODE,
        ),
    ),
    (
        AGENT_CODE,
        re.compile(
            r"写|实现|生成|创建|开发|构建|编写|制作|页面|组件|功能|代码|function|implement|create|build|generate|write|develop|\bcode\b",
            re.IGNORECASE | re.UNICODE,
        ),
    ),
]


def route_task(user_message: str) -> str:
    """根据用户消息内容，通过关键词规则返回目标 agent_id。

    匹配顺序：code → review → preview → orchestrator（默认）。
    若用户消息同时命中多条规则（如"写代码并 review"），以最先匹配的规则为准。

    Args:
        user_message: 用户发送的原始消息字符串。

    Returns:
        应被调用的 agent_id 字符串，保证是 KNOWN_AGENT_IDS 的成员。

    Examples:
        >>> route_task("帮我写一个登录页面")
        'code-agent'
        >>> route_task("review 一下这段代码有没有 bug")
        'review-agent'
        >>> route_task("预览一下当前效果")
        'preview-agent'
        >>> route_task("你好")
        'orchestrator'
    """
    if not user_message or not user_message.strip():
        return AGENT_ORCHESTRATOR

    for agent_id, pattern in _ROUTING_RULES:
        if pattern.search(user_message):
            return agent_id

    return AGENT_ORCHESTRATOR


def _matches_agent(user_message: str, target_agent_id: str) -> bool:
    return any(
        agent_id == target_agent_id and pattern.search(user_message)
        for agent_id, pattern in _ROUTING_RULES
    )


def create_plan(user_message: str) -> OrchestratorPlan:
    """基于用户消息创建 MVP 任务计划。

    这是给 FastAPI AgentService / OrchestratorExecutor 使用的结构化拆解入口；
    `route_task()` 仍保留为单 Agent 路由能力。用户显式 @Orchestrator 时，
    默认走完整 Code -> Review -> Preview 演示链路。
    """
    message = user_message.strip()
    lowered = message.lower()
    tasks: list[AgentTask] = []

    wants_code = _matches_agent(message, AGENT_CODE)
    wants_review = _matches_agent(message, AGENT_REVIEW)
    wants_preview = _matches_agent(message, AGENT_PREVIEW)

    if "@orchestrator" in lowered:
        wants_code = True
        wants_review = True
        wants_preview = True

    if wants_code:
        tasks.append(
            AgentTask(
                task_id="task-code",
                agent_id=AGENT_CODE,
                instruction=message,
            )
        )
    if wants_review:
        tasks.append(
            AgentTask(
                task_id="task-review",
                agent_id=AGENT_REVIEW,
                instruction=message,
                depends_on=["task-code"] if wants_code else [],
            )
        )
    if wants_preview:
        depends_on = ["task-review"] if wants_review else ["task-code"] if wants_code else []
        tasks.append(
            AgentTask(
                task_id="task-preview",
                agent_id=AGENT_PREVIEW,
                instruction=message,
                depends_on=depends_on,
            )
        )

    if not tasks:
        tasks.append(
            AgentTask(
                task_id="task-default",
                agent_id=AGENT_ORCHESTRATOR,
                instruction=message or "继续协作",
            )
        )

    return OrchestratorPlan(summary="Rule-based MVP plan", tasks=tasks)
