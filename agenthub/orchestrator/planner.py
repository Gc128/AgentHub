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
from typing import Annotated, Literal

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

_AGENT_ALIASES: dict[str, str] = {
    "code": AGENT_CODE,
    "code agent": AGENT_CODE,
    "code-agent": AGENT_CODE,
    "code_agent": AGENT_CODE,
    "codeagent": AGENT_CODE,
    "review": AGENT_REVIEW,
    "review agent": AGENT_REVIEW,
    "review-agent": AGENT_REVIEW,
    "review_agent": AGENT_REVIEW,
    "reviewagent": AGENT_REVIEW,
    "preview": AGENT_PREVIEW,
    "preview agent": AGENT_PREVIEW,
    "preview-agent": AGENT_PREVIEW,
    "preview_agent": AGENT_PREVIEW,
    "previewagent": AGENT_PREVIEW,
    "orchestrator": AGENT_ORCHESTRATOR,
    "orchestrator agent": AGENT_ORCHESTRATOR,
}


def _normalize_agent_id(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    key = value.strip().lower().replace("@", "").replace("_", " ")
    key = re.sub(r"\s+", " ", key)
    return _AGENT_ALIASES.get(key) or _AGENT_ALIASES.get(key.replace(" ", "-"))


def _default_task_id_for_agent(agent_id: str | None) -> str:
    if agent_id is None:
        return str(uuid.uuid4())
    return {
        AGENT_CODE: "task-code",
        AGENT_REVIEW: "task-review",
        AGENT_PREVIEW: "task-preview",
        AGENT_ORCHESTRATOR: "task-orchestrator",
    }.get(agent_id, str(uuid.uuid4()))


def _normalize_task_id_alias(value: str) -> str:
    key = value.strip()
    normalized = key.lower().replace("_", "-").replace(" ", "-")
    return {
        "code": "task-code",
        "task-code": "task-code",
        "review": "task-review",
        "task-review": "task-review",
        "preview": "task-preview",
        "task-preview": "task-preview",
        "orchestrator": "task-orchestrator",
        "task-orchestrator": "task-orchestrator",
    }.get(normalized, key)


def _normalize_dependency_alias(value: object) -> str:
    if not isinstance(value, str):
        return ""
    stripped = value.strip()
    agent_id = _normalize_agent_id(stripped)
    if agent_id is not None:
        return agent_id
    return _normalize_task_id_alias(stripped).replace("_", "-")


def _is_empty_dependency(value: str) -> bool:
    return value.strip().lower() in {"", "none", "null", "n/a", "无", "无依赖"}


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

    @model_validator(mode="before")
    @classmethod
    def normalize_llm_task_shape(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data

        values = dict(data)
        agent_value = values.get("agent_id") or values.get("agent") or values.get("agent_name")
        agent_id = _normalize_agent_id(agent_value)
        if agent_id is not None:
            values["agent_id"] = agent_id

        task_id = values.get("task_id") or values.get("id")
        if isinstance(task_id, str) and task_id.strip():
            values["task_id"] = _normalize_task_id_alias(task_id)

        if "instruction" not in values:
            values["instruction"] = (
                values.get("description")
                or values.get("task")
                or values.get("objective")
                or values.get("title")
                or ""
            )

        depends_on = values.get("depends_on", [])
        if isinstance(depends_on, str):
            values["depends_on"] = [] if _is_empty_dependency(depends_on) else [depends_on]
        elif depends_on is None:
            values["depends_on"] = []
        return values

    @field_validator("agent_id")
    @classmethod
    def validate_agent_id(cls, v: str) -> str:
        normalized = _normalize_agent_id(v)
        if normalized is None or normalized not in KNOWN_AGENT_IDS:
            raise ValueError(
                f"agent_id {v!r} is not recognised. Valid values: {sorted(KNOWN_AGENT_IDS)}"
            )
        return normalized

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

    @model_validator(mode="before")
    @classmethod
    def normalize_llm_plan_dependencies(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        tasks = data.get("tasks")
        if not isinstance(tasks, list):
            return data

        normalized_tasks: list[object] = []
        dependency_aliases: dict[str, str] = {}
        for task in tasks:
            if not isinstance(task, dict):
                normalized_tasks.append(task)
                continue

            next_task = dict(task)
            agent_id = _normalize_agent_id(
                next_task.get("agent_id") or next_task.get("agent") or next_task.get("agent_name")
            )
            task_id_value = next_task.get("task_id") or next_task.get("id")
            task_id = (
                _normalize_task_id_alias(task_id_value)
                if isinstance(task_id_value, str) and task_id_value.strip()
                else _default_task_id_for_agent(agent_id)
            )
            next_task["task_id"] = task_id

            if agent_id is not None:
                dependency_aliases[agent_id] = task_id
                dependency_aliases[agent_id.removesuffix("-agent")] = task_id
            dependency_aliases[task_id] = task_id
            dependency_aliases[task_id.replace("-", "_")] = task_id
            normalized_tasks.append(next_task)

        coerced_tasks: list[object] = []
        for task in normalized_tasks:
            if not isinstance(task, dict):
                coerced_tasks.append(task)
                continue
            next_task = dict(task)
            raw_dependencies = next_task.get("depends_on", [])
            if isinstance(raw_dependencies, str):
                dependencies = [] if _is_empty_dependency(raw_dependencies) else [raw_dependencies]
            elif raw_dependencies is None:
                dependencies = []
            else:
                dependencies = list(raw_dependencies)
            next_task["depends_on"] = [
                dependency_aliases[normalized]
                for value in dependencies
                if (normalized := _normalize_dependency_alias(value)) in dependency_aliases
            ]
            coerced_tasks.append(next_task)

        return {**data, "tasks": coerced_tasks}

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


class OrchestratorDecision(BaseModel):
    """LLM Orchestrator 对一次用户输入的决策。

    mode=chat 表示直接回复用户；mode=plan 表示进入多 Agent harness。
    """

    mode: Literal["chat", "plan"]
    content: Annotated[str, Field(min_length=1)]
    plan: OrchestratorPlan | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_llm_decision_shape(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data

        values = dict(data)
        top_level_tasks = values.get("tasks")
        raw_plan = values.get("plan")
        if isinstance(raw_plan, dict):
            plan = dict(raw_plan)
            if not isinstance(plan.get("tasks"), list) and isinstance(top_level_tasks, list):
                plan["tasks"] = top_level_tasks
            plan.setdefault("summary", values.get("summary", ""))
            values["plan"] = plan
        elif isinstance(top_level_tasks, list):
            values["plan"] = {
                "summary": values.get("summary", ""),
                "tasks": top_level_tasks,
            }

        if values.get("mode") not in {"chat", "plan"}:
            values["mode"] = "plan" if isinstance(values.get("plan"), dict) else "chat"

        content = values.get("content")
        if not isinstance(content, str) or not content.strip():
            fallback_content = (
                values.get("reply")
                or values.get("message")
                or values.get("summary")
                or ("## 任务拆解" if values["mode"] == "plan" else "我已收到。")
            )
            values["content"] = str(fallback_content)

        return values

    @model_validator(mode="after")
    def validate_plan_mode_has_plan(self) -> OrchestratorDecision:
        if self.mode == "plan" and self.plan is None:
            raise ValueError("plan mode requires a plan")
        return self


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
            r"写|实现|生成|创建|开发|构建|编写|制作|页面|网页|组件|功能|代码|待办|清单|"
            r"todo|list|app|function|implement|create|build|generate|write|develop|\bcode\b",
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

    if "@orchestrator" in lowered or wants_code:
        wants_code = True
        wants_review = True
        wants_preview = True

    if wants_code:
        tasks.append(
            AgentTask(
                task_id="task-code",
                agent_id=AGENT_CODE,
                instruction=(
                    "实现用户提出的开发需求，保留所有明确要求的字段、交互和数据规则；"
                    "输出 Markdown 说明、code artifact，并为每个变更文件提供 diff artifact。"
                ),
            )
        )
    if wants_review:
        tasks.append(
            AgentTask(
                task_id="task-review",
                agent_id=AGENT_REVIEW,
                instruction=(
                    "审查前序代码与 diff 产物，检查正确性、路径安全、遗漏场景和可演示风险；"
                    "输出 findings、risk_level 和建议的修复方向。"
                ),
                depends_on=["task-code"] if wants_code else [],
            )
        )
    if wants_preview:
        depends_on = ["task-review"] if wants_review else ["task-code"] if wants_code else []
        tasks.append(
            AgentTask(
                task_id="task-preview",
                agent_id=AGENT_PREVIEW,
                instruction=(
                    "基于 workspace 状态和前序产物验证预览是否可用；"
                    "说明 preview_url/status、入口文件情况，以及用户应用 diff 后应如何查看效果。"
                ),
                depends_on=depends_on,
            )
        )

    if not tasks:
        tasks.append(
            AgentTask(
                task_id="task-default",
                agent_id=AGENT_ORCHESTRATOR,
                instruction="作为 AgentHub 助手直接回应用户；如果发现是开发需求，再创建执行计划。",
            )
        )

    return OrchestratorPlan(summary="AgentHub execution harness plan", tasks=tasks)
