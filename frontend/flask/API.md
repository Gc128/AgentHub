# AgentHub Flask API 文档

本服务位于 `frontend/flask/main.py`，默认运行在 `http://127.0.0.1:5001`。

启动方式：

```bash
python frontend/flask/main.py
```

前端默认读取 `VITE_API_BASE_URL`，未配置时调用 `http://127.0.0.1:5001`。

## 1. 通用约定

### 1.1 请求约定

- 除 GET 接口外，接口请求体均使用 JSON。
- 建议请求头携带 `Content-Type: application/json`。
- 路径中的 `<conversation_id>`、`<workspace_id>` 都是字符串 id。

### 1.2 统一响应结构

所有接口都会返回统一 JSON envelope。

成功响应：

```json
{
  "success": true,
  "data": {},
  "error": null
}
```

失败响应：

```json
{
  "success": false,
  "data": null,
  "error": "错误信息"
}
```

字段说明：

| 字段 | 类型 | 必返 | 含义 |
|---|---|---|---|
| `success` | `boolean` | 是 | 请求是否成功。成功为 `true`，失败为 `false`。 |
| `data` | `unknown \| null` | 是 | 成功时为业务数据；失败时为 `null`。 |
| `error` | `string \| null` | 是 | 失败时为可读错误信息；成功时为 `null`。 |

常见错误状态：

| HTTP 状态码 | 含义 |
|---|---|
| `400` | 请求字段缺失、为空或格式不符合要求。 |
| `403` | 当前会话不允许调用目标 Agent。 |
| `404` | 会话、消息所属会话或 workspace 文件不存在。 |

## 2. 数据表

JSON 表位于 `frontend/flask/data/`。

| 文件 | 含义 |
|---|---|
| `users.json` | 用户表。 |
| `agents.json` | Agent 联系人表。 |
| `conversations.json` | 会话表。 |
| `messages.json` | 消息表。 |
| `previews.json` | workspace 预览状态表。 |
| `workspace_files.json` | workspace 文件表。 |
| `applied_diffs.json` | 已应用 Diff 记录表。 |

## 3. 公共返回模型

下面的模型会在多个接口中作为 `data` 或 `data[]` 返回。

### 3.1 User

| 字段 | 类型 | 必返 | 含义 |
|---|---|---|---|
| `id` | `string` | 是 | 用户 id。当前 Demo 用户固定为 `user`。 |
| `name` | `string` | 是 | 用户展示名称。 |
| `created_at` | `string` | 是 | 用户创建时间，UTC ISO 字符串。 |

### 3.2 Agent

| 字段 | 类型 | 必返 | 含义 |
|---|---|---|---|
| `id` | `string` | 是 | Agent 稳定 id，例如 `orchestrator`、`code-agent`。 |
| `name` | `string` | 是 | Agent 展示名称。 |
| `role` | `string` | 是 | Agent 角色，可选值：`orchestrator`、`code`、`review`、`preview`、`custom`。 |
| `description` | `string` | 是 | Agent 能力简介。 |
| `capabilities` | `string[]` | 是 | 能力标签数组，用于前端 Badge 和后续调度。 |
| `adapter_type` | `string` | 是 | Agent 适配器类型，可选值：`mock`、`codex`、`claude`、`opencode`、`custom`。当前 Flask 本地规则 Agent 使用 `custom`。 |

### 3.3 Conversation

| 字段 | 类型 | 必返 | 含义 |
|---|---|---|---|
| `id` | `string` | 是 | 会话 id。 |
| `title` | `string` | 是 | 会话标题。 |
| `mode` | `"single" \| "group"` | 是 | 会话模式。一个 Agent 为 `single`，多个 Agent 为 `group`。 |
| `agent_ids` | `string[]` | 是 | 当前会话包含的 Agent id 列表。 |
| `is_pinned` | `boolean` | 是 | 是否置顶。 |
| `workspace_id` | `string` | 是 | 会话绑定的 workspace id。 |
| `created_at` | `string` | 是 | 会话创建时间，UTC ISO 字符串。 |
| `updated_at` | `string` | 是 | 会话最近更新时间，UTC ISO 字符串。 |

### 3.4 Artifact

| 字段 | 类型 | 必返 | 含义 |
|---|---|---|---|
| `id` | `string` | 是 | Artifact id。Apply Diff 时会用到 diff artifact 的 id。 |
| `type` | `string` | 是 | Artifact 类型，可选值：`code`、`diff`、`preview`、`file`、`deploy`。 |
| `title` | `string` | 是 | Artifact 卡片标题。 |
| `data` | `object` | 是 | Artifact 载荷，不同 `type` 的字段不同。 |
| `created_at` | `string` | 是 | Artifact 创建时间，UTC ISO 字符串。 |

Artifact `data` 常见结构：

| Artifact 类型 | `data` 字段 | 类型 | 必返 | 含义 |
|---|---|---|---|---|
| `code` | `filename` | `string` | 是 | 代码文件路径，例如 `src/App.tsx`。 |
| `code` | `language` | `string` | 是 | 代码语言，例如 `tsx`。 |
| `code` | `content` | `string` | 是 | 代码内容。 |
| `diff` | `filename` | `string` | 是 | Diff 对应文件路径。 |
| `diff` | `diff` | `string` | 是 | unified diff 字符串。 |
| `preview` | `workspace_id` | `string` | 是 | 预览所属 workspace id。 |
| `preview` | `status` | `string` | 是 | 预览状态：`not_started`、`running`、`ready`、`error`。 |
| `preview` | `checked_at` | `string` | 否 | Preview Agent 检查时间。 |
| `file` | `summary` | `string` | 否 | 文件型 Artifact 的摘要。 |
| `file` | `steps` | `string[]` | 否 | Orchestrator 任务拆解步骤。 |
| `file` | `findings` | `string[]` | 否 | Review Agent 检查项。 |
| `file` | `risk_level` | `string` | 否 | Review Agent 风险级别，例如 `low`、`medium`。 |

### 3.5 Message

| 字段 | 类型 | 必返 | 含义 |
|---|---|---|---|
| `id` | `string` | 是 | 消息 id。 |
| `conversation_id` | `string` | 是 | 消息所属会话 id。 |
| `role` | `"user" \| "agent" \| "system"` | 是 | 消息角色。当前 Flask 写消息时，`sender_id=user` 会生成 `user`，其他发送者生成 `agent`。 |
| `sender_id` | `string` | 是 | 发送者 id。用户为 `user`，Agent 消息为 Agent id。 |
| `content` | `string` | 是 | 消息正文。 |
| `artifacts` | `Artifact[]` | 是 | 消息携带的结构化产物数组。 |
| `created_at` | `string` | 是 | 消息创建时间，UTC ISO 字符串。 |

### 3.6 Preview

| 字段 | 类型 | 必返 | 含义 |
|---|---|---|---|
| `workspace_id` | `string` | 是 | workspace id。 |
| `status` | `"not_started" \| "running" \| "ready" \| "error"` | 是 | 预览状态。 |

### 3.7 WorkspaceFile

| 字段 | 类型 | 必返 | 含义 |
|---|---|---|---|
| `workspace_id` | `string` | 是 | 文件所属 workspace id。 |
| `path` | `string` | 是 | workspace 内相对路径。 |
| `content` | `string` | 是 | 文件内容。 |
| `updated_at` | `string` | 是 | 文件最近更新时间，UTC ISO 字符串。 |

### 3.8 AgentRunResult

| 字段 | 类型 | 必返 | 含义 |
|---|---|---|---|
| `agent_id` | `string` | 是 | 实际响应的 Agent id。 |
| `content` | `string` | 是 | Agent 自然语言回复内容。 |
| `artifacts` | `Artifact[]` | 是 | Agent 生成的结构化产物。 |
| `next_actions` | `string[]` | 是 | 建议后续动作，例如 `review`、`preview`。 |

## 4. 基础接口

### 4.1 GET `/health`

用途：健康检查，确认 Flask 服务已经启动。

请求字段：无。

成功响应：

| 项 | 值 |
|---|---|
| HTTP 状态码 | `200` |
| `data` 类型 | `object` |

`data` 字段：

| 字段 | 类型 | 必返 | 含义 |
|---|---|---|---|
| `status` | `string` | 是 | 服务状态。当前固定返回 `ok`。 |

示例：

```json
{
  "success": true,
  "data": {
    "status": "ok"
  },
  "error": null
}
```

### 4.2 GET `/api/users`

用途：获取用户列表。当前 MVP 只有一个 Demo User。

请求字段：无。

成功响应：

| 项 | 值 |
|---|---|
| HTTP 状态码 | `200` |
| `data` 类型 | `User[]` |

`data[]` 字段见 [3.1 User](#31-user)。

## 5. Agent 接口

### 5.1 GET `/api/agents`

用途：获取 Agent 联系人列表，用于左侧 Agent 列表、新建会话选择、输入框 @ 菜单。

请求字段：无。

成功响应：

| 项 | 值 |
|---|---|
| HTTP 状态码 | `200` |
| `data` 类型 | `Agent[]` |

`data[]` 字段见 [3.2 Agent](#32-agent)。

### 5.2 POST `/api/agents/run`

用途：调用当前会话内的 Agent，并返回 AgentRunResult。

请求 Body 字段：

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `conversation_id` | `string` | 是 | 当前会话 id。后端会用它查找会话，不存在返回 `404`。 |
| `workspace_id` | `string` | 是 | 当前会话绑定的 workspace id。Preview Agent 和 preview artifact 依赖该字段。 |
| `user_message` | `string` | 是 | 用户输入的原始消息，例如 `@CodeAgent 生成页面`。 |
| `history` | `Message[]` | 否 | 当前会话历史消息。当前 Flask 规则 Agent 暂未使用，但保留给真实 Agent 接入。 |
| `context` | `object` | 否 | 可扩展上下文。当前只读取 `context.agent_id`。 |
| `context.agent_id` | `string` | 否 | 要调用的 Agent id。未传时默认 `orchestrator`。如果该 Agent 不属于当前会话 `agent_ids`，返回 `403`。 |

请求示例：

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

成功响应：

| 项 | 值 |
|---|---|
| HTTP 状态码 | `200` |
| `data` 类型 | `AgentRunResult` |

`data` 字段见 [3.8 AgentRunResult](#38-agentrunresult)。

可能返回的 Artifact：

| Agent | Artifact 类型 | 说明 |
|---|---|---|
| `orchestrator` | `file` | 任务拆解步骤。 |
| `code-agent` | `code`、`diff` | 代码内容和 unified diff。 |
| `review-agent` | `file` | Review 检查项和风险等级。 |
| `preview-agent` | `preview` | workspace 预览状态。 |

错误响应：

| HTTP 状态码 | 触发条件 |
|---|---|
| `404` | `conversation_id` 不存在。 |
| `403` | `context.agent_id` 不在当前会话的 `agent_ids` 中。 |

## 6. 会话接口

### 6.1 GET `/api/conversations`

用途：获取会话列表。

请求字段：无。

排序说明：当前实现先按 `is_pinned=true` 置顶，再按 `updated_at` ISO 字符串排序。

成功响应：

| 项 | 值 |
|---|---|
| HTTP 状态码 | `200` |
| `data` 类型 | `Conversation[]` |

`data[]` 字段见 [3.3 Conversation](#33-conversation)。

### 6.2 POST `/api/conversations`

用途：创建会话，并初始化该会话 workspace 的 preview 状态为 `not_started`。

请求 Body 字段：

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `title` | `string` | 是 | 会话标题。不能为空字符串。 |
| `agent_ids` | `string[]` | 是 | 会话包含的 Agent id 列表。必须至少包含一个 Agent。 |
| `is_pinned` | `boolean` | 否 | 是否创建后立即置顶。未传时默认为 `false`。 |

请求示例：

```json
{
  "title": "Todo App Development",
  "agent_ids": ["orchestrator", "code-agent"],
  "is_pinned": false
}
```

成功响应：

| 项 | 值 |
|---|---|
| HTTP 状态码 | `201` |
| `data` 类型 | `Conversation` |

`data` 字段见 [3.3 Conversation](#33-conversation)。

补充规则：

- `mode` 不需要前端传入，后端会根据 `agent_ids` 自动推导。
- 一个 Agent 时 `mode=single`，多个 Agent 时 `mode=group`。
- `workspace_id`、`created_at`、`updated_at` 由后端生成。

错误响应：

| HTTP 状态码 | 触发条件 |
|---|---|
| `400` | `title` 为空。 |
| `400` | `agent_ids` 不是数组或为空数组。 |

### 6.3 GET `/api/conversations/<conversation_id>`

用途：获取单个会话详情。

路径字段：

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `conversation_id` | `string` | 是 | 要查询的会话 id。 |

成功响应：

| 项 | 值 |
|---|---|
| HTTP 状态码 | `200` |
| `data` 类型 | `Conversation` |

`data` 字段见 [3.3 Conversation](#33-conversation)。

错误响应：

| HTTP 状态码 | 触发条件 |
|---|---|
| `404` | `conversation_id` 不存在。 |

### 6.4 PATCH `/api/conversations/<conversation_id>`

用途：更新会话标题、成员、模式或置顶状态。

路径字段：

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `conversation_id` | `string` | 是 | 要更新的会话 id。 |

请求 Body 字段：

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `title` | `string` | 否 | 新会话标题。如果传入则不能为空字符串。 |
| `agent_ids` | `string[]` | 否 | 新的会话 Agent 成员列表。如果传入则必须至少包含一个 Agent，并会重新推导 `mode`。 |
| `mode` | `"single" \| "group"` | 否 | 会话模式。仅在未传 `agent_ids` 时生效。 |
| `is_pinned` | `boolean` | 否 | 是否置顶。 |

请求示例：

```json
{
  "agent_ids": ["orchestrator", "review-agent"],
  "is_pinned": true
}
```

成功响应：

| 项 | 值 |
|---|---|
| HTTP 状态码 | `200` |
| `data` 类型 | `Conversation` |

`data` 字段见 [3.3 Conversation](#33-conversation)。

补充规则：

- 每次 PATCH 都会刷新 `updated_at`。
- 如果同时传 `agent_ids` 和 `mode`，以 `agent_ids` 推导出的 `mode` 为准。

错误响应：

| HTTP 状态码 | 触发条件 |
|---|---|
| `404` | `conversation_id` 不存在。 |
| `400` | `title` 为空。 |
| `400` | `agent_ids` 不是数组或为空数组。 |

### 6.5 DELETE `/api/conversations/<conversation_id>`

用途：删除会话，并同步删除该会话消息和预览状态。

路径字段：

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `conversation_id` | `string` | 是 | 要删除的会话 id。 |

请求 Body 字段：无。

成功响应：

| 项 | 值 |
|---|---|
| HTTP 状态码 | `200` |
| `data` 类型 | `object` |

`data` 字段：

| 字段 | 类型 | 必返 | 含义 |
|---|---|---|---|
| `id` | `string` | 是 | 已删除的会话 id。 |
| `deleted` | `boolean` | 是 | 删除结果。成功时固定为 `true`。 |

示例：

```json
{
  "success": true,
  "data": {
    "id": "conv_001",
    "deleted": true
  },
  "error": null
}
```

错误响应：

| HTTP 状态码 | 触发条件 |
|---|---|
| `404` | `conversation_id` 不存在。 |

## 7. 消息接口

### 7.1 GET `/api/conversations/<conversation_id>/messages`

用途：获取某个会话的消息列表。

路径字段：

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `conversation_id` | `string` | 是 | 要查询消息的会话 id。 |

请求 Body 字段：无。

成功响应：

| 项 | 值 |
|---|---|
| HTTP 状态码 | `200` |
| `data` 类型 | `Message[]` |

`data[]` 字段见 [3.5 Message](#35-message)。

排序说明：消息按 `created_at` 升序返回。

错误响应：

| HTTP 状态码 | 触发条件 |
|---|---|
| `404` | `conversation_id` 不存在。 |

### 7.2 POST `/api/conversations/<conversation_id>/messages`

用途：向指定会话创建一条消息。

路径字段：

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `conversation_id` | `string` | 是 | 要写入消息的会话 id。 |

请求 Body 字段：

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `content` | `string` | 是 | 消息正文。不能为空字符串。 |
| `sender_id` | `string` | 否 | 发送者 id。未传时默认为 `user`。 |
| `artifacts` | `Artifact[]` | 否 | 消息携带的结构化产物。未传或不是数组时默认为空数组。 |

请求示例：

```json
{
  "sender_id": "user",
  "content": "@Orchestrator 帮我做一个 Todo List",
  "artifacts": []
}
```

成功响应：

| 项 | 值 |
|---|---|
| HTTP 状态码 | `201` |
| `data` 类型 | `Message` |

`data` 字段见 [3.5 Message](#35-message)。

补充规则：

- `sender_id=user` 时，后端生成的 `role` 为 `user`。
- `sender_id` 不是 `user` 时，后端生成的 `role` 为 `agent`。
- 创建消息会刷新所属会话的 `updated_at`。

错误响应：

| HTTP 状态码 | 触发条件 |
|---|---|
| `404` | `conversation_id` 不存在。 |
| `400` | `content` 为空。 |

### 7.3 GET `/api/messages/<conversation_id>`

用途：兼容接口，等价于 `GET /api/conversations/<conversation_id>/messages`。

路径字段：

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `conversation_id` | `string` | 是 | 要查询消息的会话 id。 |

成功响应：

| 项 | 值 |
|---|---|
| HTTP 状态码 | `200` |
| `data` 类型 | `Message[]` |

`data[]` 字段见 [3.5 Message](#35-message)。

错误响应同 [7.1](#71-get-apiconversationsconversation_idmessages)。

### 7.4 POST `/api/messages`

用途：兼容接口。通过请求体传入 `conversation_id` 创建消息。

请求 Body 字段：

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `conversation_id` | `string` | 是 | 要写入消息的会话 id。 |
| `content` | `string` | 是 | 消息正文。不能为空字符串。 |
| `sender_id` | `string` | 否 | 发送者 id。未传时默认为 `user`。 |
| `artifacts` | `Artifact[]` | 否 | 消息携带的结构化产物。未传或不是数组时默认为空数组。 |

请求示例：

```json
{
  "conversation_id": "conv_001",
  "sender_id": "user",
  "content": "继续优化页面",
  "artifacts": []
}
```

成功响应：

| 项 | 值 |
|---|---|
| HTTP 状态码 | `201` |
| `data` 类型 | `Message` |

`data` 字段见 [3.5 Message](#35-message)。

错误响应：

| HTTP 状态码 | 触发条件 |
|---|---|
| `400` | `conversation_id` 缺失或为空。 |
| `404` | `conversation_id` 不存在。 |
| `400` | `content` 为空。 |

## 8. Workspace 接口

### 8.1 GET `/api/workspaces/<workspace_id>/preview`

用途：获取 workspace 预览状态。

路径字段：

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `workspace_id` | `string` | 是 | 要查询预览状态的 workspace id。 |

请求 Body 字段：无。

成功响应：

| 项 | 值 |
|---|---|
| HTTP 状态码 | `200` |
| `data` 类型 | `Preview` |

`data` 字段见 [3.6 Preview](#36-preview)。

补充规则：如果 `previews.json` 中没有对应 workspace，后端会返回 `{ workspace_id, status: "not_started" }`，不会返回 404。

### 8.2 POST `/api/workspaces/<workspace_id>/apply-diff`

用途：应用 Diff，并把该 workspace 的 preview 状态更新为 `ready`。

路径字段：

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `workspace_id` | `string` | 是 | 要应用 Diff 的 workspace id。 |

请求 Body 字段：

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `artifact_id` | `string` | 是 | 要应用的 diff artifact id。不能为空字符串。 |
| `diff` | `string` | 是 | unified diff 字符串。不能为空字符串。 |

请求示例：

```json
{
  "artifact_id": "artifact_diff_001",
  "diff": "--- a/src/App.tsx\n+++ b/src/App.tsx\n..."
}
```

成功响应：

| 项 | 值 |
|---|---|
| HTTP 状态码 | `200` |
| `data` 类型 | `object` |

`data` 字段：

| 字段 | 类型 | 必返 | 含义 |
|---|---|---|---|
| `workspace_id` | `string` | 是 | 应用 Diff 的 workspace id。 |
| `status` | `"ready"` | 是 | 应用成功后的 preview 状态。当前固定返回 `ready`。 |
| `applied_artifact_id` | `string` | 是 | 已应用的 artifact id，对应请求体 `artifact_id`。 |
| `applied_at` | `string` | 是 | 应用时间，UTC ISO 字符串。 |

错误响应：

| HTTP 状态码 | 触发条件 |
|---|---|
| `400` | `artifact_id` 缺失或为空。 |
| `400` | `diff` 缺失或为空。 |

### 8.3 GET `/api/workspaces/<workspace_id>/files`

用途：获取 workspace 文件列表。

路径字段：

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `workspace_id` | `string` | 是 | 要查询文件列表的 workspace id。 |

请求 Body 字段：无。

成功响应：

| 项 | 值 |
|---|---|
| HTTP 状态码 | `200` |
| `data` 类型 | `object[]` |

`data[]` 字段：

| 字段 | 类型 | 必返 | 含义 |
|---|---|---|---|
| `path` | `string` | 是 | workspace 内相对路径。 |
| `updated_at` | `string \| null` | 是 | 文件最近更新时间；数据缺失时可能为 `null`。 |

补充规则：文件列表接口不返回 `content`，需要通过文件内容接口单独获取。

### 8.4 GET `/api/workspaces/<workspace_id>/files/content?path=<path>`

用途：获取 workspace 中某个文件的内容。

路径字段：

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `workspace_id` | `string` | 是 | 文件所属 workspace id。 |

Query 字段：

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `path` | `string` | 是 | workspace 内相对路径，例如 `src/App.tsx`。 |

请求示例：

```txt
GET /api/workspaces/ws_001/files/content?path=src/App.tsx
```

成功响应：

| 项 | 值 |
|---|---|
| HTTP 状态码 | `200` |
| `data` 类型 | `WorkspaceFile` |

`data` 字段见 [3.7 WorkspaceFile](#37-workspacefile)。

错误响应：

| HTTP 状态码 | 触发条件 |
|---|---|
| `404` | 指定 `workspace_id + path` 的文件不存在，或未传有效 `path`。 |

### 8.5 POST `/api/workspaces/<workspace_id>/files`

用途：新增或覆盖 workspace 文件。

路径字段：

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `workspace_id` | `string` | 是 | 要写入文件的 workspace id。 |

请求 Body 字段：

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `path` | `string` | 是 | workspace 内相对路径。不能为空字符串。 |
| `content` | `string` | 否 | 文件内容。未传时默认为空字符串。 |

请求示例：

```json
{
  "path": "src/App.tsx",
  "content": "export default function App() { return null }"
}
```

成功响应：

| 项 | 值 |
|---|---|
| HTTP 状态码 | `201` |
| `data` 类型 | `WorkspaceFile` |

`data` 字段见 [3.7 WorkspaceFile](#37-workspacefile)。

补充规则：同一个 `workspace_id + path` 已存在时覆盖原内容；不存在时新增文件记录。

错误响应：

| HTTP 状态码 | 触发条件 |
|---|---|
| `400` | `path` 缺失或为空。 |

## 9. 接口清单速览

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/health` | 健康检查。 |
| `GET` | `/api/users` | 获取用户列表。 |
| `GET` | `/api/agents` | 获取 Agent 列表。 |
| `POST` | `/api/agents/run` | 调用 Agent。 |
| `GET` | `/api/conversations` | 获取会话列表。 |
| `POST` | `/api/conversations` | 创建会话。 |
| `GET` | `/api/conversations/<conversation_id>` | 获取会话详情。 |
| `PATCH` | `/api/conversations/<conversation_id>` | 更新会话。 |
| `DELETE` | `/api/conversations/<conversation_id>` | 删除会话。 |
| `GET` | `/api/conversations/<conversation_id>/messages` | 获取会话消息。 |
| `POST` | `/api/conversations/<conversation_id>/messages` | 创建会话消息。 |
| `GET` | `/api/messages/<conversation_id>` | 获取消息列表兼容接口。 |
| `POST` | `/api/messages` | 创建消息兼容接口。 |
| `GET` | `/api/workspaces/<workspace_id>/preview` | 获取预览状态。 |
| `POST` | `/api/workspaces/<workspace_id>/apply-diff` | 应用 Diff。 |
| `GET` | `/api/workspaces/<workspace_id>/files` | 获取文件列表。 |
| `GET` | `/api/workspaces/<workspace_id>/files/content?path=<path>` | 获取文件内容。 |
| `POST` | `/api/workspaces/<workspace_id>/files` | 写入或更新文件。 |
