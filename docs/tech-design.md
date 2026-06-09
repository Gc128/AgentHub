# AgentHub Technical Design

## 架构概览

AgentHub 当前默认链路是 React 前端 + FastAPI 后端 + SQLite/memory repository + OpenAI-compatible Agent Adapter。前端只负责 UI、输入、SSE 消费和 artifact 操作；后端负责会话、消息、Agent 调度、workspace 文件、diff 应用与 preview 路由。

核心后端模块：

- `agenthub/api/*`：FastAPI route，保持薄接口层。
- `agenthub/services/*`：会话、消息、Agent、workspace 业务逻辑。
- `agenthub/repositories/*`：memory 与 SQLite 数据访问。
- `agenthub/agents/*`：Agent Adapter、真实 LLM、Mock、自建 Agent adapter。
- `agenthub/orchestrator/*`：路由、决策模型、harness 校验。
- `agenthub/workspace/*`：路径安全、diff、preview 页面和静态资源。

## API 合约

会话 API：

- `GET /api/conversations?status=active|archived|all`
- `POST /api/conversations`
- `GET /api/conversations/{id}`
- `PATCH /api/conversations/{id}`
- `DELETE /api/conversations/{id}`

消息 API：

- `GET /api/conversations/{conversation_id}/messages`
- `POST /api/conversations/{conversation_id}/messages`
- `POST /api/conversations/{conversation_id}/messages/run`
- `POST /api/conversations/{conversation_id}/messages/stream`
- `DELETE /api/conversations/{conversation_id}/messages/{message_id}`
- `POST|DELETE /api/conversations/{conversation_id}/messages/{message_id}/pin-context`
- `POST /api/conversations/{conversation_id}/messages/{message_id}/regenerate/stream`

Agent API：

- `GET /api/agents`：返回内置 Agent 和启用中的自建 Agent。
- `GET /api/agents/runtime`：返回 provider/model/base_url_host/api_key_configured，不返回密钥。
- `POST /api/agents/run`、`POST /api/agents/stream`：调试和直接运行 Agent。
- `GET /api/agents/custom`
- `POST /api/agents/custom`
- `PATCH /api/agents/custom/{agent_id}`
- `DELETE /api/agents/custom/{agent_id}`
- `POST /api/agents/custom/{agent_id}/test`

Workspace API：

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

- `user_message`：用户消息已保存。
- `harness_step`：Orchestrator 或单 Agent 当前阶段。
- `agent_started`：前端创建 Agent 草稿气泡。
- `agent_delta`：追加可见文本增量。
- `artifact`：发送结构化 artifact。
- `agent_done`：后端已落盘最终 Agent message，前端替换草稿。
- `error`：可读错误。
- `done`：本次运行结束。

前端按 `conversationId` 隔离运行状态、draft、消息缓存和生成提示，避免切换会话时互相污染。

## 数据模型

`Conversation` 增加 `status=active|archived`，归档只影响列表可见性，不删除消息或 workspace。

`Message` 支持 `reply_to_id`、`regenerated_from_id`、`is_context_pinned`、`deleted_at`。软删除消息保留时间线位置，清空 artifacts，并从 Agent history 中过滤；pinned 消息通过 `context.pinned_messages` 注入 Agent 输入。

`CustomAgent` 字段：

- `id`：后端生成，`custom-agent_*` 前缀。
- `name`、`description`
- `system_prompt`：自建 Agent 的角色提示词，必填。
- `capabilities`
- `is_enabled`
- `created_at`、`updated_at`

SQLite 对自建 Agent 使用独立 `customagentrecord` 表，不改动 workspace/diff/preview 既有表。

## Agent Adapter

业务层只依赖 `AgentRunInput` 和 `AgentRunResult`，不直接耦合供应商 SDK。当前 Adapter：

- `RealAgent`：OpenAI-compatible HTTP 调用、timeout、stream、结构化解析和 repair。
- `MockAgent`：离线测试和 demo 的确定性输出。
- `CodeAgent`、`ReviewAgent`、`PreviewAgent`：包装 `RealAgent` 并补充角色校验。
- `OrchestratorAdapter`：调用 LLM 生成 `OrchestratorDecision`。
- `CustomAgentAdapter`：读取自建 Agent 的 `system_prompt`；真实模式下请求文本，Mock 模式下返回可识别回复。

内置 Orchestrator 自动开发计划仍只调度 `code-agent`、`review-agent`、`preview-agent`。自建 Agent 仅在用户显式 `@名称` 或 `context.agent_id` 指定时运行。

## Orchestrator Harness

开发任务执行流程：

```txt
Orchestrator decision -> plan message -> run step -> verify artifacts -> retry once -> continue/fail
```

默认校验：

- Code Agent 必须返回 code/diff。
- Review Agent 必须返回 review/risk 类产物或可读 findings。
- Preview Agent 必须返回 preview artifact/status。

Schema 失败不会直接裸露 JSON 错误。真实 Agent 会尝试 repair、归一化常见 LLM 输出形状；最终失败时返回可读错误消息。

## Workspace 与 Preview

Workspace 文件操作全部限制在 `WORKSPACE_ROOT` 内。Apply Diff 写入真实文件，并记录 `AppliedDiffRecord`，包含 `artifact_id`、`path`、before/after 内容和 `reverted_at`。Revert Diff 使用记录中的 before 内容恢复。

Preview API 以 workspace 中的 HTML 入口为准，Apply Diff 会返回 `preview_url` 和 `entry_path`。`preview-page?path=...` 支持嵌套 HTML 文件，并按入口目录注入资源 base，保证工作区预览与代码 artifact 对应。

## 前端实现

React 前端维护：

- `messagesByConversationId`
- `agentRunningByConversationId`
- `generationNoticeByConversationId`
- 当前 workspace preview/files/applied diff 状态
- 自建 Agent 管理弹窗状态

消息输入支持当前会话成员范围内的 `@` 菜单；自建 Agent 启用并加入会话后，会出现在成员选择和 `@` 菜单中。自建 Agent 管理弹窗支持创建、编辑、启用/禁用、删除和测试调用。

## 配置与验证

默认真实模型配置来自 `.env`：

- `USE_MOCK_AGENTS`
- `AGENT_PROVIDER`
- `AGENT_MODEL`
- `AGENT_BASE_URL`
- `OPENAI_API_KEY`
- `AGENT_RESPONSE_FORMAT`
- `AGENT_ALLOW_FALLBACKS`

前端默认连接 `http://127.0.0.1:8000`。如果连接 Mock 后端，UI 会显示明显提醒。

常规验证命令：

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check agenthub tests scripts
.venv/bin/python -m ruff format --check agenthub tests scripts
.venv/bin/python -m mypy agenthub
cd frontend && npm run build
```
