# AGENTS.md

本文件是 AgentHub 项目的仓库级 AI Coding 指令。Codex、Claude Code、OpenCode、TRAE 或其他 AI Coding 工具在本仓库工作时，必须优先遵守本文件。

## 1. 项目目标

AgentHub 是一个 IM 聊天式多 Agent 协作平台。用户可以像使用飞书/微信一样创建会话、选择 Agent、发送消息，并通过 `@Agent` 让多个 AI Agent 在同一会话中协作完成开发任务。

项目核心演示链路：

```txt
用户提出开发需求
→ Orchestrator 拆解任务
→ 多个 Agent 依次产出
→ 系统展示代码和 Diff
→ 用户应用变更
→ 页面预览更新
→ 聊天记录保留完整协作过程
```

所有开发都应服务于这条主线，不要优先开发偏离主线的大功能。

## 2. 技术方向

本项目采用 **Python-first** 开发策略。

优先技术栈：

- Python 3.11+
- FastAPI：后端 API、SSE 流式输出、Agent 调用入口
- Pydantic v2：请求、响应、领域模型校验
- pydantic-settings：环境变量配置
- SQLModel 或 SQLAlchemy：数据模型与数据库访问
- SQLite：MVP 阶段默认数据库
- httpx：调用外部 Agent / LLM API
- pytest：测试
- ruff：格式化与 lint
- mypy 或 pyright：类型检查
- pathlib：文件路径处理
- difflib / unidiff：Diff 生成与解析
- subprocess：封装 Git 命令，必须限制参数和工作目录

UI 方案：

 **产品体验优先**：允许保留 React/Next.js 前端，但 Agent、Orchestrator、Workspace、后端 API 均使用 Python。


## 3. 当前 MVP 范围

必须优先完成：

1. 会话列表和聊天主界面；
2. 用户消息和 Agent 消息展示；
3. `@Agent` 识别；
4. Orchestrator 任务拆解；
5. Agent Adapter 统一接口；
6. 至少两个子 Agent 的 Mock 调用；
7. 代码卡片、Diff 卡片、预览卡片；
8. workspace 文件读写；
9. Apply Diff；
10. 可稳定演示的端到端 Demo。

暂缓：

1. 多端支持；
2. 用户权限系统；
3. 复杂实时协同；
4. 完整部署平台；
5. 企业级 IM 功能；
6. 复杂并行调度和自动冲突解决。

## 4. 推荐目录结构

```txt
agenthub/
  __init__.py
  api/
    main.py                 # FastAPI app 入口
    deps.py                 # 依赖注入
    routes/
      conversations.py
      messages.py
      agents.py
      workspaces.py
  core/
    config.py               # 环境变量与配置
    logging.py
    errors.py
  models/                   # 数据库模型
    conversation.py
    message.py
    agent.py
    artifact.py
  schemas/                  # Pydantic 请求/响应模型
    conversation.py
    message.py
    agent.py
    artifact.py
  repositories/             # 数据访问层
    conversation_repo.py
    message_repo.py
  agents/
    base.py                 # AgentAdapter 协议与通用模型
    mock_agent.py
    codex_agent.py
    claude_agent.py
    registry.py
  orchestrator/
    planner.py
    scheduler.py
    summarizer.py
  workspace/
    manager.py              # workspace 创建、路径安全、文件读写
    diff.py                 # diff 生成、解析、应用
    git.py                  # git 命令封装
    preview.py              # 预览服务
  services/
    conversation_service.py
    message_service.py
    agent_service.py
  ui/                       # 如果选择 NiceGUI / Reflex，可放这里
  utils/

tests/
  test_agents/
  test_orchestrator/
  test_workspace/
  test_api/

docs/
  product-spec.md
  tech-design.md
  ai-rules.md
  prompt-log.md
  demo-script.md

mock/
  demo_responses/

workspace_samples/
```

如果目录尚未存在，创建前必须说明原因。

## 5. 修改文件规则

Codex 每次执行任务前必须先确认：

1. 本次任务目标是什么；
2. 预计修改哪些文件；
3. 哪些文件不能修改；
4. 是否会影响 API、数据模型或其他成员模块；
5. 如何验证结果。

禁止行为：

1. 不得大范围重构无关代码；
2. 不得删除他人模块；
3. 不得擅自改动目录结构；
4. 不得硬编码 API Key、Token 或本地绝对路径；
5. 不得用伪代码冒充可运行代码；
6. 不得跳过错误处理；
7. 不得在没有说明的情况下引入新依赖；
8. 不得直接修改 `main` 分支相关配置；
9. 不得在没有安全限制的情况下执行 shell 命令。

## 6. Python 编码风格

1. 所有核心代码必须写类型注解；
2. API 入参与出参必须使用 Pydantic 模型；
3. 业务逻辑不要写在 FastAPI route 里，应放入 service / orchestrator / workspace 模块；
4. 文件路径必须使用 `pathlib.Path`；
5. 所有 workspace 文件操作必须限制在 workspace 根目录内；
6. 外部 API 调用优先使用 `httpx.AsyncClient`；
7. 能 async 的 Agent 调用和 API 调用优先使用 async；
8. 不要在模块顶层创建不可控的全局客户端；
9. 错误信息必须可读，但不得泄露密钥；
10. Mock 数据集中放置，不要散落在业务代码中；
11. 不允许提交真实 `.env`；
12. 必须提供 `.env.example`。

## 7. Agent Adapter 接口要求

所有 Agent 调用必须通过统一 Adapter，不得在业务代码中直接调用某个具体平台。

参考接口：

```python
from __future__ import annotations

from typing import Any, Literal, Protocol
from pydantic import BaseModel, Field

ArtifactType = Literal["code", "diff", "preview", "file", "deploy"]

class Artifact(BaseModel):
    id: str
    type: ArtifactType
    title: str
    data: dict[str, Any] = Field(default_factory=dict)

class Message(BaseModel):
    id: str
    conversation_id: str
    role: Literal["user", "agent", "system"]
    sender_id: str
    content: str
    artifacts: list[Artifact] = Field(default_factory=list)

class AgentRunInput(BaseModel):
    conversation_id: str
    workspace_id: str
    user_message: str
    history: list[Message] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)

class AgentRunResult(BaseModel):
    agent_id: str
    content: str
    artifacts: list[Artifact] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)

class AgentAdapter(Protocol):
    id: str
    name: str
    capabilities: list[str]

    async def run(self, input: AgentRunInput) -> AgentRunResult:
        ...
```

## 8. Orchestrator 规则

Orchestrator 负责：

1. 理解用户需求；
2. 拆解任务；
3. 选择子 Agent；
4. 汇总结果；
5. 在聊天流中清晰展示过程。

第一版调度规则：

```txt
写代码 / 实现页面 / 生成组件
→ Code Agent

检查 / review / 优化 / bug
→ Review Agent

预览 / 效果 / 页面展示
→ Preview Agent

用户直接 @ 某个 Agent
→ 优先调用该 Agent

用户 @Orchestrator
→ Orchestrator 拆解并调用多个 Agent
```

## 9. Artifact 输出规则

Agent 返回的产物必须结构化，优先使用 Artifact。

Artifact 类型：

```python
ArtifactType = Literal["code", "diff", "preview", "file", "deploy"]
```

要求：

1. 代码不要只放在自然语言里，应生成 code artifact；
2. 文件变更应生成 diff artifact；
3. 可视化页面应生成 preview artifact；
4. artifact 必须包含 title 和 data；
5. 前端或 Python UI 应能根据 type 渲染不同卡片。

## 10. Git 与分支规则

分支：

```txt
main                  # 稳定可演示版本
dev                   # 日常集成分支
feature/chat-ui
feature/orchestrator
feature/agent-adapter
feature/diff-preview
feature/workspace
docs/spec
```

提交信息：

```txt
feat: 新功能
fix: 修复问题
docs: 文档修改
style: 样式调整
refactor: 重构
test: 测试
chore: 工程配置
```

Codex 不应自动执行 `git push`，除非用户明确要求。

## 11. 测试与验证

每次完成任务后，必须给出：

1. 修改文件列表；
2. 核心实现说明；
3. 本地启动方式；
4. 测试方式；
5. 已知风险；
6. 是否需要更新文档。

最低验证标准：

```bash
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m mypy agenthub
```

如果项目使用 `uv`，可使用：

```bash
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy agenthub
uv run uvicorn agenthub.api.main:app --reload
```

如果项目当前没有这些脚本或工具，应说明缺失情况，并建议补充。

## 12. 安全规则

1. 不得暴露 API Key；
2. 不得提交 `.env`；
3. 必须提供 `.env.example`；
4. 后端代理真实 Agent 调用，前端或 UI 不直接请求敏感 API；
5. 日志不得输出密钥、Token、个人隐私信息；
6. 文件操作必须限制在 workspace 内；
7. 执行 Git 或 shell 命令前必须说明用途；
8. `subprocess` 必须使用参数列表，不得拼接用户输入形成 shell 字符串；
9. 所有外部调用必须有 timeout；
10. 所有路径必须做越权检查。

## 13. 回复格式要求

Codex 完成任务后，必须按以下格式回复：

```md
## 完成情况

已完成：xxx

## 修改文件

- `path/to/file.py`：修改说明
- `path/to/test_file.py`：测试说明

## 核心逻辑

简要说明实现方式。

## 如何验证

1. xxx
2. xxx

## 风险与后续

- 风险：xxx
- 后续：xxx
```

## 14. 优先级原则

当任务发生冲突时，按以下优先级判断：

1. Demo 主线稳定性；
2. 功能可运行；
3. 架构清晰；
4. UI 体验；
5. 代码优雅；
6. 扩展能力。

不要为了追求“架构完整”而牺牲 Demo 可运行性。
