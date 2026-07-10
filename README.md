# AgentHub

AgentHub 是一个 **IM 聊天式多 Agent 协作平台**。用户像使用飞书/微信一样创建会话、选择 Agent、发送消息，并通过 `@Agent` 让多个 AI Agent 在同一个会话中协作完成开发任务。

当前项目重点服务一条稳定可演示的端到端主链路：

```txt
用户提出开发需求
-> Orchestrator 理解并拆解任务
-> Code / Review / Preview 等 Agent 分工输出
-> 聊天流展示 Markdown、code、diff、preview 等 artifact
-> 用户点击 Apply Diff 确认写入真实 workspace
-> Workspace Preview 打开当前代码入口
-> 用户继续迭代或 Revert 回退
-> 聊天历史保留完整协作过程
```

## 当前状态

AgentHub 已从早期 Mock Demo 演进为 React + FastAPI 的可运行 MVP，包含基于 LangChain 的真实 LLM 调用、流式消息、多 Agent 调度、workspace diff/preview、自建 Agent、Codex/Claude Code CLI 接入和 IM 核心操作。

## 核心能力

### IM 聊天体验

- 会话创建、切换、搜索、置顶、归档/恢复、删除。
- 会话成员管理，支持内置 Agent、Codex、Claude Code 和自建 Agent。
- 消息引用、复制、软删除、重新生成、pin/unpin 长期上下文。
- SSE 流式输出，用户消息立即出现，Agent 回复以 draft 气泡逐段更新。
- 运行状态按 `conversationId` 隔离，切换会话不会污染其他会话。

### 多 Agent 协作

- 无 `@` 默认进入 Orchestrator 智能入口。
- 显式 `@Agent` 优先调用目标 Agent。
- Orchestrator 优先调用真实 LLM 生成 `OrchestratorDecision`。
- 开发任务进入 `plan -> run -> verify -> retry/fail` harness。
- 内置开发链路默认调度：
  - `Code Agent`：生成代码和 diff artifact。
  - `Review Agent`：检查风险、功能完整性和改进点。
  - `Preview Agent`：验证 workspace preview 状态和入口。

### Agent 后端与自建 Agent

- LangChain `ChatOpenAI` 真实 LLM 后端，支持 OpenAI-compatible base URL，统一由后端代理调用。
- Mock 模式用于测试和离线演示，前端会显示明显提醒。
- Codex 和 Claude Code 作为独立内置 Agent 接入。
- 自建 Agent 支持：
  - 名称、描述、能力标签。
  - 系统提示词 `system_prompt`。
  - 启用/禁用、删除、测试。
  - 后端选择：LangChain/OpenAI-compatible、Codex、Claude Code。

### Workspace、Diff 与 Preview

- 每个会话绑定一个 workspace。
- Agent 先返回结构化 artifact，不直接写入真实 workspace。
- 用户点击 Apply Diff 后，后端将 diff 写入真实文件。
- Applied Diff 记录 before/after 快照，支持 Revert 回退。
- Preview 支持 `preview-page?path=...`，Apply Diff 后返回真实 `preview_url` 和 `entry_path`。
- 嵌套 HTML 页面会按入口目录注入资源 base，保证 CSS/JS 相对路径可加载。

### AI 协作沉淀

- `AGENTS.md`：仓库级 AI Coding 指令。
- `PROMPT_LOG.md`：Prompt、Skill、自建 Skill 和开发复盘。
- `docs/ai-rules.md`：AI 协作详细规则。
- `CODEX_REVIEW_CHECKLIST.md`：AI 生成代码 Review 清单。
- `DECISION_LOG.md`：关键架构决策记录。

## 技术栈

| 层级 | 技术 |
| --- | --- |
| 后端 | Python 3.11+、FastAPI、Pydantic v2 |
| 配置 | pydantic-settings、`.env` |
| 数据 | SQLite + SQLModel；测试可用 memory repository |
| Agent 调用 | LangChain、langchain-openai、OpenAI-compatible Chat Completions |
| CLI Agent | Codex CLI、Claude Code CLI、`asyncio.create_subprocess_exec` |
| Workspace | pathlib、统一路径安全校验、diff apply/revert |
| 测试 | pytest、pytest-asyncio |
| 质量 | ruff、mypy strict |
| 前端 | React、Vite、TypeScript、Ant Design |
| Markdown | react-markdown、remark-gfm、rehype-sanitize |

## 目录结构

```txt
agenthub/
  main.py                         FastAPI app 入口
  config.py                       环境变量配置
  api/                            FastAPI routes
  services/                       会话、消息、Agent、workspace 业务逻辑
  repositories/                   memory / SQLite 数据访问
  models/                         SQLModel 数据表
  schemas/                        Pydantic API/领域模型
  agents/                         Agent Adapter 与具体 Agent
  orchestrator/                   路由、计划模型、harness 模型
  workspace/                      路径安全、diff、preview、git helper
  core/                           统一业务错误

frontend/
  src/
    App.tsx                       前端主状态和核心流程
    api/client.ts                 FastAPI/SSE 客户端
    types/api.ts                  前端类型
    components/chat/              聊天流、输入框、Markdown、artifact 操作
    components/conversations/     会话列表、新建会话、成员管理
    components/agents/            Agent 列表、自建 Agent 管理
    components/workspace/         Workspace 面板
    components/artifactCards/     Artifact 卡片

tests/                            pytest 测试
docs/                             产品、技术、Prompt 和 Demo 文档
workspaces/                       运行时 workspace 根目录
```

## 快速启动

### 1. 安装后端依赖

```bash
python -m pip install -e ".[dev]"
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

至少需要关注：

```txt
PERSISTENCE_BACKEND=sqlite
DATABASE_URL=sqlite:///./agenthub.db
WORKSPACE_ROOT=./workspaces
USE_MOCK_AGENTS=false

AGENT_PROVIDER=openai-compatible
AGENT_MODEL=deepseek-v4-flash
AGENT_BASE_URL=https://api.deepseek.com
AGENT_THINKING=disabled
OPENAI_API_KEY=

CODEX_CLI_PATH=codex
CLAUDE_CODE_CLI_PATH=claude
CODE_AGENT_BACKEND_ID=openai-compatible
```

说明：

- 不要提交真实 `.env`。
- 真实 Agent 调用由 LangChain `ChatOpenAI` 驱动，`AGENT_BASE_URL` 填 OpenAI-compatible base URL，不要手动加 `/chat/completions`。
- 如果没有真实 API Key，可以设置 `USE_MOCK_AGENTS=true` 做离线演示。
- `AGENT_ALLOW_FALLBACKS=false` 时，真实模式不会用本地规则或硬编码产物替代模型失败。
- Codex/Claude Code CLI 后端需要本机安装对应命令。

### 3. 启动后端

```bash
python -m uvicorn agenthub.main:app --reload --host 127.0.0.1 --port 8000
```

健康检查：

```bash
curl http://127.0.0.1:8000/health
```

期望返回：

```json
{"status":"ok","service":"agenthub"}
```

### 4. 启动前端

```bash
cd frontend
npm install
npm run dev
```

前端默认连接：

```txt
http://127.0.0.1:8000
```

如需修改后端地址，可设置：

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000
```

## 常用 API

### Conversations

- `GET /api/conversations?status=active|archived|all`
- `POST /api/conversations`
- `GET /api/conversations/{id}`
- `PATCH /api/conversations/{id}`
- `DELETE /api/conversations/{id}`

### Messages

- `GET /api/conversations/{conversation_id}/messages`
- `POST /api/conversations/{conversation_id}/messages`
- `POST /api/conversations/{conversation_id}/messages/run`
- `POST /api/conversations/{conversation_id}/messages/stream`
- `DELETE /api/conversations/{conversation_id}/messages/{message_id}`
- `POST|DELETE /api/conversations/{conversation_id}/messages/{message_id}/pin-context`
- `POST /api/conversations/{conversation_id}/messages/{message_id}/regenerate/stream`

### Agents

- `GET /api/agents`
- `GET /api/agents/runtime`
- `GET /api/agents/backends`
- `POST /api/agents/run`
- `POST /api/agents/stream`
- `GET /api/agents/custom`
- `POST /api/agents/custom`
- `PATCH /api/agents/custom/{agent_id}`
- `DELETE /api/agents/custom/{agent_id}`
- `POST /api/agents/custom/{agent_id}/test`

### Workspaces

- `GET /api/workspaces/{workspace_id}/files`
- `GET /api/workspaces/{workspace_id}/files/content?path=...`
- `DELETE /api/workspaces/{workspace_id}/files?path=...`
- `GET /api/workspaces/{workspace_id}/preview`
- `GET /api/workspaces/{workspace_id}/preview-page?path=...`
- `GET /api/workspaces/{workspace_id}/preview-assets/{path}`
- `POST /api/workspaces/{workspace_id}/apply-diff`
- `GET /api/workspaces/{workspace_id}/applied-diffs`
- `POST /api/workspaces/{workspace_id}/applied-diffs/{record_id}/revert`

## SSE 事件协议

`/messages/stream` 和 regenerate stream 使用固定事件名：

```txt
user_message
harness_step
agent_started
agent_delta
artifact
agent_done
error
done
```

前端依赖这些事件维护流式 draft、artifact 增量展示和最终消息替换，因此修改事件名会破坏主链路。

## Demo 脚本

### 开发任务主链路

1. 新建会话：`Todo App Development`。
2. 选择 Orchestrator、Code Agent、Review Agent、Preview Agent。
3. 发送：

   ```txt
   @Orchestrator 帮我做一个简洁的 Todo List 网页，支持新增、完成、删除和筛选。
   ```

4. 观察 Orchestrator 任务拆解和多 Agent 流式回复。
5. 在 Code Agent 的 diff artifact 上点击 Apply Diff。
6. 在右侧 Workspace 打开 Preview。
7. 点击 Revert 验证可以回退。

### 自建 Agent

1. 打开“管理 Agent”。
2. 新建 Agent：

   ```txt
   名称：需求澄清 Agent
   描述：帮助用户把模糊需求拆成可执行问题
   能力标签：clarify, product
   系统提示词：你是 AgentHub 的需求澄清 Agent。你不直接写代码，而是把用户需求整理成 3 个关键问题。
   ```

3. 测试 Agent。
4. 启用并加入当前会话。
5. 发送：

   ```txt
   @需求澄清Agent 我想做一个学生成绩管理页面
   ```

### Codex / Claude Code

1. 确认本机已安装 `codex` 或 `claude` 命令。
2. 在会话成员中加入 Codex 或 Claude Code。
3. 发送：

   ```txt
   @Codex 帮我检查当前 workspace，并做一个很小的代码修改。
   ```

CLI Agent 会在临时 workspace 副本中执行，真实 workspace 仍需用户 Apply Diff 后才会写入。

## 验证命令

后端：

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check agenthub tests scripts
.venv/bin/python -m ruff format --check agenthub tests scripts
.venv/bin/python -m mypy agenthub
```

前端：

```bash
cd frontend
npm run build
```

真实 Agent smoke：

```bash
.venv/bin/python scripts/verify_real_agent_tasks.py
```

## 文档

- `docs/product-spec.md`：产品设计文档。
- `docs/tech-design.md`：技术设计文档。
- `docs/demo-script.md`：演示脚本。
- `docs/prompt-log.md`：AI 协作开发记录。
- `docs/ai-rules.md`：AI 协作规则。
- `PROMPT_LOG.md`：Prompt、Skill、自建 Skill 和问题复盘。
- `AGENTS.md`：仓库级 AI Coding 指令。
- `CODEX_REVIEW_CHECKLIST.md`：AI 生成代码 Review 清单。
- `DECISION_LOG.md`：关键架构决策。


## 开发约定

- 优先保持 Demo 主线稳定。
- 修改前阅读 `AGENTS.md`。
- 不提交 `.env` 或真实密钥。
- 后端业务逻辑放在 service 层。
- 所有 Agent 调用必须走统一 Adapter。
- workspace 路径必须做越权检查。
- 重要 Prompt 和 AI 协作经验记录到 `PROMPT_LOG.md` 或 `docs/prompt-log.md`。
