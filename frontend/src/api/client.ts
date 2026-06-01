import type {
  Agent,
  AgentRunInput,
  AgentRunResult,
  Conversation,
  CreateConversationInput,
  Message,
  WorkspacePreview,
} from '../types/api'
import { mockApi } from './mock'

/**
 * 是否使用前端 mock。
 * 默认启用 mock，保证没有后端时也能稳定演示；设置 VITE_USE_MOCK=false 后请求真实 /api。
 */
const useMock = import.meta.env.VITE_USE_MOCK !== 'false'

/**
 * 统一的 JSON 请求助手。
 * 这里集中处理 Content-Type、HTTP 错误和 JSON 解析，避免组件里散落 fetch 细节。
 */
const requestJson = async <T>(
  path: string,
  init?: RequestInit,
): Promise<T> => {
  const response = await fetch(path, {
    headers: {
      'Content-Type': 'application/json',
      ...init?.headers,
    },
    ...init,
  })

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status} ${response.statusText}`)
  }

  return response.json() as Promise<T>
}

export const apiClient = {
  /**
   * 获取会话列表。
   * Mock 模式读内存数据；真实模式对齐后端 GET /api/conversations。
   */
  listConversations(): Promise<Conversation[]> {
    if (useMock) {
      return mockApi.listConversations()
    }
    return requestJson<Conversation[]>('/api/conversations')
  },

  /**
   * 新建会话。
   * 请求体沿用前端最小输入 CreateConversationInput，等待后端文档进一步明确。
   */
  createConversation(
    input: CreateConversationInput,
  ): Promise<Conversation> {
    if (useMock) {
      return mockApi.createConversation(input)
    }
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
    if (useMock) {
      return mockApi.listMessages(conversationId)
    }
    return requestJson<Message[]>(
      `/api/conversations/${conversationId}/messages`,
    )
  },

  /**
   * 获取 Agent 联系人列表。
   * 该接口是前端需要但后端文档未明确的接口，真实联调前需要后端补充。
   */
  listAgents(): Promise<Agent[]> {
    if (useMock) {
      return mockApi.listAgents()
    }
    return requestJson<Agent[]>('/api/agents')
  },

  /**
   * 调用 Agent。
   * 请求体严格使用当前仓库 AgentRunInput：目标 Agent 放在 context.agent_id。
   */
  runAgent(input: AgentRunInput): Promise<AgentRunResult> {
    if (useMock) {
      return mockApi.runAgent(input)
    }
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
    if (useMock) {
      return mockApi.getWorkspacePreview(workspaceId)
    }
    return requestJson<WorkspacePreview>(
      `/api/workspaces/${workspaceId}/preview`,
    )
  },
}
