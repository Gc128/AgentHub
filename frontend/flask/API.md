# AgentHub Flask API 文档

本服务位于 `frontend/flask/main.py`，默认运行在 `http://127.0.0.1:5001`。

启动方式：

```bash
python frontend/flask/main.py
```

前端默认读取 `VITE_API_BASE_URL`，未配置时调用 `http://127.0.0.1:5001`。

## 统一响应

所有接口都返回统一 JSON：

```json
{
  "success": true,
  "data": {},
  "error": null
}
```

失败时：

```json
{
  "success": false,
  "data": null,
  "error": "错误信息"
}
```

## 数据表

JSON 表位于 `frontend/flask/data/`：

- `users.json`：用户表
- `agents.json`：Agent 联系人表
- `conversations.json`：会话表
- `messages.json`：消息表
- `previews.json`：workspace 预览状态表
- `workspace_files.json`：workspace 文件表
- `applied_diffs.json`：已应用 Diff 记录表

## 会话接口

### GET `/api/conversations`

获取会话列表。后端按置顶优先、最近更新时间倒序返回。

### POST `/api/conversations`

创建会话。

请求体：

```json
{
  "title": "Todo App Development",
  "agent_ids": ["orchestrator", "code-agent"],
  "is_pinned": false
}
```

说明：`mode` 由 `agent_ids` 数量自动推导，一个 Agent 是 `single`，多个 Agent 是 `group`。

### GET `/api/conversations/<conversation_id>`

获取单个会话详情。

### PATCH `/api/conversations/<conversation_id>`

更新会话标题、成员或置顶状态。

请求体示例：

```json
{
  "agent_ids": ["orchestrator", "review-agent"],
  "is_pinned": true
}
```

说明：更新成员时至少保留一个 Agent。

### DELETE `/api/conversations/<conversation_id>`

删除会话，并同步删除该会话消息和预览状态。

返回：

```json
{
  "id": "conv_001",
  "deleted": true
}
```

## 消息接口

### GET `/api/conversations/<conversation_id>/messages`

获取某个会话的消息列表。

### POST `/api/conversations/<conversation_id>/messages`

创建消息。

请求体：

```json
{
  "sender_id": "user",
  "content": "@Orchestrator 帮我做一个 Todo List",
  "artifacts": []
}
```

### GET `/api/messages/<conversation_id>`

兼容接口，等价于 `GET /api/conversations/<conversation_id>/messages`。

### POST `/api/messages`

兼容接口。请求体必须包含 `conversation_id`。

```json
{
  "conversation_id": "conv_001",
  "sender_id": "user",
  "content": "继续优化页面"
}
```

## Agent 接口

### GET `/api/agents`

获取 Agent 联系人列表。

### POST `/api/agents/run`

调用当前会话内的 Agent。

请求体：

```json
{
  "conversation_id": "conv_001",
  "workspace_id": "ws_001",
  "user_message": "@CodeAgent 生成页面",
  "history": [],
  "context": {
    "agent_id": "code-agent"
  }
}
```

说明：后端会校验 `context.agent_id` 是否属于当前会话 `agent_ids`，不属于则返回 403。

## Workspace 接口

### GET `/api/workspaces/<workspace_id>/preview`

获取 workspace 预览状态。

### POST `/api/workspaces/<workspace_id>/apply-diff`

应用 Diff，并把 preview 状态更新为 `ready`。

请求体：

```json
{
  "artifact_id": "artifact_diff_001",
  "diff": "--- a/src/App.tsx\n+++ b/src/App.tsx\n..."
}
```

### GET `/api/workspaces/<workspace_id>/files`

获取 workspace 文件列表。

### GET `/api/workspaces/<workspace_id>/files/content?path=src/App.tsx`

获取某个文件内容。

### POST `/api/workspaces/<workspace_id>/files`

写入或更新文件。

请求体：

```json
{
  "path": "src/App.tsx",
  "content": "export default function App() { return null }"
}
```
