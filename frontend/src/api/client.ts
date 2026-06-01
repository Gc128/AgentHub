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
import { mockFetch } from './mock'

/**
 * 是否使用前端 mock。
 * 默认启用 mock，保证没有后端时也能稳定演示；设置 VITE_USE_MOCK=false 后请求真实 /api。
 */
const useMock = import.meta.env.VITE_USE_MOCK !== 'false'

/**
 * 前端请求使用的 fetch 实现。
 * mock 模式也先构造 method/path/body 请求，再由 mockFetch 按路由拦截，方便后端接入时直接切换。
 */
const fetchTransport: typeof fetch = useMock ? mockFetch : fetch

/**
 * 统一的 JSON 请求助手。
 * 这里集中处理 Content-Type、HTTP 错误和 JSON 解析，避免组件里散落 fetch 细节。
 */
const requestJson = async <T>(
  path: string,
  init?: RequestInit,
): Promise<T> => {
  const response = await fetchTransport(path, {
    headers: {
      'Content-Type': 'application/json',
      ...init?.headers,
    },
    ...init,
  })

  if (!response.ok) {
    const errorPayload = (await response.json().catch(() => null)) as
      | { detail?: string }
      | null
    throw new Error(
      errorPayload?.detail ??
        `Request failed: ${response.status} ${response.statusText}`,
    )
  }

  return response.json() as Promise<T>
}

export const apiClient = {
  /**
   * 获取会话列表。
   * 始终发起 GET /api/conversations；mock 模式由 mockFetch 拦截。
   */
  listConversations(): Promise<Conversation[]> {
    return requestJson<Conversation[]>('/api/conversations')
  },

  /**
   * 新建会话。
   * 请求体沿用前端最小输入 CreateConversationInput，等待后端文档进一步明确。
   */
  createConversation(
    input: CreateConversationInput,
  ): Promise<Conversation> {
    return requestJson<Conversation>('/api/conversations', {
      method: 'POST',
      body: JSON.stringify(input),
    })
  },

  /**
   * 获取某个会话的消息列表。
   * 返回 Message[]，每条消息可能带 artifacts，聊天流和右侧面板都依赖它。
   */
  listMessages(conversationId: string): Promise<Message[]> {
    return requestJson<Message[]>(
      `/api/conversations/${conversationId}/messages`,
    )
  },

  /**
   * 在指定会话中创建一条消息。
   * 后端请求体尚未定稿，当前前端只传 sender_id/content，mock 会补齐 Message 结构。
   */
  createMessage(
    conversationId: string,
    input: CreateMessageInput,
  ): Promise<Message> {
    return requestJson<Message>(
      `/api/conversations/${conversationId}/messages`,
      {
        method: 'POST',
        body: JSON.stringify(input),
      },
    )
  },

  /**
   * 获取 Agent 联系人列表。
   * 该接口是前端需要但后端文档未明确的接口，真实联调前需要后端补充。
   */
  listAgents(): Promise<Agent[]> {
    return requestJson<Agent[]>('/api/agents')
  },

  /**
   * 调用 Agent。
   * 请求体严格使用当前仓库 AgentRunInput：目标 Agent 放在 context.agent_id。
   */
  runAgent(input: AgentRunInput): Promise<AgentRunResult> {
    return requestJson<AgentRunResult>('/api/agents/run', {
      method: 'POST',
      body: JSON.stringify(input),
    })
  },

  /**
   * 获取 workspace 预览状态。
   * 当前后端已有 GET /api/workspaces/{workspace_id}/preview 的基础实现。
   */
  getWorkspacePreview(workspaceId: string): Promise<WorkspacePreview> {
    return requestJson<WorkspacePreview>(
      `/api/workspaces/${workspaceId}/preview`,
    )
  },

  /**
   * 应用 workspace 中的 Diff。
   * 后端请求体未定稿，当前前端按 ApplyDiffInput 发送，mock 会同步刷新 preview 状态。
   */
  applyDiff(
    workspaceId: string,
    input: ApplyDiffInput,
  ): Promise<ApplyDiffResult> {
    return requestJson<ApplyDiffResult>(
      `/api/workspaces/${workspaceId}/apply-diff`,
      {
        method: 'POST',
        body: JSON.stringify(input),
      },
    )
  },
}
