"""AgentHub 前端联调用的 Flask 服务入口。

这个文件承担的是“本地真实后端”的职责：前端不再从 TS mock 中直接取数据，
而是通过 HTTP 请求访问这里的 API；API 再读写 `frontend/flask/data/*.json`。

注意：
- 这里用 JSON 文件模拟数据库表，方便比赛 Demo 和前后端联调。
- 每个接口都返回统一 envelope：`{ success, data, error }`。
- 业务字段尽量和前端 `src/types/api.ts`、仓库 schema、需求文档保持一致。
- 目前是 MVP 版本，所以把服务、仓储、规则 Agent 放在一个文件中；后续可拆到
  routes / repositories / services / agents 模块。
"""

from __future__ import annotations

import json
import random
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Literal
from uuid import uuid4

from flask import Flask, Response, jsonify, request

from agenthub.orchestrator.planner import (
    AGENT_CODE,
    AGENT_PREVIEW,
    AGENT_REVIEW,
    AgentTask,
    OrchestratorPlan,
)
from agenthub.workspace.diff import (
    DiffApplyError,
    create_unified_diff,
)
from agenthub.workspace.diff import (
    apply_diff as apply_workspace_diff,
)

# 当前 Flask 文件所在目录：`frontend/flask`。
# 使用相对本文件的位置计算路径，避免硬编码用户机器上的绝对路径。
BASE_DIR = Path(__file__).resolve().parent

# JSON “数据库”目录。首次启动时，如果某张表不存在，会由 `read_json` 写入默认数据。
DATA_DIR = BASE_DIR / "data"

# ConversationMode 对应前端 Conversation.mode：
# - single：单 Agent 会话
# - group：多 Agent 群聊协作会话
ConversationMode = Literal["single", "group"]

# PreviewStatus 对应前端 Preview 面板状态：
# - not_started：还没有启动预览
# - running：预览服务启动中
# - ready：预览已可用
# - error：预览失败
PreviewStatus = Literal["not_started", "running", "ready", "error"]


def now_iso() -> str:
    """生成统一的 UTC 时间字符串。

    返回示例：`2026-06-02T12:30:00.000000Z`。
    前端所有列表排序、消息时间展示、Artifact 时间展示都依赖这个字段。
    """

    # 统一使用 UTC ISO 字符串，方便前端直接格式化展示。
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def make_id(prefix: str) -> str:
    """按业务前缀生成唯一 ID。

    Args:
        prefix: ID 前缀，例如 `conv`、`msg`、`artifact_code`。

    Returns:
        形如 `conv_ab12cd34` 的字符串，便于前端根据前缀快速理解类型。
    """

    # 使用 uuid 生成唯一 ID，避免删除后再创建时和历史数据冲突。
    return f"{prefix}_{uuid4().hex[:8]}"


def preview_page_url(workspace_id: str) -> str:
    """生成本地 Flask iframe 预览地址。"""

    return f"http://127.0.0.1:5001/api/workspaces/{workspace_id}/preview-page"


def infer_mode(agent_ids: list[str]) -> ConversationMode:
    """根据会话成员数量推导会话模式。

    前端创建会话时只需要传 `agent_ids`，后端统一补出 mode，避免前端和后端
    对“单聊 / 群聊”的判断不一致。
    """

    # 会话模式由成员数量推导：一个 Agent 是单聊，多个 Agent 是群聊。
    return "group" if len(agent_ids) > 1 else "single"


def success(data: Any, status: int = 200) -> tuple[Response, int]:
    """构造统一成功响应。

    Args:
        data: 真实业务数据，例如会话数组、消息数组、AgentRunResult。
        status: HTTP 状态码，列表查询一般是 200，新增一般是 201。

    Returns:
        Flask 可直接返回的 `(Response, status_code)`。
    """

    # 所有成功接口统一包一层 JSON envelope，前端 requestJson 会自动取 data。
    return jsonify({"success": True, "data": data, "error": None}), status


def failure(message: str, status: int = 400) -> tuple[Response, int]:
    """构造统一失败响应。

    Args:
        message: 给前端展示的人类可读错误说明，不包含密钥或隐私信息。
        status: HTTP 状态码，例如 400 参数错误、403 权限错误、404 不存在。
    """

    # 所有失败接口返回明确错误信息，便于前端 Alert 展示。
    return jsonify({"success": False, "data": None, "error": message}), status


def read_json(path: Path, default: Any) -> Any:
    """读取一张 JSON 表。

    Args:
        path: 表文件路径，例如 `data/conversations.json`。
        default: 首次运行时写入的默认表数据。

    Returns:
        JSON 文件反序列化后的 Python 对象，通常是 `list[dict]`。
    """

    # 读表时如果文件缺失就创建默认数据，保证服务第一次运行可用。
    if not path.exists():
        write_json(path, default)
        return deepcopy(default)

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json(path: Path, data: Any) -> None:
    """写入一张 JSON 表。

    所有 JSON 持久化都从这里走，后续如果换成 SQLite，只需要把 `JsonTable`
    一层替换掉，路由函数不必到处改文件读写细节。
    """

    # 写表逻辑集中在这里，避免路由函数散落文件操作细节。
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


class JsonTable:
    """一个很轻量的 JSON 表封装，负责基础读写和按 id 查找。

    字段说明：
    - name: 表名，会映射为 `frontend/flask/data/{name}.json`。
    - default: 表文件缺失时写入的初始数据。

    这个类故意只实现 MVP 需要的 all / save / find，避免为了 Demo 引入复杂 ORM。
    """

    def __init__(self, name: str, default: list[dict[str, Any]]) -> None:
        # 每张表都独立存成一个 JSON 文件，结构接近数据库中的一张表。
        self.path = DATA_DIR / f"{name}.json"

        # default 只在文件不存在时使用；文件存在后，以磁盘数据为准。
        self.default = default

    def all(self) -> list[dict[str, Any]]:
        """读取整张表，返回所有记录。"""

        return read_json(self.path, self.default)

    def save(self, rows: list[dict[str, Any]]) -> None:
        """覆盖保存整张表。

        JSON 文件没有数据库事务能力，所以这里一次写入完整数组，保持结构简单。
        """

        write_json(self.path, rows)

    def find(self, item_id: str) -> dict[str, Any] | None:
        """按通用 `id` 字段查找单条记录。

        适用于 users / agents / conversations / messages 等以 id 为主键的表。
        preview 表的主键是 workspace_id，所以 preview 相关逻辑单独处理。
        """

        return next((row for row in self.all() if row.get("id") == item_id), None)


# Agent 表默认数据。
#
# 字段说明：
# - id: Agent 的稳定标识，前端 @ 菜单、会话成员、Agent 调用都用这个值。
# - name: 前端展示名。
# - role: Agent 角色，和前端类型中的 orchestrator/code/review/preview/custom 对齐。
# - description: Agent 能力简介，用于联系人卡片。
# - capabilities: 能力标签，用于前端 Badge 展示和后续调度规则扩展。
# - adapter_type: 真实 Agent 适配器类型；当前本地服务用 custom 代表 Flask 规则实现。
DEFAULT_AGENTS: list[dict[str, Any]] = [
    {
        "id": "orchestrator",
        "name": "Orchestrator",
        "role": "orchestrator",
        "description": "拆解开发需求，协调多个 Agent 完成任务。",
        "capabilities": ["task-planning", "routing", "summary"],
        "adapter_type": "custom",
    },
    {
        "id": "code-agent",
        "name": "Code Agent",
        "role": "code",
        "description": "生成页面代码、组件和文件变更。",
        "capabilities": ["code", "diff", "file-generation"],
        "adapter_type": "custom",
    },
    {
        "id": "review-agent",
        "name": "Review Agent",
        "role": "review",
        "description": "检查代码质量、风险和可维护性。",
        "capabilities": ["review", "quality", "risk"],
        "adapter_type": "custom",
    },
    {
        "id": "preview-agent",
        "name": "Preview Agent",
        "role": "preview",
        "description": "生成预览信息并反馈页面效果。",
        "capabilities": ["preview", "workspace-status"],
        "adapter_type": "custom",
    },
]

# Conversation 表默认数据。
#
# 字段说明：
# - id: 会话主键，前端切换会话、查询消息都依赖它。
# - title: 会话标题，显示在左侧会话列表和聊天头部。
# - mode: single/group，会由 agent_ids 数量推导，前端用于展示“单聊/群聊”。
# - agent_ids: 当前会话允许调用的 Agent id 列表，run_agent 会据此做校验。
# - is_pinned: 是否置顶，前端置顶按钮和排序逻辑依赖这个字段。
# - workspace_id: 会话绑定的工作区 id，用于预览、文件和 Apply Diff。
# - created_at: 会话创建时间。
# - updated_at: 最近更新时间，发送消息或修改会话时会刷新。
DEFAULT_CONVERSATIONS: list[dict[str, Any]] = [
    {
        "id": "conv_001",
        "title": "Todo App Development",
        "mode": "group",
        "agent_ids": ["orchestrator", "code-agent", "review-agent", "preview-agent"],
        "is_pinned": False,
        "workspace_id": "ws_001",
        "created_at": "2026-06-03T09:00:00Z",
        "updated_at": "2026-06-03T09:13:00Z",
    },
    {
        "id": "conv_002",
        "title": "Landing Page Review",
        "mode": "single",
        "agent_ids": ["review-agent"],
        "is_pinned": False,
        "workspace_id": "ws_002",
        "created_at": "2026-06-03T09:20:00Z",
        "updated_at": "2026-06-03T09:31:00Z",
    },
    {
        "id": "conv_003",
        "title": "Bug Fix Iteration",
        "mode": "group",
        "agent_ids": ["orchestrator", "code-agent", "review-agent", "preview-agent"],
        "is_pinned": True,
        "workspace_id": "ws_003",
        "created_at": "2026-06-03T09:40:00Z",
        "updated_at": "2026-06-03T09:55:00Z",
    },
    {
        "id": "conv_004",
        "title": "Workspace Preview Demo",
        "mode": "group",
        "agent_ids": ["code-agent", "review-agent", "preview-agent"],
        "is_pinned": False,
        "workspace_id": "ws_004",
        "created_at": "2026-06-03T10:00:00Z",
        "updated_at": "2026-06-03T10:12:00Z",
    },
]

TODO_APP_CODE = (
    "import { useState } from 'react'\n\n"
    "const initialTodos = ['梳理需求', '生成代码', '应用 Diff']\n\n"
    "export default function App() {\n"
    "  const [todos, setTodos] = useState(initialTodos)\n\n"
    "  return (\n"
    '    <main className="todo-shell">\n'
    '      <section className="todo-card">\n'
    '        <p className="eyebrow">AgentHub Demo</p>\n'
    "        <h1>Team Todo</h1>\n"
    "        <button onClick={() => setTodos([...todos, '预览并提交'])}>Add task</button>\n"
    "        <ul>{todos.map((todo) => <li key={todo}>{todo}</li>)}</ul>\n"
    "      </section>\n"
    "    </main>\n"
    "  )\n"
    "}\n"
)

TODO_APP_DIFF = (
    "--- a/src/App.tsx\n"
    "+++ b/src/App.tsx\n"
    "@@\n"
    "-export default function App() { return null }\n"
    "+import { useState } from 'react'\n"
    "+\n"
    "+const initialTodos = ['梳理需求', '生成代码', '应用 Diff']\n"
    "+\n"
    "+export default function App() {\n"
    "+  const [todos, setTodos] = useState(initialTodos)\n"
    '+  return <main className="todo-shell">Team Todo</main>\n'
    "+}\n"
)

BUG_FIX_CODE = (
    "const submitTask = (value: string) => {\n"
    "  const normalized = value.trim()\n"
    "  if (!normalized) {\n"
    "    setError('请输入任务内容')\n"
    "    return\n"
    "  }\n"
    "  setTodos((items) => [...items, normalized])\n"
    "  setDraft('')\n"
    "  setError(null)\n"
    "}\n"
)

BUG_FIX_DIFF = (
    "--- a/src/todo-actions.ts\n"
    "+++ b/src/todo-actions.ts\n"
    "@@\n"
    "-setTodos((items) => [...items, value])\n"
    "+const normalized = value.trim()\n"
    "+if (!normalized) {\n"
    "+  setError('请输入任务内容')\n"
    "+  return\n"
    "+}\n"
    "+setTodos((items) => [...items, normalized])\n"
)

# Message 表默认数据。
#
# 字段说明：
# - id: 消息主键。
# - conversation_id: 所属会话 id，用于按会话筛选消息。
# - role: user/agent/system，前端根据 role 决定气泡样式。
# - sender_id: 发送者 id；用户固定为 user，Agent 消息使用 Agent id。
# - content: 消息正文。
# - artifacts: 消息携带的结构化产物数组，前端按 type 渲染不同卡片。
# - created_at: 消息创建时间，聊天区按该字段升序展示。
DEFAULT_MESSAGES: list[dict[str, Any]] = [
    {
        "id": "msg_001",
        "conversation_id": "conv_001",
        "role": "user",
        "sender_id": "user",
        "content": (
            "@Orchestrator 帮我做一个适合比赛演示的 Todo List 页面，要能展示代码、Diff 和预览。"
        ),
        "artifacts": [],
        "created_at": "2026-06-03T09:01:00Z",
    },
    {
        "id": "msg_002",
        "conversation_id": "conv_001",
        "role": "agent",
        "sender_id": "orchestrator",
        "content": (
            "## 任务拆解\n\n"
            "我会按比赛 Demo 主线推进：\n\n"
            "1. **Code Agent** 生成 Todo 页面和可应用 Diff。\n"
            "2. **Review Agent** 检查交互、空状态和移动端风险。\n"
            "3. **Preview Agent** 刷新 workspace 预览，并把结果放到右侧面板。\n\n"
            "> 目标不是堆卡片，而是让聊天记录本身完整记录协作过程。"
        ),
        "artifacts": [
            {
                "id": "artifact_plan_001",
                "type": "file",
                "title": "Task Breakdown",
                "data": {
                    "summary": "Rule-based MVP plan",
                    "steps": ["生成 Todo 页面", "检查代码质量", "准备页面预览"],
                },
                "created_at": "2026-06-03T09:02:00Z",
            }
        ],
        "created_at": "2026-06-03T09:02:00Z",
    },
    {
        "id": "msg_003",
        "conversation_id": "conv_001",
        "role": "agent",
        "sender_id": "code-agent",
        "content": (
            "## Todo 页面实现\n\n"
            "我先给出一个轻量 React 版本，主交互集中在新增任务和列表展示。\n\n"
            "```tsx file=src/App.tsx\n"
            f"{TODO_APP_CODE}"
            "```\n\n"
            "这次变更会替换空壳 `App.tsx`，并保留后续接入真实 workspace 的空间。"
        ),
        "artifacts": [
            {
                "id": "artifact_code_001",
                "type": "code",
                "title": "Todo App Component",
                "data": {
                    "filename": "src/App.tsx",
                    "language": "tsx",
                    "content": TODO_APP_CODE,
                },
                "created_at": "2026-06-03T09:04:00Z",
            },
            {
                "id": "artifact_diff_001",
                "type": "diff",
                "title": "Todo App Diff",
                "data": {
                    "filename": "src/App.tsx",
                    "diff": TODO_APP_DIFF,
                },
                "created_at": "2026-06-03T09:04:10Z",
            },
        ],
        "created_at": "2026-06-03T09:04:00Z",
    },
    {
        "id": "msg_004",
        "conversation_id": "conv_001",
        "role": "agent",
        "sender_id": "review-agent",
        "content": (
            "## Review 结果\n\n"
            "| 检查项 | 结论 | 建议 |\n"
            "| --- | --- | --- |\n"
            "| 空状态 | 通过 | 初始任务足够支撑 Demo |\n"
            "| 移动端 | 有风险 | 标题和按钮需要换行保护 |\n"
            "| Diff 应用 | 通过 | artifact 中已有 unified diff |\n\n"
            "- 建议 Apply Diff 后立即刷新右侧预览。\n"
            "- 代码块已经适合 Markdown 渲染和复制。"
        ),
        "artifacts": [],
        "created_at": "2026-06-03T09:06:00Z",
    },
    {
        "id": "msg_005",
        "conversation_id": "conv_001",
        "role": "user",
        "sender_id": "user",
        "content": "可以，应用这个 Diff，然后帮我看预览状态。",
        "artifacts": [],
        "created_at": "2026-06-03T09:08:00Z",
    },
    {
        "id": "msg_006",
        "conversation_id": "conv_001",
        "role": "agent",
        "sender_id": "preview-agent",
        "content": (
            "## Workspace Preview\n\n"
            "预览已经就绪，右侧 Workspace 面板会展示 iframe、文件列表和变更历史。\n\n"
            "- Workspace: `ws_001`\n"
            "- Status: `ready`\n"
            "- Preview URL: 已写入结构化 preview artifact"
        ),
        "artifacts": [
            {
                "id": "artifact_preview_001",
                "type": "preview",
                "title": "Workspace Preview",
                "data": {
                    "workspace_id": "ws_001",
                    "status": "ready",
                    "preview_url": preview_page_url("ws_001"),
                },
                "created_at": "2026-06-03T09:10:00Z",
            }
        ],
        "created_at": "2026-06-03T09:10:00Z",
    },
    {
        "id": "msg_007",
        "conversation_id": "conv_001",
        "role": "agent",
        "sender_id": "orchestrator",
        "content": (
            "## 小结\n\n"
            "这条会话已经跑通：用户需求 -> 任务拆解 -> 代码生成 -> "
            "Review -> Apply Diff -> Preview。\n\n"
            "下一步如果继续迭代，只需要让 Code Agent 输出新的 Markdown 说明和 diff artifact。"
        ),
        "artifacts": [],
        "created_at": "2026-06-03T09:13:00Z",
    },
    {
        "id": "msg_008",
        "conversation_id": "conv_002",
        "role": "user",
        "sender_id": "user",
        "content": "@ReviewAgent 帮我检查一个落地页首屏，重点看转化、移动端和视觉层级。",
        "artifacts": [],
        "created_at": "2026-06-03T09:21:00Z",
    },
    {
        "id": "msg_009",
        "conversation_id": "conv_002",
        "role": "agent",
        "sender_id": "review-agent",
        "content": (
            "## Landing Page Review\n\n"
            "整体方向清楚，但首屏还有三个会影响转化的点：\n\n"
            "1. **CTA 层级不够稳定**：主按钮和次按钮视觉权重接近。\n"
            "2. **移动端标题可能过长**：建议限制行宽并允许自然换行。\n"
            "3. **信任证据出现太晚**：首屏下沿应露出客户案例或指标。\n\n"
            "| 风险 | 等级 | 处理方式 |\n"
            "| --- | --- | --- |\n"
            "| CTA 混淆 | medium | 主按钮使用实色，次按钮降权 |\n"
            "| 移动端拥挤 | medium | 标题控制在 2-3 行 |\n"
            "| 缺少证据 | low | 加一条数据型 proof |\n"
        ),
        "artifacts": [],
        "created_at": "2026-06-03T09:23:00Z",
    },
    {
        "id": "msg_010",
        "conversation_id": "conv_002",
        "role": "user",
        "sender_id": "user",
        "content": "如果只改文案，不动布局，你会怎么建议？",
        "artifacts": [],
        "created_at": "2026-06-03T09:25:00Z",
    },
    {
        "id": "msg_011",
        "conversation_id": "conv_002",
        "role": "agent",
        "sender_id": "review-agent",
        "content": (
            "## 只改文案的版本\n\n"
            "> 目标是让用户在 5 秒内知道：它解决什么问题、为什么可信、下一步点哪里。\n\n"
            "- H1：从“智能开发平台”改成“让多个 AI Agent 一起完成开发任务”。\n"
            "- 副标题：强调 `聊天记录 + Diff + 预览` 的闭环。\n"
            "- CTA：主按钮写“开始一个开发会话”，次按钮写“查看 Demo 流程”。"
        ),
        "artifacts": [],
        "created_at": "2026-06-03T09:27:00Z",
    },
    {
        "id": "msg_012",
        "conversation_id": "conv_002",
        "role": "user",
        "sender_id": "user",
        "content": "移动端最担心什么？",
        "artifacts": [],
        "created_at": "2026-06-03T09:29:00Z",
    },
    {
        "id": "msg_013",
        "conversation_id": "conv_002",
        "role": "agent",
        "sender_id": "review-agent",
        "content": (
            "## 移动端优先级\n\n"
            "最担心的是按钮和标题挤压输入区域。建议：\n\n"
            "- 首屏只保留一个主 CTA。\n"
            "- 导航不要超过 3 个可见入口。\n"
            "- 文案不要依赖横向排列的对比卡片。\n\n"
            "这类调整不影响后端，可以作为前端体验优化独立完成。"
        ),
        "artifacts": [],
        "created_at": "2026-06-03T09:31:00Z",
    },
    {
        "id": "msg_014",
        "conversation_id": "conv_003",
        "role": "user",
        "sender_id": "user",
        "content": "@Orchestrator Todo 输入框现在空字符串也会新增任务，请组织修复并 review。",
        "artifacts": [],
        "created_at": "2026-06-03T09:41:00Z",
    },
    {
        "id": "msg_015",
        "conversation_id": "conv_003",
        "role": "agent",
        "sender_id": "orchestrator",
        "content": (
            "## Bug 修复计划\n\n"
            "我会让 Code Agent 先修复输入归一化，再交给 Review Agent 检查边界。\n\n"
            "```txt\n"
            "用户输入 -> trim -> 空值拦截 -> 更新 todos -> 清空输入\n"
            "```\n\n"
            "修复完成后由 Preview Agent 刷新 `ws_003`。"
        ),
        "artifacts": [],
        "created_at": "2026-06-03T09:43:00Z",
    },
    {
        "id": "msg_016",
        "conversation_id": "conv_003",
        "role": "agent",
        "sender_id": "code-agent",
        "content": (
            "## 修复输入空值问题\n\n"
            "我把提交逻辑改为先 `trim()`，空字符串直接显示错误，不再写入列表。\n\n"
            "```ts file=src/todo-actions.ts\n"
            f"{BUG_FIX_CODE}"
            "```\n\n"
            "Diff 已附加为结构化 artifact，可以直接 Apply。"
        ),
        "artifacts": [
            {
                "id": "artifact_code_bugfix_001",
                "type": "code",
                "title": "Todo Submit Guard",
                "data": {
                    "filename": "src/todo-actions.ts",
                    "language": "ts",
                    "content": BUG_FIX_CODE,
                },
                "created_at": "2026-06-03T09:46:00Z",
            },
            {
                "id": "artifact_diff_bugfix_001",
                "type": "diff",
                "title": "Trim Empty Todo Diff",
                "data": {"filename": "src/todo-actions.ts", "diff": BUG_FIX_DIFF},
                "created_at": "2026-06-03T09:46:10Z",
            },
        ],
        "created_at": "2026-06-03T09:46:00Z",
    },
    {
        "id": "msg_017",
        "conversation_id": "conv_003",
        "role": "agent",
        "sender_id": "review-agent",
        "content": (
            "## Review 结论\n\n"
            "- [x] 空字符串不会新增任务。\n"
            "- [x] 输入会在成功提交后清空。\n"
            "- [x] 错误文案不泄露内部实现。\n\n"
            "剩余建议：把错误提示放在输入框下方，不要用浏览器 alert。"
        ),
        "artifacts": [],
        "created_at": "2026-06-03T09:49:00Z",
    },
    {
        "id": "msg_018",
        "conversation_id": "conv_003",
        "role": "agent",
        "sender_id": "preview-agent",
        "content": (
            "## 修复预览\n\n`ws_003` 已经刷新为 ready。右侧可以看到当前文件和最新变更历史。"
        ),
        "artifacts": [
            {
                "id": "artifact_preview_bugfix_001",
                "type": "preview",
                "title": "Bug Fix Preview",
                "data": {
                    "workspace_id": "ws_003",
                    "status": "ready",
                    "preview_url": preview_page_url("ws_003"),
                },
                "created_at": "2026-06-03T09:52:00Z",
            }
        ],
        "created_at": "2026-06-03T09:52:00Z",
    },
    {
        "id": "msg_019",
        "conversation_id": "conv_003",
        "role": "user",
        "sender_id": "user",
        "content": "这个修复可以作为答辩时的迭代例子。",
        "artifacts": [],
        "created_at": "2026-06-03T09:55:00Z",
    },
    {
        "id": "msg_020",
        "conversation_id": "conv_004",
        "role": "user",
        "sender_id": "user",
        "content": "@PreviewAgent 展示一下右侧 workspace 面板应该怎么工作。",
        "artifacts": [],
        "created_at": "2026-06-03T10:01:00Z",
    },
    {
        "id": "msg_021",
        "conversation_id": "conv_004",
        "role": "agent",
        "sender_id": "preview-agent",
        "content": (
            "## Workspace 面板说明\n\n"
            "右侧不再重复聊天里的 artifact，而是展示三个真正有用的信息：\n\n"
            "1. iframe 预览当前 workspace。\n"
            "2. 文件列表帮助定位 Agent 改了什么。\n"
            "3. 变更历史记录用户已经应用过哪些 Diff。"
        ),
        "artifacts": [
            {
                "id": "artifact_preview_workspace_001",
                "type": "preview",
                "title": "Workspace Panel Preview",
                "data": {
                    "workspace_id": "ws_004",
                    "status": "ready",
                    "preview_url": preview_page_url("ws_004"),
                },
                "created_at": "2026-06-03T10:03:00Z",
            }
        ],
        "created_at": "2026-06-03T10:03:00Z",
    },
    {
        "id": "msg_022",
        "conversation_id": "conv_004",
        "role": "agent",
        "sender_id": "code-agent",
        "content": (
            "## HTML 预览示例\n\n"
            "下面这个 HTML 代码块可以直接在聊天里点“预览”：\n\n"
            "```html file=index.html\n"
            '<main style="font-family: system-ui; padding: 32px">\n'
            "  <h1>AgentHub Workspace</h1>\n"
            "  <p>Preview, files, and applied diffs live in the right panel.</p>\n"
            "</main>\n"
            "```"
        ),
        "artifacts": [],
        "created_at": "2026-06-03T10:05:00Z",
    },
    {
        "id": "msg_023",
        "conversation_id": "conv_004",
        "role": "agent",
        "sender_id": "review-agent",
        "content": (
            "## 面板 Review\n\n"
            "- 不再展示重复 artifact，信息噪音明显降低。\n"
            "- iframe、文件、历史是三个不同维度，适合放在右栏。\n"
            "- 如果移动端宽度不足，右栏可以隐藏，不影响聊天主流程。"
        ),
        "artifacts": [],
        "created_at": "2026-06-03T10:08:00Z",
    },
    {
        "id": "msg_024",
        "conversation_id": "conv_004",
        "role": "user",
        "sender_id": "user",
        "content": "这个方向比产物卡片列表清晰很多。",
        "artifacts": [],
        "created_at": "2026-06-03T10:10:00Z",
    },
    {
        "id": "msg_025",
        "conversation_id": "conv_004",
        "role": "agent",
        "sender_id": "preview-agent",
        "content": (
            "## Demo 提示\n\n"
            "答辩时可以先展示聊天主回复的 Markdown 排版，再点击 Apply Diff，"
            "最后说明右侧面板只承载 workspace 状态。"
        ),
        "artifacts": [],
        "created_at": "2026-06-03T10:12:00Z",
    },
]

# Preview 表默认数据。
#
# 字段说明：
# - workspace_id: 预览状态所属工作区。
# - status: not_started/running/ready/error，右侧预览面板直接展示。
DEFAULT_PREVIEWS: list[dict[str, Any]] = [
    {"workspace_id": "ws_001", "status": "ready", "preview_url": preview_page_url("ws_001")},
    {"workspace_id": "ws_002", "status": "ready", "preview_url": preview_page_url("ws_002")},
    {"workspace_id": "ws_003", "status": "ready", "preview_url": preview_page_url("ws_003")},
    {"workspace_id": "ws_004", "status": "ready", "preview_url": preview_page_url("ws_004")},
]

# Workspace 文件表默认数据。
#
# 字段说明：
# - workspace_id: 文件所属工作区。
# - path: 工作区内相对路径，前端文件树和文件查看使用。
# - content: 文件正文。
# - updated_at: 最近写入时间。
DEFAULT_WORKSPACE_FILES: list[dict[str, Any]] = [
    {
        "workspace_id": "ws_001",
        "path": "src/App.tsx",
        "content": TODO_APP_CODE,
        "updated_at": "2026-06-03T09:09:00Z",
    },
    {
        "workspace_id": "ws_001",
        "path": "index.html",
        "content": "<main><h1>Team Todo</h1><p>Diff 已应用，预览已就绪。</p></main>",
        "updated_at": "2026-06-03T09:10:00Z",
    },
    {
        "workspace_id": "ws_002",
        "path": "src/LandingReview.md",
        "content": "# Landing Review\n\nCTA、移动端、信任证据是主要风险。\n",
        "updated_at": "2026-06-03T09:31:00Z",
    },
    {
        "workspace_id": "ws_002",
        "path": "index.html",
        "content": "<main><h1>Landing Review</h1><p>Review Agent 输出首屏优化建议。</p></main>",
        "updated_at": "2026-06-03T09:31:00Z",
    },
    {
        "workspace_id": "ws_003",
        "path": "src/todo-actions.ts",
        "content": BUG_FIX_CODE,
        "updated_at": "2026-06-03T09:52:00Z",
    },
    {
        "workspace_id": "ws_003",
        "path": "index.html",
        "content": "<main><h1>Bug Fix Ready</h1><p>空输入已被拦截。</p></main>",
        "updated_at": "2026-06-03T09:52:00Z",
    },
    {
        "workspace_id": "ws_004",
        "path": "index.html",
        "content": (
            '<main style="font-family: system-ui; padding: 32px">'
            "<h1>AgentHub Workspace</h1>"
            "<p>Preview, files, and applied diffs live in the right panel.</p>"
            "</main>"
        ),
        "updated_at": "2026-06-03T10:03:00Z",
    },
    {
        "workspace_id": "ws_004",
        "path": "README.md",
        "content": "# Workspace Preview Demo\n\n右栏展示 iframe、文件树、变更历史。\n",
        "updated_at": "2026-06-03T10:08:00Z",
    },
]

DEFAULT_APPLIED_DIFFS: list[dict[str, Any]] = [
    {
        "id": "apply_todo_001",
        "workspace_id": "ws_001",
        "artifact_id": "artifact_diff_001",
        "diff": TODO_APP_DIFF,
        "applied_at": "2026-06-03T09:09:00Z",
    },
    {
        "id": "apply_bugfix_001",
        "workspace_id": "ws_003",
        "artifact_id": "artifact_diff_bugfix_001",
        "diff": BUG_FIX_DIFF,
        "applied_at": "2026-06-03T09:52:00Z",
    },
    {
        "id": "apply_workspace_001",
        "workspace_id": "ws_004",
        "artifact_id": "artifact_preview_workspace_001",
        "diff": "--- a/index.html\n+++ b/index.html\n@@\n+<h1>AgentHub Workspace</h1>\n",
        "applied_at": "2026-06-03T10:03:00Z",
    },
]

# 下面这些变量就是“表对象”：
# - 路由函数不直接拼文件路径，而是通过表对象读取/保存数据。
# - users/agents/conversations/messages 是核心业务表。
# - previews/workspace_files/applied_diffs 是 workspace 演示链路需要的辅助表。
users_table = JsonTable(
    "users",
    [{"id": "user", "name": "Demo User", "created_at": "2026-06-01T09:00:00Z"}],
)
agents_table = JsonTable("agents", DEFAULT_AGENTS)
conversations_table = JsonTable("conversations", DEFAULT_CONVERSATIONS)
messages_table = JsonTable("messages", DEFAULT_MESSAGES)
previews_table = JsonTable("previews", DEFAULT_PREVIEWS)
workspace_files_table = JsonTable("workspace_files", DEFAULT_WORKSPACE_FILES)
applied_diffs_table = JsonTable("applied_diffs", DEFAULT_APPLIED_DIFFS)

# Flask 应用对象。前端默认请求 `http://127.0.0.1:5001/api/...`。
app = Flask(__name__)


@app.after_request
def add_cors_headers(response: Response) -> Response:
    """给所有响应追加 CORS 头。

    前端 Vite dev server 一般运行在 5173/5174，Flask 运行在 5001，
    浏览器会把这视为跨域请求。这里统一放行本地联调需要的 HTTP 方法。
    """

    # Vite dev server 和 Flask 不同端口运行，必须允许跨域请求。
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,PATCH,DELETE,OPTIONS"
    return response


@app.before_request
def handle_preflight() -> tuple[str, int] | None:
    """处理浏览器 OPTIONS 预检请求。

    当前端发送 POST/PATCH/DELETE 或 JSON body 时，浏览器会先发 OPTIONS。
    预检请求不需要读写 JSON 表，直接返回 204 即可。
    """

    # 浏览器预检请求不进入业务路由。
    if request.method == "OPTIONS":
        return "", 204
    return None


def get_json_body() -> dict[str, Any]:
    """安全读取 JSON 请求体。

    Returns:
        如果请求体是 JSON 对象，则返回 dict；否则返回空 dict。

    这样路由函数可以统一从 dict 中取字段，再自己决定哪些字段必填。
    """

    # Flask 的 silent=True 可以避免非法 JSON 直接抛异常，便于返回统一错误。
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else {}


def get_conversation_or_error(conversation_id: str) -> dict[str, Any] | None:
    """按会话 id 获取会话。

    返回 None 表示会话不存在，调用方负责把它转成 404 错误响应。
    """

    return conversations_table.find(conversation_id)


def save_conversation(updated_conversation: dict[str, Any]) -> None:
    """保存单个会话的更新结果。

    JSON 表没有“按 id 更新一行”的能力，所以这里读取整张 conversations 表，
    用更新后的会话替换同 id 记录，再整体保存。
    """

    rows = conversations_table.all()
    conversations_table.save(
        [updated_conversation if row["id"] == updated_conversation["id"] else row for row in rows]
    )


def sort_conversations(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """排序会话列表。

    当前规则：
    - `is_pinned=True` 的会话排在前面；
    - 未置顶会话按 `updated_at` 字符串排序。

    `updated_at` 使用 ISO 字符串，适合做字典序排序；如果后续要严格“最新优先”，
    可以在这里统一调整，前端不需要改排序规则。
    """

    # 置顶优先，排序逻辑集中在后端，前端只负责展示接口返回顺序。
    return sorted(
        rows,
        key=lambda row: (not row.get("is_pinned", False), row.get("updated_at", "")),
        reverse=False,
    )


def get_preview(workspace_id: str) -> dict[str, Any]:
    """读取指定 workspace 的预览状态。

    如果 JSON 表里没有对应记录，则返回默认的 not_started；这样前端切换到一个
    新建会话时，也能拿到稳定结构，而不是空值。
    """

    previews = previews_table.all()
    preview = next(
        (row for row in previews if row.get("workspace_id") == workspace_id),
        None,
    )
    return preview or {"workspace_id": workspace_id, "status": "not_started"}


def upsert_preview(
    workspace_id: str,
    status: PreviewStatus,
    preview_url: str | None = None,
) -> dict[str, Any]:
    """新增或更新 workspace 预览状态。

    Args:
        workspace_id: 会话绑定的工作区 id。
        status: 新状态，必须是 PreviewStatus 定义的四种之一。

    Returns:
        写入后的 preview 记录，结构为 `{ workspace_id, status }`。
    """

    previews = previews_table.all()

    # preview 表以 workspace_id 作为业务主键，而不是通用 id。
    # 更新状态时保留 preview_url，避免 Apply Diff 后右侧 iframe 地址丢失。
    existing_preview = next(
        (row for row in previews if row.get("workspace_id") == workspace_id),
        {},
    )
    preview = {**existing_preview, "workspace_id": workspace_id, "status": status}
    if preview_url is not None:
        preview["preview_url"] = preview_url
    found = False
    next_previews = []

    for row in previews:
        if row.get("workspace_id") == workspace_id:
            next_previews.append(preview)
            found = True
        else:
            next_previews.append(row)

    if not found:
        next_previews.append(preview)

    previews_table.save(next_previews)
    return preview


def normalize_workspace_file_path(path: str) -> str:
    """校验并规范化 workspace 内文件路径。"""

    value = path.strip()
    if value.startswith(("a/", "b/")):
        value = value[2:]

    candidate = PurePosixPath(value)
    if (
        not value
        or candidate.is_absolute()
        or any(part in {"", ".", ".."} for part in candidate.parts)
    ):
        raise ValueError("文件路径必须是 workspace 内的相对路径")
    return candidate.as_posix()


def get_workspace_file_content_value(workspace_id: str, path: str) -> str:
    """读取 workspace 文件正文；不存在时返回空字符串。"""

    normalized_path = normalize_workspace_file_path(path)
    row = next(
        (
            item
            for item in workspace_files_table.all()
            if item.get("workspace_id") == workspace_id and item.get("path") == normalized_path
        ),
        None,
    )
    return str(row.get("content", "")) if row is not None else ""


def create_workspace_unified_diff(old: str, new: str, filename: str) -> str:
    """按 workspace 文件内容生成 Git 风格 unified diff。"""

    normalized_filename = normalize_workspace_file_path(filename)
    return create_unified_diff(old, new, normalized_filename)


def extract_diff_target_path(diff: str) -> str:
    """从 unified diff 的 `+++` 文件头中提取目标 workspace 路径。"""

    for line in diff.splitlines():
        if line.startswith("+++ "):
            path = line[4:].strip()
            if path == "/dev/null":
                raise ValueError("当前 Demo 暂不支持删除文件 Diff")
            return normalize_workspace_file_path(path)
    raise ValueError("Diff 缺少目标文件头")


def apply_unified_diff_to_content(old_content: str, diff: str) -> str:
    """把单文件 unified diff 应用到旧内容，返回新内容。"""

    try:
        return apply_workspace_diff(old_content, diff)
    except DiffApplyError as error:
        raise ValueError(str(error)) from error


def upsert_workspace_file(
    workspace_id: str,
    path: str,
    content: str,
    updated_at: str,
) -> dict[str, Any]:
    """新增或覆盖 workspace 文件记录。"""

    normalized_path = normalize_workspace_file_path(path)
    rows = workspace_files_table.all()
    next_rows: list[dict[str, Any]] = []
    file_record = {
        "workspace_id": workspace_id,
        "path": normalized_path,
        "content": content,
        "updated_at": updated_at,
    }
    found = False

    for row in rows:
        if row.get("workspace_id") == workspace_id and row.get("path") == normalized_path:
            next_rows.append(file_record)
            found = True
        else:
            next_rows.append(row)

    if not found:
        next_rows.append(file_record)

    workspace_files_table.save(next_rows)
    return file_record


def ensure_code_artifact_diffs(
    workspace_id: str,
    artifacts: list[Any],
) -> list[dict[str, Any]]:
    """为缺少 diff 的 code artifact 自动生成待应用 Diff。"""

    normalized_artifacts = [
        deepcopy(artifact) for artifact in artifacts if isinstance(artifact, dict)
    ]
    diff_filenames: set[str] = set()
    for artifact in normalized_artifacts:
        data = artifact.get("data") if isinstance(artifact.get("data"), dict) else {}
        if artifact.get("type") != "diff" or not data.get("filename"):
            continue
        try:
            diff_filenames.add(normalize_workspace_file_path(str(data["filename"])))
        except ValueError:
            continue

    for artifact in list(normalized_artifacts):
        data = artifact.get("data") if isinstance(artifact.get("data"), dict) else {}
        if artifact.get("type") != "code":
            continue

        filename = data.get("filename")
        content = data.get("content")
        if not isinstance(filename, str) or not isinstance(content, str):
            continue

        try:
            normalized_filename = normalize_workspace_file_path(filename)
        except ValueError:
            continue
        if normalized_filename in diff_filenames:
            continue

        old_content = get_workspace_file_content_value(workspace_id, normalized_filename)
        diff = create_workspace_unified_diff(old_content, content, normalized_filename)
        if diff:
            normalized_artifacts.append(
                create_agent_artifact(
                    "diff",
                    f"{normalized_filename} Diff",
                    {
                        "filename": normalized_filename,
                        "diff": diff,
                        "source_artifact_id": str(artifact.get("id", "")),
                    },
                )
            )
            diff_filenames.add(normalized_filename)

    return normalized_artifacts


def create_agent_artifact(kind: str, title: str, data: dict[str, Any]) -> dict[str, Any]:
    """生成 Agent 返回的结构化产物。

    Args:
        kind: Artifact 类型，例如 code/diff/preview/file/deploy。
        title: 前端卡片标题。
        data: 类型相关数据：
            - code: filename/language/content
            - diff: filename/diff
            - preview: workspace_id/status/checked_at
            - file: summary/steps/findings 等说明性数据
    """

    return {
        # id 让前端可以定位某个 Artifact，例如 Apply Diff 时传 artifact_id。
        "id": make_id(f"artifact_{kind}"),
        # type 决定前端使用哪种卡片渲染。
        "type": kind,
        # title 是卡片标题，不参与业务判断。
        "title": title,
        # data 是 Artifact 的核心载荷，不同 type 的结构不同。
        "data": data,
        # created_at 用于排序、展示和调试。
        "created_at": now_iso(),
    }


def get_task_title(message: str) -> str:
    """从用户消息中提取一个短任务标题。

    前端发送的消息可能带 `@Orchestrator`、`@CodeAgent` 等 mention。
    这里去掉 mention，只保留自然语言需求，并截断为适合卡片展示的短标题。
    """

    cleaned = (
        message.replace("@Orchestrator", "")
        .replace("@CodeAgent", "")
        .replace("@ReviewAgent", "")
        .replace("@PreviewAgent", "")
        .strip()
    )
    return cleaned[:28] or "开发任务"


def build_code_agent_result(input_data: dict[str, Any]) -> dict[str, Any]:
    """构造 Code Agent 的返回结果。

    入参使用前端 `POST /api/agents/run` 的请求体，核心字段：
    - conversation_id: 当前会话 id。
    - workspace_id: 当前工作区 id。
    - user_message: 用户输入的原始需求。
    - context.agent_id: 本次要调用的 Agent。

    返回结构对齐 AgentRunResult：
    - agent_id: 实际响应的 Agent。
    - content: 聊天气泡中的自然语言说明。
    - artifacts: 结构化产物，Code Agent 主要返回 code 和 diff。
    - next_actions: 建议前端/编排器后续调用 review、preview。
    """

    task_title = get_task_title(str(input_data.get("user_message", "")))

    # 随机选择一点展示细节，让每次 Agent 回复不完全相同，更接近真实生成结果。
    accent = random.choice(["#235b54", "#3f6c8f", "#7a5c22", "#6a5acd"])
    button_text = random.choice(["Add task", "Create todo", "Save item"])

    # code artifact 的正文：前端会以代码块形式展示 data.content。
    content = (
        "const initialTodos = ['梳理需求', '生成代码', '检查 Diff']\n\n"
        "export default function App() {\n"
        "  return (\n"
        f"    <main className=\"todo-app\" style={{{{ '--accent': '{accent}' }}}}>\n"
        f"      <h1>{task_title}</h1>\n"
        f"      <button>{button_text}</button>\n"
        "    </main>\n"
        "  )\n"
        "}\n"
    )
    html_preview = (
        '<main style="font-family: system-ui; padding: 32px; background: #f6f3ed;">\n'
        f"  <h1>{task_title}</h1>\n"
        "  <p>这是 Code Agent 为聊天内 Modal 准备的静态 HTML 预览。</p>\n"
        f"  <button>{button_text}</button>\n"
        "</main>\n"
    )

    filename = "src/App.tsx"
    workspace_id = str(input_data.get("workspace_id", ""))
    old_content = get_workspace_file_content_value(workspace_id, filename)

    # diff artifact 的正文来自当前 workspace 文件状态，点击 Apply 后会真正落到文件表。
    diff = create_workspace_unified_diff(old_content, content, filename)

    markdown_content = (
        f"## 已生成“{task_title}”页面代码\n\n"
        "我先给出一个可直接进入 workspace 的 React 组件，并附上可应用 Diff。\n\n"
        "```tsx file=src/App.tsx\n"
        f"{content}"
        "```\n\n"
        "下面是同一页面的静态 HTML 预览版，点击代码块右上角 **预览** "
        "可以打开 Modal：\n\n"
        "```html file=index.html\n"
        f"{html_preview}"
        "```\n\n"
        "| 产物 | 用途 |\n"
        "| --- | --- |\n"
        "| Markdown 代码块 | 给用户阅读、复制和预览 |\n"
        "| diff artifact | 给系统执行 Apply Diff |\n\n"
        "下一步建议交给 Review Agent 检查交互和移动端风险。"
    )

    return {
        # 这里必须返回 code-agent，前端根据 agent_id 关联头像和名称。
        "agent_id": "code-agent",
        "content": markdown_content,
        "artifacts": [
            create_agent_artifact(
                "code",
                "Todo App Component",
                {"filename": filename, "language": "tsx", "content": content},
            ),
            create_agent_artifact(
                "diff",
                "Todo App Diff",
                {"filename": filename, "diff": diff},
            ),
        ],
        "next_actions": [AGENT_REVIEW, AGENT_PREVIEW],
    }


def build_review_agent_result() -> dict[str, Any]:
    """构造 Review Agent 的返回结果。

    Review Agent 当前不修改 workspace，只返回检查意见。它的 Artifact 使用 file
    类型承载 findings/risk_level，前端会用通用 Artifact 卡片展示。
    """

    # 随机选择一组审查意见，让演示时每次回复有一点变化。
    findings = random.choice(
        [
            ["按钮需要 disabled 状态", "空列表要有提示", "移动端标题需要换行保护"],
            ["Diff 应用失败要提示", "输入框需要 trim", "预览未就绪时不要展示空 iframe"],
            ["Artifact 卡片要可滚动", "Agent 回复要保留时间线", "长文件名需要省略显示"],
        ]
    )
    markdown_content = (
        "## Review Agent 检查结果\n\n"
        "我重点检查了 Demo 稳定性、聊天可读性和 workspace 操作闭环。\n\n"
        "| 检查项 | 结论 |\n"
        "| --- | --- |\n"
        f"| 主要风险 | {'、'.join(findings)} |\n"
        "| Apply Diff | 保持结构化 artifact 驱动，可靠 |\n"
        "| Markdown 回复 | 适合比赛展示和答辩讲解 |\n\n"
        "建议优先处理：\n" + "\n".join(f"- {finding}" for finding in findings)
    )

    return {
        "agent_id": "review-agent",
        "content": markdown_content,
        "artifacts": [
            create_agent_artifact(
                "file",
                "Review Notes",
                {"findings": findings, "risk_level": random.choice(["low", "medium"])},
            )
        ],
        "next_actions": [AGENT_PREVIEW],
    }


def build_preview_agent_result(input_data: dict[str, Any]) -> dict[str, Any]:
    """构造 Preview Agent 的返回结果。

    Preview Agent 会更新 preview 表，所以它不只是返回消息，还会改变右侧预览面板
    读取到的 workspace 状态。
    """

    workspace_id = str(input_data.get("workspace_id", "ws_unknown"))

    # ready 权重更高，保证 Demo 大多数情况下可以展示“预览已就绪”。
    status: PreviewStatus = random.choice(["ready", "ready", "running"])
    preview_url = preview_page_url(workspace_id)
    upsert_preview(workspace_id, status, preview_url)
    markdown_content = (
        "## Workspace Preview\n\n"
        f"- Workspace: `{workspace_id}`\n"
        f"- Status: `{status}`\n"
        f"- Preview URL: `{preview_url}`\n\n"
        + (
            "预览环境已就绪，右侧 Workspace 面板会显示 iframe、文件列表和变更历史。"
            if status == "ready"
            else "预览服务正在启动，右侧状态会显示为 running。"
        )
    )
    return {
        "agent_id": "preview-agent",
        "content": markdown_content,
        "artifacts": [
            create_agent_artifact(
                "preview",
                "Workspace Preview",
                {
                    "workspace_id": workspace_id,
                    "status": status,
                    "checked_at": now_iso(),
                    "preview_url": preview_url,
                },
            )
        ],
        "next_actions": [],
    }


def build_orchestrator_result(input_data: dict[str, Any]) -> dict[str, Any]:
    """构造 Orchestrator 的任务拆解结果。

    Orchestrator 负责把用户需求拆成多个 Agent 步骤。当前实现是规则版：
    固定输出 Code -> Review -> Preview 的协作流程，满足比赛 Demo 主线。
    """

    task_title = get_task_title(str(input_data.get("user_message", "")))

    steps = ["Code Agent 生成页面代码", "Review Agent 检查实现风险", "Preview Agent 准备预览状态"]
    code_task = AgentTask(
        task_id="plan-code",
        agent_id=AGENT_CODE,
        instruction=f"为“{task_title}”生成代码和可应用 Diff",
    )
    review_task = AgentTask(
        task_id="plan-review",
        agent_id=AGENT_REVIEW,
        instruction="检查 Code Agent 产物的交互、稳定性和移动端风险",
        depends_on=[code_task.task_id],
    )
    preview_task = AgentTask(
        task_id="plan-preview",
        agent_id=AGENT_PREVIEW,
        instruction="刷新 workspace 预览状态并反馈右侧面板结果",
        depends_on=[review_task.task_id],
    )
    plan = OrchestratorPlan(
        summary="Rule-based MVP plan",
        tasks=[code_task, review_task, preview_task],
    )

    markdown_content = (
        f"## “{task_title}”任务拆解\n\n"
        "我会按多 Agent 协作链路推进：\n\n"
        + "\n".join(f"{index}. {step}" for index, step in enumerate(steps, start=1))
        + "\n\n> 结构化 artifacts 只用于执行动作，主要回复会以 Markdown 形式留在聊天记录里。"
    )

    return {
        "agent_id": "orchestrator",
        "content": markdown_content,
        "artifacts": [
            create_agent_artifact(
                "file",
                "Task Breakdown",
                {
                    "summary": plan.summary,
                    "task_title": task_title,
                    "steps": steps,
                    "tasks": [task.model_dump() for task in plan.tasks],
                    "agent_ids": plan.agent_ids,
                    "estimated_minutes": random.randint(6, 14),
                },
            )
        ],
        "next_actions": plan.agent_ids,
    }


@app.get("/health")
def health() -> tuple[Response, int]:
    """健康检查接口。

    前端或启动脚本可用它确认 Flask 服务已经启动，不涉及任何 JSON 表读写。
    """

    return success({"status": "ok"})


@app.get("/api/users")
def list_users() -> tuple[Response, int]:
    """返回用户列表。

    当前 MVP 只有一个 Demo User；保留这个接口是为了后续扩展真实登录用户。
    """

    return success(users_table.all())


@app.get("/api/agents")
def list_agents() -> tuple[Response, int]:
    """返回可用 Agent 列表。

    前端用途：
    - 左侧 Agent 联系人列表。
    - 新建会话时选择 Agent。
    - 输入框 @ 菜单显示 Agent。
    """

    return success(agents_table.all())


@app.get("/api/conversations")
def list_conversations() -> tuple[Response, int]:
    """返回会话列表。

    数据来源：`conversations.json`。
    返回前会统一排序，前端只按接口返回顺序展示，避免前后端排序规则分叉。
    """

    return success(sort_conversations(conversations_table.all()))


@app.post("/api/conversations")
def create_conversation() -> tuple[Response, int]:
    """创建新会话。

    请求体字段：
    - title: 必填，会话标题。
    - agent_ids: 必填，当前会话包含的 Agent id 数组。
    - is_pinned: 可选，是否创建后立即置顶。

    写入：
    - conversations.json: 新增会话记录。
    - previews.json: 为新 workspace 初始化 not_started 预览状态。
    """

    body = get_json_body()
    title = str(body.get("title", "")).strip()
    agent_ids = body.get("agent_ids")

    if not title:
        return failure("会话标题不能为空", 400)
    if not isinstance(agent_ids, list) or not agent_ids:
        return failure("创建会话至少需要选择一个 Agent", 400)

    timestamp = now_iso()
    conversation_id = make_id("conv")
    conversation = {
        # 会话 id，用于后续获取详情、消息、删除和更新。
        "id": conversation_id,
        # 会话标题，展示在侧边栏和聊天头部。
        "title": title,
        # mode 根据 agent_ids 自动推导，减少前端传错模式的可能。
        "mode": infer_mode([str(agent_id) for agent_id in agent_ids]),
        # agent_ids 决定这个会话里允许 @ 和调用哪些 Agent。
        "agent_ids": [str(agent_id) for agent_id in agent_ids],
        # is_pinned 是置顶按钮会修改的字段。
        "is_pinned": bool(body.get("is_pinned", False)),
        # workspace_id 把会话、预览、文件、Diff 应用串起来。
        "workspace_id": make_id("ws"),
        # created_at 和 updated_at 分开记录，便于后续做审计或排序。
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    conversations = conversations_table.all()
    conversations.append(conversation)
    conversations_table.save(conversations)
    upsert_preview(conversation["workspace_id"], "not_started")
    return success(conversation, 201)


@app.get("/api/conversations/<conversation_id>")
def get_conversation(conversation_id: str) -> tuple[Response, int]:
    """获取单个会话详情。

    Args:
        conversation_id: URL 路径中的会话 id。
    """

    conversation = get_conversation_or_error(conversation_id)
    if conversation is None:
        return failure("会话不存在", 404)
    return success(conversation)


@app.patch("/api/conversations/<conversation_id>")
def update_conversation(conversation_id: str) -> tuple[Response, int]:
    """更新会话。

    支持的请求体字段：
    - title: 修改会话标题，不能为空字符串。
    - agent_ids: 修改会话成员，不能为空数组；同时会重新推导 mode。
    - mode: 兼容直接修改 single/group，但 agent_ids 优先级更高。
    - is_pinned: 置顶/取消置顶。

    每次更新都会刷新 updated_at，让会话列表能反映最近操作时间。
    """

    conversation = get_conversation_or_error(conversation_id)
    if conversation is None:
        return failure("会话不存在，无法更新", 404)

    body = get_json_body()

    # title 只在请求体包含该字段时更新；没传就保留原值。
    if "title" in body:
        title = str(body["title"]).strip()
        if not title:
            return failure("会话标题不能为空", 400)
        conversation["title"] = title

    # agent_ids 是成员管理的核心字段，修改后同步更新 mode。
    if "agent_ids" in body:
        agent_ids = body["agent_ids"]
        if not isinstance(agent_ids, list) or not agent_ids:
            return failure("当前会话至少需要保留一个 Agent", 400)
        conversation["agent_ids"] = [str(agent_id) for agent_id in agent_ids]
        conversation["mode"] = infer_mode(conversation["agent_ids"])
    elif "mode" in body and body["mode"] in ["single", "group"]:
        # 保留 mode 直接更新能力，方便以后接入单独的会话设置表单。
        conversation["mode"] = body["mode"]

    if "is_pinned" in body:
        # is_pinned 用于左侧会话列表置顶按钮。
        conversation["is_pinned"] = bool(body["is_pinned"])

    conversation["updated_at"] = now_iso()
    save_conversation(conversation)
    return success(conversation)


@app.delete("/api/conversations/<conversation_id>")
def delete_conversation(conversation_id: str) -> tuple[Response, int]:
    """删除会话，并清理与它直接关联的数据。

    删除范围：
    - conversations.json 中的会话记录。
    - messages.json 中该会话的所有消息。
    - previews.json 中该会话 workspace 的预览状态。

    注意：workspace_files.json 暂不级联删除，避免误删后续想查看的文件内容。
    """

    conversation = get_conversation_or_error(conversation_id)
    if conversation is None:
        return failure("会话不存在，无法删除", 404)

    # 删除会话本体。
    conversations_table.save(
        [row for row in conversations_table.all() if row["id"] != conversation_id]
    )

    # 删除该会话的聊天记录，保证前端再次查询不会看到孤儿消息。
    messages_table.save(
        [row for row in messages_table.all() if row["conversation_id"] != conversation_id]
    )

    # 删除该 workspace 的 preview 状态；文件内容保留，便于后续排查。
    previews_table.save(
        [row for row in previews_table.all() if row["workspace_id"] != conversation["workspace_id"]]
    )
    return success({"id": conversation_id, "deleted": True})


def list_conversation_messages_data(conversation_id: str) -> list[dict[str, Any]]:
    """读取某个会话下的消息数组，并按创建时间升序排列。"""

    rows = [row for row in messages_table.all() if row.get("conversation_id") == conversation_id]
    return sorted(rows, key=lambda row: row.get("created_at", ""))


@app.get("/api/conversations/<conversation_id>/messages")
def list_conversation_messages(conversation_id: str) -> tuple[Response, int]:
    """获取会话消息列表。

    前端切换会话时会调用它；如果会话不存在，返回 404，避免展示脏数据。
    """

    if get_conversation_or_error(conversation_id) is None:
        return failure("会话不存在，无法获取消息", 404)
    return success(list_conversation_messages_data(conversation_id))


@app.get("/api/messages/<conversation_id>")
def list_messages_alias(conversation_id: str) -> tuple[Response, int]:
    """消息列表接口别名。

    用户需求里提到了 `GET /api/messages/<conversation_id>`；前端主线目前使用
    `/api/conversations/<id>/messages`，这里保留别名方便其他同学联调。
    """

    # 兼容用户提出的 GET /api/messages/<conversation_id> 风格。
    return list_conversation_messages(conversation_id)


def create_message_for_conversation(
    conversation_id: str,
    body: dict[str, Any],
) -> tuple[Response, int]:
    """创建消息的共享实现。

    两个接口都会复用这里：
    - POST /api/conversations/<conversation_id>/messages
    - POST /api/messages

    请求体字段：
    - content: 必填，消息正文。
    - sender_id: 可选，默认 user；非 user 会被视为 Agent 消息。
    - artifacts: 可选，Agent 消息携带的结构化产物数组。
    """

    conversation = get_conversation_or_error(conversation_id)
    if conversation is None:
        return failure("会话不存在，无法创建消息", 404)

    content = str(body.get("content", "")).strip()
    sender_id = str(body.get("sender_id", "user"))
    if not content:
        return failure("消息内容不能为空", 400)

    timestamp = now_iso()
    raw_artifacts = body.get("artifacts") if isinstance(body.get("artifacts"), list) else []
    artifacts = ensure_code_artifact_diffs(conversation["workspace_id"], raw_artifacts)

    message = {
        # 消息主键，前端渲染列表时可作为 key。
        "id": make_id("msg"),
        # 所属会话 id，后续按会话拉取聊天记录。
        "conversation_id": conversation_id,
        # role 控制前端气泡样式：用户消息靠右，Agent/系统消息靠左。
        "role": "user" if sender_id == "user" else "agent",
        # sender_id 用于查找 Agent 名称、头像字母和能力标签。
        "sender_id": sender_id,
        # content 是聊天气泡主体文本。
        "content": content,
        # artifacts 是消息内产物；用户消息一般为空，Agent 消息可能有 code/diff。
        "artifacts": artifacts,
        # created_at 用于消息排序和右侧时间展示。
        "created_at": timestamp,
    }
    messages = messages_table.all()
    messages.append(message)
    messages_table.save(messages)

    # 发消息会刷新会话更新时间，让会话列表能把活跃会话排出来。
    conversation["updated_at"] = timestamp
    save_conversation(conversation)
    return success(message, 201)


@app.post("/api/conversations/<conversation_id>/messages")
def create_conversation_message(conversation_id: str) -> tuple[Response, int]:
    """向指定会话发送一条消息。"""

    return create_message_for_conversation(conversation_id, get_json_body())


@app.post("/api/messages")
def create_message_alias() -> tuple[Response, int]:
    """发送消息接口别名。

    这个接口把 conversation_id 放在请求体里，方便兼容用户提出的接口风格。
    """

    # 兼容用户提出的 POST /api/messages 风格，请求体必须包含 conversation_id。
    body = get_json_body()
    conversation_id = body.get("conversation_id")
    if not isinstance(conversation_id, str) or not conversation_id:
        return failure("conversation_id 不能为空", 400)
    return create_message_for_conversation(conversation_id, body)


@app.post("/api/agents/run")
def run_agent() -> tuple[Response, int]:
    """调用一个 Agent 并返回 AgentRunResult。

    请求体字段对齐前端 AgentRunInput：
    - conversation_id: 当前会话 id。
    - workspace_id: 当前会话绑定的 workspace id。
    - user_message: 用户刚发送的消息。
    - history: 当前会话历史消息，当前规则版暂未使用，保留给真实 Agent。
    - context.agent_id: 本次要调用的 Agent id。

    这个接口会检查 Agent 是否属于当前会话，避免前端绕过会话成员限制直接调用。
    """

    body = get_json_body()
    conversation_id = str(body.get("conversation_id", ""))

    # context 是可扩展字段；目前只读取 agent_id，未来可放模型参数、工具开关等。
    context = body.get("context") if isinstance(body.get("context"), dict) else {}
    agent_id = str(context.get("agent_id", "orchestrator"))
    conversation = get_conversation_or_error(conversation_id)

    if conversation is None:
        return failure("会话不存在，无法调用 Agent", 404)
    if agent_id not in conversation.get("agent_ids", []):
        return failure("该 Agent 不属于当前会话，无法调用", 403)

    # 当前是规则版本地 Agent：根据 agent_id 分发到不同构造函数。
    # 未来接真实 LLM/Agent Adapter 时，可以在这里替换为统一 Adapter 调用。
    if agent_id == "code-agent":
        return success(build_code_agent_result(body))
    if agent_id == "review-agent":
        return success(build_review_agent_result())
    if agent_id == "preview-agent":
        return success(build_preview_agent_result(body))
    return success(build_orchestrator_result(body))


@app.get("/api/workspaces/<workspace_id>/preview")
def get_workspace_preview(workspace_id: str) -> tuple[Response, int]:
    """获取 workspace 预览状态。

    前端右侧 Preview 面板会定期或在切换会话时调用它。
    """

    return success(get_preview(workspace_id))


@app.get("/api/workspaces/<workspace_id>/preview-page")
def get_workspace_preview_page(workspace_id: str) -> Response:
    """返回一个可嵌入 iframe 的 workspace 预览页面。

    Demo 后端优先读取 workspace 中的 `index.html`；如果当前 workspace 没有 HTML
    文件，则返回一个轻量状态页，避免 iframe 空白。
    """

    html_file = next(
        (
            row
            for row in workspace_files_table.all()
            if row.get("workspace_id") == workspace_id and row.get("path") == "index.html"
        ),
        None,
    )
    if html_file is not None:
        return Response(str(html_file.get("content", "")), mimetype="text/html")

    preview = get_preview(workspace_id)
    status = preview.get("status", "not_started")
    return Response(
        (
            '<!doctype html><html><head><meta charset="utf-8">'
            "<style>body{font-family:Inter,system-ui,sans-serif;margin:0;"
            "padding:32px;background:#f6f3ed;color:#1f2926}"
            ".card{border:1px solid #d9d1c5;border-radius:12px;padding:24px;"
            "background:#fff;max-width:560px;margin:auto}"
            "code{background:#eef5f2;border-radius:6px;padding:2px 6px}</style>"
            f'</head><body><section class="card"><h1>{workspace_id}</h1>'
            f"<p>Preview status: <code>{status}</code></p>"
            "<p>当前 workspace 尚未生成 index.html，先展示预览状态页。</p>"
            "</section></body></html>"
        ),
        mimetype="text/html",
    )


@app.post("/api/workspaces/<workspace_id>/apply-diff")
def apply_diff(workspace_id: str) -> tuple[Response, int]:
    """应用 Diff。

    请求体字段：
    - artifact_id: 必填，要应用的 diff artifact id。
    - diff: 必填，unified diff 字符串。

    当前 JSON 版不会真正修改本地项目文件，而是：
    - 把应用记录写入 applied_diffs.json；
    - 把 workspace preview 状态更新为 ready；
    - 返回应用结果给前端更新按钮状态。
    """

    body = get_json_body()
    artifact_id = str(body.get("artifact_id", "")).strip()
    diff = str(body.get("diff", ""))

    if not artifact_id:
        return failure("artifact_id 不能为空", 400)
    if not diff.strip():
        return failure("Diff 内容为空，无法应用", 400)

    try:
        target_path = extract_diff_target_path(diff)
        old_content = get_workspace_file_content_value(workspace_id, target_path)
        new_content = apply_unified_diff_to_content(old_content, diff)
    except ValueError as error:
        return failure(str(error), 400)

    applied_at = now_iso()
    upsert_workspace_file(workspace_id, target_path, new_content, applied_at)
    applied = applied_diffs_table.all()
    applied.append(
        {
            # 应用记录自己的主键，方便后续做历史列表。
            "id": make_id("apply"),
            # 这次 Diff 应用到哪个 workspace。
            "workspace_id": workspace_id,
            # 对应前端点击的 Diff Artifact。
            "artifact_id": artifact_id,
            # 原始 unified diff 内容，便于演示或后续回放。
            "diff": diff,
            # 实际被修改的 workspace 文件路径。
            "path": target_path,
            # 应用时间，用于展示和调试。
            "applied_at": applied_at,
        }
    )
    applied_diffs_table.save(applied)

    # Demo 闭环：Apply Diff 成功后，预览状态变为 ready，并确保右侧 iframe 有地址。
    current_preview_url = get_preview(workspace_id).get("preview_url")
    upsert_preview(
        workspace_id,
        "ready",
        str(current_preview_url) if current_preview_url else preview_page_url(workspace_id),
    )
    return success(
        {
            "workspace_id": workspace_id,
            "status": "ready",
            "applied_artifact_id": artifact_id,
            "path": target_path,
            "applied_at": applied_at,
        }
    )


@app.get("/api/workspaces/<workspace_id>/applied-diffs")
def list_applied_diffs(workspace_id: str) -> tuple[Response, int]:
    """获取当前 workspace 已应用的 Diff 历史。"""

    rows = [row for row in applied_diffs_table.all() if row.get("workspace_id") == workspace_id]
    return success(rows)


@app.get("/api/workspaces/<workspace_id>/files")
def list_workspace_files(workspace_id: str) -> tuple[Response, int]:
    """获取 workspace 文件列表。

    返回字段：
    - path: 文件相对路径。
    - updated_at: 最近更新时间。

    文件正文不在列表接口返回，避免以后文件很多时列表响应过大。
    """

    files = [
        {"path": row["path"], "updated_at": row.get("updated_at")}
        for row in workspace_files_table.all()
        if row.get("workspace_id") == workspace_id
    ]
    return success(files)


@app.get("/api/workspaces/<workspace_id>/files/content")
def get_workspace_file_content(workspace_id: str) -> tuple[Response, int]:
    """获取 workspace 中某个文件的内容。

    Query 参数：
    - path: 必填，workspace 内相对路径，例如 `src/App.tsx`。

    返回整条文件记录：`{ workspace_id, path, content, updated_at }`。
    """

    try:
        path = normalize_workspace_file_path(request.args.get("path", ""))
    except ValueError as error:
        return failure(str(error), 400)
    row = next(
        (
            item
            for item in workspace_files_table.all()
            if item.get("workspace_id") == workspace_id and item.get("path") == path
        ),
        None,
    )
    if row is None:
        return failure("文件不存在", 404)
    return success(row)


@app.post("/api/workspaces/<workspace_id>/files")
def write_workspace_file(workspace_id: str) -> tuple[Response, int]:
    """新增或覆盖 workspace 文件。

    请求体字段：
    - path: 必填，workspace 内相对路径。
    - content: 可选，文件内容，默认空字符串。

    当前是 JSON 表模拟写文件：同 workspace_id + path 存在时覆盖，否则新增。
    """

    body = get_json_body()
    try:
        path = normalize_workspace_file_path(str(body.get("path", "")).strip())
    except ValueError as error:
        return failure(str(error), 400)
    content = str(body.get("content", ""))
    timestamp = now_iso()
    file_record = upsert_workspace_file(workspace_id, path, content, timestamp)
    return success(file_record, 201)


if __name__ == "__main__":
    # 直接运行：python frontend/flask/main.py
    # 启动后前端可通过 http://127.0.0.1:5001/api/... 访问这些接口。
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    app.run(host="127.0.0.1", port=5001, debug=True)
