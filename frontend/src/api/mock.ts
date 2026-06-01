import type {
  Agent,
  AgentRunInput,
  AgentRunResult,
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

/** 生成 ISO 时间字符串，保持和后端 created_at/updated_at 字段格式一致。 */
const nowIso = () => new Date().toISOString()

/** 生成 mock 自增 ID，保持 Demo 数据可读。 */
const nextId = (prefix: string, count: number) =>
  `${prefix}_${String(count + 1).padStart(3, '0')}`

/**
 * 模拟网络延迟。
 * 这样 UI 能暴露 loading 状态，后续接真实后端时交互不会突然变样。
 */
const delay = async () => {
  await new Promise((resolve) => {
    window.setTimeout(resolve, 160)
  })
}

/** 会话列表按 updated_at 倒序展示，符合 IM 最近活跃优先的体验。 */
const sortByUpdatedAt = (items: Conversation[]) =>
  [...items].sort(
    (left, right) =>
      new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime(),
  )

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
      artifacts: [],
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
   * 第一阶段只提供统一返回壳，第三天任务会在这里扩展 Orchestrator 多 Agent 回复链路。
   */
  async runAgent(input: AgentRunInput): Promise<AgentRunResult> {
    await delay()
    const agentId = input.context.agent_id ?? 'orchestrator'
    return {
      agent_id: agentId,
      content: `${agentId} received: ${input.user_message}`,
      artifacts: [],
      next_actions: ['review', 'preview'],
    }
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
}
