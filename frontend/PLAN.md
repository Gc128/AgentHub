# AgentHub 前端任务拆解

## 1. 项目与仓库理解

本次只做只读分析，不修改代码。目标是结合附件 1、附件 2 和当前仓库，拆解前端开发任务；预计修改文件为无；不应修改后端、schema、接口字段或目录结构；本次不影响 API 和数据模型；验证方式为阅读仓库、文档、前端结构和后端 schema/API。

项目目标是 IM 聊天式多 Agent 协作平台，核心 Demo 链路为：

用户提出开发需求 → Orchestrator 拆解任务 → Code/Review/Preview Agent 依次产出 → 展示代码、Diff、Preview Artifact → 用户 Apply Diff → 预览更新 → 聊天记录保留完整过程。

当前仓库情况：

- 后端：已有 FastAPI 基础入口 `agenthub/main.py`，已有 `/health`、`/api/conversations`、`/api/conversations/{conversation_id}/messages`、`/api/agents/run`、`/api/workspaces/{workspace_id}/preview` 的雏形。
- Schema：已有 `Conversation`、`Message`、`Agent`、`Artifact`、`AgentRunInput`、`AgentRunResult`，前端字段应优先对齐这些模型。
- Orchestrator：已有规则路由和任务计划基础，需要前端展示其过程。
- Mock Agent：已有 Code/Review/Mock Agent 基础，但接口仍不完整。
- 前端：`frontend/` 是 React + TypeScript + Vite 默认模板，仅有 `App.tsx`、`App.css`、`index.css`，没有路由、页面、组件体系、API 请求封装、mock 拦截或状态管理。结论：已有基础，需要完善的是工程壳；核心业务前端基本需要新建。

当前前端技术栈：

- React 18
- TypeScript
- Vite
- 无 UI 组件库
- 无路由库
- 无状态管理库
- 无请求库封装
- 无 mock 方案

## 2. 前端模块拆分

| 模块 | 目标 | 涉及页面/组件 | 接口 | Mock | 状态 | 优先级 |
|---|---|---|---|---|---|---|
| 应用主框架 | 搭建 IM 三栏工作台：会话列表、聊天区、Artifact/Preview 侧栏 | `AppLayout`、`Sidebar`、`ChatPanel`、`ArtifactPanel` | 无直接接口 | 不需要 | 需要新建 | P0 |
| 会话列表 | 展示、新建、切换会话，支持搜索；置顶/归档文档有要求但接口未明确 | `ConversationList`、`ConversationItem`、`NewConversationModal` | `GET /api/conversations`、`POST /api/conversations` | 需要 | 需要新建 | P0 |
| 聊天主界面 | 展示用户、Agent、系统消息，保留协作过程 | `MessageList`、`MessageBubble`、`AgentAvatar` | `GET /api/conversations/{id}/messages` | 需要 | 需要新建 | P0 |
| 消息输入与 @Agent | 支持输入消息、识别 `@Orchestrator`、`@CodeAgent`、`@ReviewAgent`、`@PreviewAgent` | `MessageComposer`、`MentionMenu` | `POST /api/conversations/{id}/messages`、`POST /api/agents/run` | 需要 | 需要新建 | P0 |
| Agent 管理/联系人 | 展示 Orchestrator、Code、Review、Preview Agent 的名称、角色、能力标签 | `AgentList`、`AgentBadge` | 文档有 `Agent` 模型，但未明确 `GET /api/agents` | 需要 | 文档未明确，建议补充 | P0 |
| 多 Agent 调度展示 | 展示 Orchestrator 拆解、子 Agent 顺序执行、汇总结果 | `PlanCard`、`AgentStepTimeline` | `POST /api/agents/run` 或未来 `POST /api/agents/stream` | 需要 | 已有后端基础，需要完善 | P0 |
| Artifact 卡片 | 展示 code、diff、preview、file、deploy 五类 Artifact，P0 优先 code/diff/preview | `ArtifactCard`、`CodeArtifact`、`DiffArtifact`、`PreviewArtifact` | 消息中的 `artifacts` 字段 | 需要 | 需要新建 | P0 |
| Apply Diff | 用户点击后应用 Diff，展示成功/失败状态 | `ApplyDiffButton` | `POST /api/workspaces/{workspace_id}/apply-diff` | 需要 | 文档有接口，仓库暂无实现 | P1 |
| Preview 面板 | iframe 展示 workspace 预览状态和 URL | `PreviewPanel` | `GET /api/workspaces/{workspace_id}/preview` | 需要 | 已有基础，需要完善 | P0 |
| 文件/Workspace | 展示文件列表、查看文件内容、上传/写入文件 | `FileTree`、`FileViewer` | 文档定义 workspace files 接口 | 需要 | 文档有接口，仓库暂无实现 | P1 |
| 设置 | Mock/真实 Agent 模式、API base URL、Demo 模式开关 | `SettingsPanel` | 文档未明确 | 需要本地状态即可 | 文档未明确，建议补充 | P2 |
| SSE 流式输出 | Agent 回复逐步显示 | `StreamingMessage` | `POST /api/agents/stream` | 需要 | 文档有接口，仓库暂无实现 | P1 |

## 3. 开发任务清单

### FE-001 应用主框架

- 需求描述：替换 Vite 默认页面，搭建 IM 工作台：左侧会话列表，中间聊天流，右侧 Artifact/Preview 面板。
- 需要修改/新增文件：修改 `frontend/src/App.tsx`、`frontend/src/App.css`、`frontend/src/index.css`；新增 `frontend/src/components/layout/*`。
- 依赖接口：无。
- mock 数据要求：先使用静态会话和消息数据。
- 预期效果：打开页面即进入 AgentHub 工作台。
- 验收标准：无 Vite 默认内容；桌面宽度下三栏清晰；移动端至少可纵向使用。
- 优先级：P0。

### FE-002 类型定义对齐后端 Schema

- 需求描述：在前端定义 `Conversation`、`Message`、`Agent`、`Artifact`、`AgentRunInput`、`AgentRunResult` 类型，字段严格对齐文档和仓库 schema。
- 需要修改/新增文件：新增 `frontend/src/types/api.ts`。
- 依赖接口：所有接口。
- mock 数据要求：mock 必须使用这些类型。
- 预期效果：前端不随意创造字段。
- 验收标准：Artifact type 仅允许 `"code" | "diff" | "preview" | "file" | "deploy"`；Message role 仅允许 `"user" | "agent" | "system"`。
- 优先级：P0。

### FE-003 Mock 请求拦截层

- 需求描述：当前无后端可用时，前端通过统一 API client 调用 mock handler，后续可切换真实 `/api`。
- 需要修改/新增文件：新增 `frontend/src/api/client.ts`、`frontend/src/api/mock.ts`、`frontend/src/mock/data.ts`。
- 依赖接口：文档第 9 节 API。
- mock 数据要求：内存保存 conversations、messages、agents、workspace preview 状态。
- 预期效果：前端调用 API 方法，不直接读取静态数据。
- 验收标准：关闭后端也能跑完整 Demo 主线。
- 优先级：P0。

### FE-004 会话列表与新建会话

- 需求描述：展示会话列表，支持新建会话、切换会话、按最近更新时间排序。
- 需要修改/新增文件：新增 `ConversationList`、`ConversationItem`、`NewConversationModal`。
- 依赖接口：`GET /api/conversations`、`POST /api/conversations`。
- mock 数据要求：创建会话时生成 `id`、`title`、`mode`、`agent_ids`、`workspace_id`、`created_at`、`updated_at`。
- 预期效果：用户可以创建 `Todo App Development` 会话并进入聊天。
- 验收标准：切换会话后消息区随之变化。
- 优先级：P0。

### FE-005 聊天消息流

- 需求描述：展示用户消息、Agent 消息、系统消息和消息内 Artifact。
- 需要修改/新增文件：新增 `ChatPanel`、`MessageList`、`MessageBubble`、`ArtifactRenderer`。
- 依赖接口：`GET /api/conversations/{conversation_id}/messages`。
- mock 数据要求：内置一组 Demo 消息，覆盖 user/agent/system。
- 预期效果：聊天记录像 IM 一样连续展示。
- 验收标准：每条消息显示 sender、content、created_at；Agent 消息可渲染 artifacts。
- 优先级：P0。

### FE-006 消息输入与 @Agent 识别

- 需求描述：输入框支持发送消息；输入 `@` 时展示 Agent 菜单；发送后触发 mock Agent 返回。
- 需要修改/新增文件：新增 `MessageComposer`、`MentionMenu`。
- 依赖接口：`POST /api/conversations/{conversation_id}/messages`、`POST /api/agents/run`。
- mock 数据要求：支持 `@Orchestrator`、`@CodeAgent`、`@ReviewAgent`、`@PreviewAgent`。
- 预期效果：用户发送 `@Orchestrator 帮我做一个简洁的 Todo List 网页` 后，聊天流出现多 Agent 回复。
- 验收标准：用户消息立即显示；Agent 回复带 code/diff/preview artifacts。
- 优先级：P0。

### FE-007 Agent 联系人与能力标签

- 需求描述：展示 Agent 列表、角色、能力标签，供 @ 菜单和会话创建使用。
- 需要修改/新增文件：新增 `AgentList`、`AgentBadge`。
- 依赖接口：文档有 `Agent` 模型，但未明确 `GET /api/agents`，建议补充。
- mock 数据要求：至少 Orchestrator、Code Agent、Review Agent、Preview Agent。
- 预期效果：用户能理解当前可用 Agent。
- 验收标准：每个 Agent 显示 `name`、`role`、`description`、`capabilities`。
- 优先级：P0。

### FE-008 Orchestrator 调度过程展示

- 需求描述：把 Orchestrator 的任务拆解和子 Agent 产出展示为时间线。
- 需要修改/新增文件：新增 `AgentStepTimeline`、`PlanCard`。
- 依赖接口：`POST /api/agents/run`；任务计划模型 `OrchestratorPlan` 文档有定义，但当前 AgentRunResult 未包含 plan 字段。
- mock 数据要求：可用 system message 或 artifact 表达拆解过程；如需结构化 plan，文档未明确，建议补充。
- 预期效果：用户能看到 Code/Review/Preview Agent 依次执行。
- 验收标准：Demo 主线中至少展示“任务拆解、代码生成、Review、Preview”四步。
- 优先级：P0。

### FE-009 Code Artifact 卡片

- 需求描述：展示代码产物，支持语言、文件名、代码内容、复制。
- 需要修改/新增文件：新增 `CodeArtifactCard`。
- 依赖接口：消息 `artifacts[].type === "code"`。
- mock 数据要求：`data.filename`、`data.language`、`data.content` 来自当前 MockAgent 结构。
- 预期效果：Agent 代码输出不只在自然语言中展示。
- 验收标准：代码等宽展示，长内容可滚动。
- 优先级：P0。

### FE-010 Diff Artifact 卡片

- 需求描述：展示 unified diff，支持 Apply Diff 按钮。
- 需要修改/新增文件：新增 `DiffArtifactCard`、`ApplyDiffButton`。
- 依赖接口：`POST /api/workspaces/{workspace_id}/apply-diff`。
- mock 数据要求：Artifact `data.diff` 使用 unified diff 字符串；Apply 后更新 preview 状态。
- 预期效果：用户可以看到文件变更并应用。
- 验收标准：diff 新增/删除行有视觉区分；Apply 成功后按钮状态变化。
- 优先级：P0/P1，展示为 P0，真实 apply 为 P1。

### FE-011 Preview Artifact 与右侧预览面板

- 需求描述：渲染 preview artifact，并在右侧 iframe 或状态面板展示预览。
- 需要修改/新增文件：新增 `PreviewArtifactCard`、`PreviewPanel`。
- 依赖接口：`GET /api/workspaces/{workspace_id}/preview`。
- mock 数据要求：返回 `{ workspace_id, status }`；如需 `preview_url`，文档未明确，建议补充。
- 预期效果：Apply Diff 后可看到预览卡片和预览区域更新。
- 验收标准：无 URL 时显示 `not_started/running/ready/error` 状态；有 URL 时 iframe 展示。
- 优先级：P0。

### FE-012 Workspace 文件查看

- 需求描述：展示 workspace 文件树和文件内容，辅助 Demo 解释代码产物。
- 需要修改/新增文件：新增 `FileTree`、`FileViewer`。
- 依赖接口：`GET /api/workspaces/{workspace_id}/files`、`GET /api/workspaces/{workspace_id}/files/content?path=...`。
- mock 数据要求：至少包含 `src/App.tsx`、`index.html` 或 Todo 示例文件。
- 预期效果：用户能查看 Agent 生成的文件。
- 验收标准：点击文件可查看内容。
- 优先级：P1。

### FE-013 SSE 流式消息占位

- 需求描述：为后续 `POST /api/agents/stream` 预留 UI 状态：生成中、打字中、失败重试。
- 需要修改/新增文件：扩展 `api/client.ts`、`MessageBubble`、`ChatPanel`。
- 依赖接口：`POST /api/agents/stream`。
- mock 数据要求：用定时器模拟分段返回。
- 预期效果：比赛展示更像真实 Agent 协作。
- 验收标准：关闭 SSE 时仍可用普通 mock 完成 Demo。
- 优先级：P1。

### FE-014 错误与空状态

- 需求描述：处理无会话、接口失败、Agent 失败、Apply Diff 失败、Preview 未启动等状态。
- 需要修改/新增文件：新增 `EmptyState`、`ErrorBanner`、`LoadingState`。
- 依赖接口：所有接口。
- mock 数据要求：可配置 mock 失败场景。
- 预期效果：Demo 不会因空数据或失败状态显得崩坏。
- 验收标准：所有 P0 接口失败时页面有可读提示。
- 优先级：P1。

### FE-015 Demo 脚本固化

- 需求描述：内置一条稳定 Demo 数据链路：Todo App 开发。
- 需要修改/新增文件：新增 `frontend/src/mock/demoScenario.ts`。
- 依赖接口：所有 P0 mock 接口。
- mock 数据要求：完整覆盖 Orchestrator、Code、Review、Preview、code/diff/preview artifacts。
- 预期效果：无需后端即可展示 3 分钟 Demo。
- 验收标准：按 `docs/demo-script.md` 可连续演示。
- 优先级：P0。

## 4. 接口与 Mock 方案

### 4.1 类型定义

#### Conversation

```ts
type Conversation = {
  id: string
  title: string
  mode: 'single' | 'group'
  agent_ids: string[]
  workspace_id: string
  created_at: string
  updated_at: string
}
```

#### Message

```ts
type Message = {
  id: string
  conversation_id: string
  role: 'user' | 'agent' | 'system'
  sender_id: string
  content: string
  artifacts: Artifact[]
  created_at: string
}
```

#### Agent

```ts
type Agent = {
  id: string
  name: string
  role: 'orchestrator' | 'code' | 'review' | 'preview' | 'custom'
  description: string
  capabilities: string[]
  adapter_type: 'mock' | 'codex' | 'claude' | 'opencode' | 'custom'
}
```

#### Artifact

```ts
type Artifact = {
  id: string
  type: 'code' | 'diff' | 'preview' | 'file' | 'deploy'
  title: string
  data: Record<string, unknown>
  created_at: string
}
```

#### AgentRunInput

仓库当前 schema：

```ts
type AgentRunInput = {
  conversation_id: string
  workspace_id: string
  user_message: string
  history: Message[]
  context: Record<string, string>
}
```

注意：附件 1 的 API 示例写的是 `{ conversation_id, agent_id, message }`，但仓库当前后端 `POST /api/agents/run` 使用 `AgentRunInput`，并从 `context.agent_id` 读取目标 Agent。这里存在不一致，文档未明确，建议补充并统一。

#### AgentRunResult

```ts
type AgentRunResult = {
  agent_id: string
  content: string
  artifacts: Artifact[]
  next_actions: string[]
}
```

### 4.2 API 清单

#### GET `/api/conversations`

- 用途：获取会话列表。
- 参数：无。
- 返回：`Conversation[]`。
- 当前仓库：已有基础，需要完善，当前返回空数组。
- Mock 示例：

```json
[
  {
    "id": "conv_001",
    "title": "Todo App Development",
    "mode": "group",
    "agent_ids": ["orchestrator", "code-agent", "review-agent", "preview-agent"],
    "workspace_id": "ws_001",
    "created_at": "2026-06-01T10:00:00Z",
    "updated_at": "2026-06-01T10:05:00Z"
  }
]
```

#### POST `/api/conversations`

- 用途：新建会话。
- 请求体：文档未明确，建议补充。前端建议最小使用 `title`、`mode`、`agent_ids`。
- 返回：`Conversation`。
- 当前仓库：需要新建后端实现；前端需要 mock。
- Mock 示例：

```json
{
  "id": "conv_002",
  "title": "New Conversation",
  "mode": "group",
  "agent_ids": ["orchestrator"],
  "workspace_id": "ws_002",
  "created_at": "2026-06-01T10:10:00Z",
  "updated_at": "2026-06-01T10:10:00Z"
}
```

#### GET `/api/conversations/{conversation_id}`

- 用途：获取单个会话详情。
- 返回：`Conversation`。
- 当前仓库：需要新建。
- Mock：从内存 conversations 查找。

#### PATCH `/api/conversations/{conversation_id}`

- 用途：更新会话标题、模式、Agent 列表等。
- 请求体：文档未明确，建议补充。
- 当前仓库：需要新建。
- Mock：更新内存对象。

#### DELETE `/api/conversations/{conversation_id}`

- 用途：删除/归档会话。
- 返回结构：文档未明确，建议补充。
- 当前仓库：需要新建。
- Mock：从内存移除或标记。归档字段文档未定义，不应擅自加到 `Conversation`。

#### GET `/api/conversations/{conversation_id}/messages`

- 用途：获取会话消息。
- 返回：`Message[]`。
- 当前仓库：已有基础，需要完善，当前返回空数组。
- Mock 示例：

```json
[
  {
    "id": "msg_001",
    "conversation_id": "conv_001",
    "role": "user",
    "sender_id": "user",
    "content": "@Orchestrator 帮我做一个简洁的 Todo List 网页",
    "artifacts": [],
    "created_at": "2026-06-01T10:01:00Z"
  }
]
```

#### POST `/api/conversations/{conversation_id}/messages`

- 用途：发送用户消息并保存。
- 请求体：文档未明确，建议补充。前端建议最小使用 `content`、`sender_id`。
- 返回：建议返回 `Message`，文档未明确，建议补充。
- 当前仓库：需要新建。
- Mock：追加用户消息，再按 Demo 场景追加 Agent 消息。

#### POST `/api/agents/run`

- 用途：调用 Agent。
- 当前仓库：已有基础，需要完善。
- 请求体：优先对齐仓库 `AgentRunInput`。
- 返回：`AgentRunResult`。
- Mock 请求示例：

```json
{
  "conversation_id": "conv_001",
  "workspace_id": "ws_001",
  "user_message": "@Orchestrator 帮我做一个简洁的 Todo List 网页",
  "history": [],
  "context": {
    "agent_id": "orchestrator"
  }
}
```

- Mock 返回示例：

```json
{
  "agent_id": "code-agent",
  "content": "Code Agent 已生成 Todo List 页面代码。",
  "artifacts": [
    {
      "id": "artifact_code_001",
      "type": "code",
      "title": "Todo App Component",
      "data": {
        "filename": "src/App.tsx",
        "language": "tsx",
        "content": "export default function App() { return <main>Todo List</main> }"
      },
      "created_at": "2026-06-01T10:02:00Z"
    }
  ],
  "next_actions": ["review", "preview"]
}
```

#### POST `/api/agents/stream`

- 用途：SSE 流式输出。
- 当前仓库：需要新建。
- 文档未明确事件格式，建议补充。
- Mock：用定时器模拟 `thinking`、`message_delta`、`artifact`、`done`。事件字段未明确，不进入 P0 强依赖。

#### GET `/api/workspaces/{workspace_id}/files`

- 用途：获取 workspace 文件列表。
- 返回结构：文档未明确，建议补充。
- 当前仓库：需要新建。
- Mock：返回文件路径数组或树。字段未明确，不应进入 P0 强展示。

#### GET `/api/workspaces/{workspace_id}/files/content?path=src/App.py`

- 用途：获取文件内容。
- 返回结构：文档未明确，建议补充。
- 当前仓库：需要新建。
- Mock：按 path 返回内容。

#### POST `/api/workspaces/{workspace_id}/files`

- 用途：写入/创建文件。
- 请求体：文档未明确，建议补充。
- 当前仓库：需要新建。
- Mock：写入内存文件表。

#### POST `/api/workspaces/{workspace_id}/apply-diff`

- 用途：应用 Diff。
- 请求体：文档未明确，建议补充。前端建议包含 artifact id 或 diff 字符串，但需后端确认。
- 当前仓库：需要新建。
- Mock：把对应 diff 标记为 applied，并把 preview status 改为 ready。

#### GET `/api/workspaces/{workspace_id}/preview`

- 用途：获取预览状态。
- 当前仓库：已有基础，需要完善，当前返回 `{ workspace_id, status: "not_started" }`。
- 返回结构：文档未明确是否包含 `preview_url`，建议补充。
- Mock 示例：

```json
{
  "workspace_id": "ws_001",
  "status": "ready"
}
```

#### POST `/api/workspaces/{workspace_id}/git/commit`

- 用途：应用变更后提交。
- 请求体/返回体：文档未明确，建议补充。
- 当前仓库：需要新建。
- Mock：返回成功状态即可，P1/P2。

### 4.3 Mock 实现建议

- 前端统一通过 `api/client.ts` 调用，不让组件直接访问 mock 数据。
- `mock.ts` 使用内存 store，保存 `conversations`、`messagesByConversationId`、`agents`、`workspaceFiles`、`previewByWorkspaceId`。
- 配置 `VITE_USE_MOCK=true` 时走 mock；否则请求真实 `/api`。
- Mock 数据必须严格使用文档/仓库 schema 字段。
- 对文档未明确的字段，不写入核心模型；需要 UI 状态时放在前端局部状态，例如按钮 loading、selectedConversationId、activeArtifactId。

## 5. 开发顺序

### 第 1 天：前端基础壳和类型

1. 清理 Vite 默认页面。
2. 建立 `types/api.ts`。
3. 建立三栏 IM 工作台布局。
4. 建立 mock 数据和 API client 雏形。

目标：页面看起来已经是 AgentHub，而不是模板。

### 第 2 天：会话和消息主流程

1. 完成会话列表。
2. 完成新建/切换会话。
3. 完成消息列表。
4. 完成消息输入和本地发送。

目标：用户能创建会话、发送消息、看到聊天历史。

### 第 3 天：@Agent 和 Mock Agent 回复

1. 完成 @Agent 菜单。
2. Mock `POST /api/agents/run`。
3. 用户消息后自动追加 Orchestrator/Agent 回复。
4. 固化 Todo App Demo 场景。

目标：`@Orchestrator 帮我做一个简洁的 Todo List 网页` 可以跑出多 Agent 协作过程。

### 第 4 天：Artifact 卡片

1. 完成 code artifact。
2. 完成 diff artifact。
3. 完成 preview artifact。
4. 消息流中内联展示 artifact。

目标：Demo 能展示代码、Diff、预览卡片。

### 第 5 天：Apply Diff 与 Preview

1. Mock `apply-diff`。
2. Apply 后更新按钮状态和 preview 状态。
3. 右侧 Preview 面板联动当前会话 workspace。
4. 补充失败/空状态。

目标：完成核心闭环：生成 → Diff → Apply → Preview。

### 第 6 天：体验打磨与演示稳定性

1. 优化聊天滚动、loading、Agent 头像、能力标签。
2. 固定 Demo 数据，不依赖真实后端。
3. 检查移动端和常见窗口尺寸。
4. 补齐 README 前端启动说明，若允许改文档时再做。

目标：3 分钟 Demo 可稳定演示。

### 第 7 天：联调预留与验收

1. 检查接口字段是否仍与后端 schema 对齐。
2. 将 mock client 切换点保留好，方便后端接入。
3. 跑 `npm run build` 和 `npm run lint`。
4. 整理待后端补充接口清单。

目标：前端单人可交付，后续能平滑接真实后端。

## 明确需要后端/文档补充的点

- `POST /api/conversations` 请求体未明确。
- `POST /api/conversations/{conversation_id}/messages` 请求体和返回体未明确。
- `GET /api/agents` 未在文档 API 中定义，但前端 Agent 列表需要。
- `POST /api/agents/run` 文档示例和仓库 schema 不一致：`agent_id/message` vs `user_message/context`。
- `POST /api/agents/stream` SSE 事件格式未明确。
- Workspace 文件列表、文件内容、写文件接口返回结构未明确。
- `apply-diff` 请求体和返回体未明确。
- Preview 是否返回 `preview_url` 未明确。
- 会话置顶、归档、搜索的后端字段/接口未明确。
