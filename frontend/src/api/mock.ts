import type {
  Agent,
  AgentRunInput,
  AgentRunResult,
  ApplyDiffInput,
  ApplyDiffResult,
  Conversation,
  CreateConversationInput,
  CreateMessageInput,
  Message,
  WorkspacePreview,
} from '../types/api'
import {
  mockAgents,
  mockConversations,
  mockMessagesByConversationId,
  mockPreviewByWorkspaceId,
} from '../mock/data'

/**
 * Mock 层的内存状态。
 * 使用副本而不是直接改 mock/data.ts 的常量，避免 Demo 初始数据被运行时操作污染。
 */
const conversations = [...mockConversations]
const agents = [...mockAgents]
const messagesByConversationId: Record<string, Message[]> = structuredClone(
  mockMessagesByConversationId,
)
const previewByWorkspaceId: Record<string, WorkspacePreview> = structuredClone(
  mockPreviewByWorkspaceId,
)
// 记录已应用的 diff artifact，方便 mock 具备“重复点击不会重复应用”的基本行为。
const appliedDiffIds = new Set<string>()

/** 生成 ISO 时间字符串，保持和后端 created_at/updated_at 字段格式一致。 */
const nowIso = () => new Date().toISOString()

/** 生成 mock 自增 ID，保持 Demo 数据可读。 */
const nextId = (prefix: string, count: number) =>
  `${prefix}_${String(count + 1).padStart(3, '0')}`

/** 生成随机整数，用于让 mock 延迟、文案和产物内容看起来更接近真实 Agent。 */
const randomInt = (min: number, max: number) =>
  Math.floor(Math.random() * (max - min + 1)) + min

/** 从候选数组中随机选择一项，避免每次 mock 回复完全一样。 */
const randomPick = <T>(items: T[]) => items[randomInt(0, items.length - 1)]

/**
 * 模拟网络延迟。
 * 这样 UI 能暴露 loading 状态，后续接真实后端时交互不会突然变样。
 */
const delay = async () => {
  await new Promise((resolve) => {
    window.setTimeout(resolve, randomInt(180, 620))
  })
}

/** 会话列表按 updated_at 倒序展示，符合 IM 最近活跃优先的体验。 */
const sortByUpdatedAt = (items: Conversation[]) =>
  [...items].sort(
    (left, right) =>
      new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime(),
  )

/** 生成随机 Artifact ID，避免连续调用 Agent 时产物 key 冲突。 */
const nextArtifactId = (type: string) =>
  `artifact_${type}_${Date.now()}_${randomInt(100, 999)}`

/** 从用户消息中提取一个可读的任务标题，用于 mock 回复和 artifact 标题。 */
const getTaskTitle = (message: string) =>
  message
    .replace(/@(?:Orchestrator|CodeAgent|ReviewAgent|PreviewAgent)/g, '')
    .trim()
    .slice(0, 28) || '开发任务'

/**
 * 生成 Code Agent 的随机代码和 Diff。
 * 内容仍然围绕 Todo Demo，但按钮文案、初始任务、强调色会随机变化。
 */
const createCodeAgentResult = (input: AgentRunInput): AgentRunResult => {
  const timestamp = nowIso()
  const accentColor = randomPick(['#235b54', '#3f6c8f', '#7a5c22', '#6a5acd'])
  const buttonText = randomPick(['Add task', 'Create todo', 'Save item'])
  const todoItems = randomPick([
    ['梳理需求', '生成代码', '检查 Diff'],
    ['设计页面', '接入 Mock', '准备预览'],
    ['创建会话', '发送消息', '查看产物'],
  ])
  const taskTitle = getTaskTitle(input.user_message)
  const todoRows = todoItems
    .map((item) => `    { id: crypto.randomUUID(), title: '${item}' },`)
    .join('\n')
  const content = `const initialTodos = [\n${todoRows}\n]\n\nexport default function App() {\n  return (\n    <main className="todo-app" style={{ '--accent': '${accentColor}' }}>\n      <h1>${taskTitle}</h1>\n      <button>${buttonText}</button>\n    </main>\n  )\n}\n`
  const diff = `--- a/src/App.tsx\n+++ b/src/App.tsx\n@@\n-export default function App() { return null }\n+${content
    .split('\n')
    .filter(Boolean)
    .map((line) => `+${line}`)
    .join('\n')}\n`

  return {
    agent_id: 'code-agent',
    content: randomPick([
      `我先补了一版可演示的 Todo 页面，包含 ${todoItems.length} 条初始任务和一个主要操作按钮。`,
      `已生成 Todo 页面骨架，并把强调色设置为 ${accentColor}，方便后续预览和调整。`,
      `代码已准备好，当前版本重点保证 Demo 链路清晰：列表、标题和主按钮都能直接展示。`,
    ]),
    artifacts: [
      {
        id: nextArtifactId('code'),
        type: 'code',
        title: 'Todo App Component',
        data: {
          filename: 'src/App.tsx',
          language: 'tsx',
          content,
        },
        created_at: timestamp,
      },
      {
        id: nextArtifactId('diff'),
        type: 'diff',
        title: 'Todo App Diff',
        data: {
          filename: 'src/App.tsx',
          diff,
        },
        created_at: timestamp,
      },
    ],
    next_actions: ['review', 'preview'],
  }
}

/** 生成 Review Agent 的随机检查建议，让每次 Demo 有细节差异。 */
const createReviewAgentResult = (): AgentRunResult => {
  const findings = randomPick([
    ['按钮需要 disabled 状态', '空列表要有提示', '移动端标题需要换行保护'],
    ['Diff 应用失败要提示', '输入框需要 trim', '预览未就绪时不要展示空 iframe'],
    ['Artifact 卡片要可滚动', 'Agent 回复要保留时间线', '长文件名需要省略显示'],
  ])

  return {
    agent_id: 'review-agent',
    content: `我完成了一轮轻量 review，建议优先处理：${findings.join('、')}。`,
    artifacts: [
      {
        id: nextArtifactId('file'),
        type: 'file',
        title: 'Review Notes',
        data: {
          findings,
          risk_level: randomPick(['low', 'medium']),
        },
        created_at: nowIso(),
      },
    ],
    next_actions: ['preview'],
  }
}

/** 生成 Preview Agent 的预览结果，并同步更新 workspace preview 状态。 */
const createPreviewAgentResult = (input: AgentRunInput): AgentRunResult => {
  const status = randomPick<WorkspacePreview['status']>(['ready', 'ready', 'running'])
  previewByWorkspaceId[input.workspace_id] = {
    workspace_id: input.workspace_id,
    status,
  }

  return {
    agent_id: 'preview-agent',
    content:
      status === 'ready'
        ? '预览环境已就绪，可以在右侧查看 workspace 状态，下一步可应用 Diff 后刷新页面。'
        : '预览服务正在启动，当前 workspace 已进入 running 状态，稍后可再次刷新预览。',
    artifacts: [
      {
        id: nextArtifactId('preview'),
        type: 'preview',
        title: 'Workspace Preview',
        data: {
          workspace_id: input.workspace_id,
          status,
          checked_at: nowIso(),
        },
        created_at: nowIso(),
      },
    ],
    next_actions: [],
  }
}

/** 生成 Orchestrator 的任务拆解结果。 */
const createOrchestratorResult = (input: AgentRunInput): AgentRunResult => {
  const taskTitle = getTaskTitle(input.user_message)
  const steps = randomPick([
    ['Code Agent 生成页面代码', 'Review Agent 检查实现风险', 'Preview Agent 准备预览状态'],
    ['先生成 Todo 页面', '再检查交互和空状态', '最后返回 workspace 预览'],
    ['拆分 UI 实现', '检查代码质量', '确认 Demo 预览路径'],
  ])

  return {
    agent_id: 'orchestrator',
    content: `我已围绕“${taskTitle}”拆解任务：${steps.join(' → ')}。接下来会按顺序调用子 Agent。`,
    artifacts: [
      {
        id: nextArtifactId('file'),
        type: 'file',
        title: 'Task Breakdown',
        data: {
          summary: 'Rule-based MVP plan',
          task_title: taskTitle,
          steps,
          estimated_minutes: randomInt(6, 14),
        },
        created_at: nowIso(),
      },
    ],
    next_actions: ['code', 'review', 'preview'],
  }
}

export const mockApi = {
  /** Mock GET /api/conversations。 */
  async listConversations(): Promise<Conversation[]> {
    await delay()
    return sortByUpdatedAt(conversations)
  },

  /**
   * Mock POST /api/conversations。
   * 新建会话时同步创建空消息列表和默认 preview 状态，保证切换到新会话不报空引用。
   */
  async createConversation(
    input: CreateConversationInput,
  ): Promise<Conversation> {
    await delay()
    const timestamp = nowIso()
    const id = nextId('conv', conversations.length)
    const conversation: Conversation = {
      id,
      title: input.title,
      mode: input.mode,
      agent_ids: input.agent_ids,
      workspace_id: nextId('ws', conversations.length),
      created_at: timestamp,
      updated_at: timestamp,
    }
    conversations.unshift(conversation)
    messagesByConversationId[id] = []
    previewByWorkspaceId[conversation.workspace_id] = {
      workspace_id: conversation.workspace_id,
      status: 'not_started',
    }
    return conversation
  },

  /** Mock GET /api/conversations/{conversation_id}/messages。 */
  async listMessages(conversationId: string): Promise<Message[]> {
    await delay()
    return messagesByConversationId[conversationId] ?? []
  },

  /**
   * Mock POST /api/conversations/{conversation_id}/messages。
   * 第二天只做用户本地发送：创建 Message、追加到当前会话，并刷新会话 updated_at。
   */
  async createMessage(
    conversationId: string,
    input: CreateMessageInput,
  ): Promise<Message> {
    await delay()
    const timestamp = nowIso()
    const existingMessages = messagesByConversationId[conversationId] ?? []
    const message: Message = {
      id: nextId('msg', Object.values(messagesByConversationId).flat().length),
      conversation_id: conversationId,
      role: input.sender_id === 'user' ? 'user' : 'agent',
      sender_id: input.sender_id,
      content: input.content,
      artifacts: input.artifacts ?? [],
      created_at: timestamp,
    }

    messagesByConversationId[conversationId] = [...existingMessages, message]

    const conversation = conversations.find((item) => item.id === conversationId)
    if (conversation) {
      conversation.updated_at = timestamp
    }

    return message
  },

  /** Mock Agent 联系人列表；真实接口文档未明确，先供前端 @Agent 和联系人列表使用。 */
  async listAgents(): Promise<Agent[]> {
    await delay()
    return agents
  },

  /**
   * Mock POST /api/agents/run。
   * 根据 context.agent_id 分发到不同 mock Agent，并随机生成更真实的回复细节。
   */
  async runAgent(input: AgentRunInput): Promise<AgentRunResult> {
    await delay()
    const agentId = input.context.agent_id ?? 'orchestrator'

    if (agentId === 'code-agent') {
      return createCodeAgentResult(input)
    }

    if (agentId === 'review-agent') {
      return createReviewAgentResult()
    }

    if (agentId === 'preview-agent') {
      return createPreviewAgentResult(input)
    }

    return createOrchestratorResult(input)
  },

  /** Mock GET /api/workspaces/{workspace_id}/preview。 */
  async getWorkspacePreview(workspaceId: string): Promise<WorkspacePreview> {
    await delay()
    return (
      previewByWorkspaceId[workspaceId] ?? {
        workspace_id: workspaceId,
        status: 'not_started',
      }
    )
  },

  /**
   * Mock POST /api/workspaces/{workspace_id}/apply-diff。
   * 应用成功后把 workspace preview 标记为 ready，并记录 artifact_id 防止重复应用。
   */
  async applyDiff(
    workspaceId: string,
    input: ApplyDiffInput,
  ): Promise<ApplyDiffResult> {
    await delay()

    if (!input.diff.trim()) {
      throw new Error('Diff 内容为空，无法应用')
    }

    appliedDiffIds.add(input.artifact_id)
    previewByWorkspaceId[workspaceId] = {
      workspace_id: workspaceId,
      status: 'ready',
    }

    return {
      workspace_id: workspaceId,
      status: 'ready',
      applied_artifact_id: input.artifact_id,
      applied_at: nowIso(),
    }
  },
}

/** mockFetch 支持的 HTTP 方法类型。 */
type MockHttpMethod = 'GET' | 'POST' | 'PATCH' | 'DELETE'

/** mock transport 拦截到的请求上下文。 */
type MockRequestContext = {
  /** 请求方法，来自 RequestInit.method，默认 GET。 */
  method: MockHttpMethod
  /** URL pathname，例如 /api/conversations。 */
  pathname: string
  /** 已解析的 JSON 请求体；GET 请求通常为 null。 */
  body: unknown
}

/** 把 mock 返回值包装成浏览器 fetch 兼容的 JSON Response。 */
const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: {
      'Content-Type': 'application/json',
    },
  })

/** 读取 RequestInit.body 中的 JSON，请求体为空时返回 null。 */
const readJsonBody = (body: BodyInit | null | undefined): unknown => {
  if (!body) {
    return null
  }

  if (typeof body === 'string') {
    return JSON.parse(body)
  }

  throw new Error('Mock transport only supports JSON string request bodies')
}

/** 根据 fetch 入参生成 mock 请求上下文，保持和真实 fetch 调用形态一致。 */
const createMockRequestContext = (
  input: RequestInfo | URL,
  init?: RequestInit,
): MockRequestContext => {
  const rawUrl =
    typeof input === 'string'
      ? input
      : input instanceof URL
        ? input.toString()
        : input.url
  const url = new URL(rawUrl, window.location.origin)
  const method = (init?.method ?? 'GET').toUpperCase() as MockHttpMethod

  return {
    method,
    pathname: url.pathname,
    body: readJsonBody(init?.body),
  }
}

/**
 * mock 请求路由。
 * apiClient 会先发起标准 method/path/body 请求，mockFetch 在这里按后端 API 形状拦截并返回模拟值。
 */
const handleMockRequest = async ({
  method,
  pathname,
  body,
}: MockRequestContext) => {
  if (method === 'GET' && pathname === '/api/conversations') {
    return mockApi.listConversations()
  }

  if (method === 'POST' && pathname === '/api/conversations') {
    return mockApi.createConversation(body as CreateConversationInput)
  }

  const messagesMatch = pathname.match(
    /^\/api\/conversations\/([^/]+)\/messages$/,
  )
  if (messagesMatch && method === 'GET') {
    return mockApi.listMessages(messagesMatch[1])
  }
  if (messagesMatch && method === 'POST') {
    return mockApi.createMessage(messagesMatch[1], body as CreateMessageInput)
  }

  if (method === 'GET' && pathname === '/api/agents') {
    return mockApi.listAgents()
  }

  if (method === 'POST' && pathname === '/api/agents/run') {
    return mockApi.runAgent(body as AgentRunInput)
  }

  const previewMatch = pathname.match(/^\/api\/workspaces\/([^/]+)\/preview$/)
  if (previewMatch && method === 'GET') {
    return mockApi.getWorkspacePreview(previewMatch[1])
  }

  const applyDiffMatch = pathname.match(
    /^\/api\/workspaces\/([^/]+)\/apply-diff$/,
  )
  if (applyDiffMatch && method === 'POST') {
    return mockApi.applyDiff(applyDiffMatch[1], body as ApplyDiffInput)
  }

  throw new Error(`No mock handler for ${method} ${pathname}`)
}

/**
 * fetch 兼容的 mock 拦截器。
 * 这不是直接调用 mock 数据，而是模拟“发起请求 → 拦截请求 → 返回 Response”的流程。
 */
export const mockFetch: typeof fetch = async (input, init) => {
  try {
    const requestContext = createMockRequestContext(input, init)
    const body = await handleMockRequest(requestContext)
    return jsonResponse(body)
  } catch (caughtError) {
    return jsonResponse(
      {
        detail:
          caughtError instanceof Error ? caughtError.message : 'Mock request failed',
      },
      400,
    )
  }
}
