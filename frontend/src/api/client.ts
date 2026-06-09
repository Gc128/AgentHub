import type {
  Agent,
  AgentRuntimeInfo,
  AgentRunInput,
  AgentRunResult,
  AppliedDiffRecord,
  ApplyDiffInput,
  ApplyDiffResult,
  Conversation,
  ConversationStatusFilter,
  CreateConversationInput,
  CustomAgent,
  CustomAgentCreateInput,
  CustomAgentDeleteResult,
  CustomAgentUpdateInput,
  CreateMessageInput,
  DeleteConversationResult,
  Message,
  MessageSendResponse,
  MessageStreamEvent,
  RevertDiffResult,
  UpdateConversationInput,
  WorkspaceFile,
  WorkspaceFileContent,
  WorkspaceFileDeleteResult,
  WorkspacePreview,
} from '../types/api'

/**
 * FastAPI API 基础地址。
 * 默认指向本地 FastAPI 服务；如需换端口或部署地址，可在 Vite 环境变量中设置 VITE_API_BASE_URL。
 */
const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'
).replace(/\/$/, '')

type ApiEnvelope<T> = {
  /** 历史 Flask 后端统一返回成功标记；FastAPI 直返业务数据。 */
  success: boolean
  /** 成功时的真实业务数据。 */
  data: T
  /** 失败时的错误信息；成功时为 null。 */
  error: string | null
}

/** 从后端错误响应里提取可读错误信息，兼容 envelope/detail/message 几种形态。 */
const getErrorMessage = (payload: unknown) => {
  if (!payload || typeof payload !== 'object') {
    return null
  }

  const errorPayload = payload as {
    /** 历史 Flask envelope 中的错误字段。 */
    error?: unknown
    /** FastAPI 常见错误字段，保留兼容。 */
    detail?: unknown
    /** 其他后端常见错误字段。 */
    message?: unknown
  }

  for (const value of [
    errorPayload.error,
    errorPayload.detail,
    errorPayload.message,
  ]) {
    if (typeof value === 'string' && value.trim()) {
      return value
    }
  }

  return null
}

/**
 * 统一的 JSON 请求助手。
 * 这里集中处理 Content-Type、HTTP 错误和 JSON 解析，避免组件里散落 fetch 细节。
 */
const requestJson = async <T>(
  path: string,
  init?: RequestInit,
): Promise<T> => {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...init?.headers,
    },
    ...init,
  })

  const payload = (await response.json().catch(() => null)) as
    | ApiEnvelope<T>
    | { detail?: string; error?: string; message?: string }
    | T
    | null

  if (!response.ok) {
    throw new Error(
      getErrorMessage(payload) ??
        `Request failed: ${response.status} ${response.statusText}`,
    )
  }

  if (
    payload &&
    typeof payload === 'object' &&
    'success' in payload &&
    'data' in payload
  ) {
    const envelopedPayload = payload as ApiEnvelope<T>

    if (!envelopedPayload.success) {
      throw new Error(envelopedPayload.error ?? '接口请求失败')
    }

    return envelopedPayload.data
  }

  return payload as T
}

const parseSseBlock = (block: string): MessageStreamEvent | null => {
  const lines = block.split(/\r?\n/)
  let event = 'message'
  const dataLines: string[] = []

  for (const line of lines) {
    if (line.startsWith('event:')) {
      event = line.slice('event:'.length).trim()
      continue
    }
    if (line.startsWith('data:')) {
      dataLines.push(line.slice('data:'.length).trim())
    }
  }

  if (dataLines.length === 0) {
    return null
  }

  return {
    event,
    data: JSON.parse(dataLines.join('\n')) as unknown,
  } as MessageStreamEvent
}

const requestSse = async (
  path: string,
  init: RequestInit,
  onEvent: (event: MessageStreamEvent) => void,
) => {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...init.headers,
    },
    ...init,
  })

  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as unknown
    throw new Error(
      getErrorMessage(payload) ??
        `Request failed: ${response.status} ${response.statusText}`,
    )
  }
  if (!response.body) {
    throw new Error('当前浏览器不支持流式响应')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) {
      break
    }
    buffer += decoder.decode(value, { stream: true })
    const blocks = buffer.split(/\r?\n\r?\n/)
    buffer = blocks.pop() ?? ''
    for (const block of blocks) {
      const parsed = parseSseBlock(block)
      if (parsed) {
        onEvent(parsed)
      }
    }
  }

  buffer += decoder.decode()
  const parsed = parseSseBlock(buffer)
  if (parsed) {
    onEvent(parsed)
  }
}

export const apiClient = {
  /**
   * 获取会话列表。
   * 始终发起 GET /api/conversations，由 FastAPI 后端返回真实持久化数据。
   */
  listConversations(
    status: ConversationStatusFilter = 'active',
  ): Promise<Conversation[]> {
    return requestJson<Conversation[]>(
      `/api/conversations?status=${encodeURIComponent(status)}`,
    )
  },

  /**
   * 新建会话。
   * 请求体沿用前端最小输入 CreateConversationInput，FastAPI 后端会生成 id/workspace_id/时间戳。
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
   * 更新会话信息。
   * 当前 UI 使用它做置顶/取消置顶和成员变更；PATCH 只修改传入字段。
   */
  updateConversation(
    conversationId: string,
    input: UpdateConversationInput,
  ): Promise<Conversation> {
    return requestJson<Conversation>(`/api/conversations/${conversationId}`, {
      method: 'PATCH',
      body: JSON.stringify(input),
    })
  },

  /**
   * 删除会话。
   * 始终发起 DELETE /api/conversations/{id}，后端会同步清理消息和预览状态。
   */
  deleteConversation(conversationId: string): Promise<DeleteConversationResult> {
    return requestJson<DeleteConversationResult>(
      `/api/conversations/${conversationId}`,
      {
        method: 'DELETE',
      },
    )
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
   * 当前前端传 sender_id/content/artifacts，FastAPI 后端会补齐 Message 结构并持久化。
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
   * 发送用户消息并由后端完成 Agent 编排。
   * 这是前端主链路：FastAPI 会保存用户消息，并返回已持久化的 Agent 消息序列。
   */
  sendMessage(
    conversationId: string,
    input: CreateMessageInput,
  ): Promise<MessageSendResponse> {
    return requestJson<MessageSendResponse>(
      `/api/conversations/${conversationId}/messages/run`,
      {
        method: 'POST',
        body: JSON.stringify(input),
      },
    )
  },

  streamMessage(
    conversationId: string,
    input: CreateMessageInput,
    onEvent: (event: MessageStreamEvent) => void,
  ): Promise<void> {
    return requestSse(
      `/api/conversations/${conversationId}/messages/stream`,
      {
        method: 'POST',
        body: JSON.stringify(input),
      },
      onEvent,
    )
  },

  deleteMessage(conversationId: string, messageId: string): Promise<Message> {
    return requestJson<Message>(
      `/api/conversations/${conversationId}/messages/${messageId}`,
      {
        method: 'DELETE',
      },
    )
  },

  pinMessageContext(
    conversationId: string,
    messageId: string,
  ): Promise<Message> {
    return requestJson<Message>(
      `/api/conversations/${conversationId}/messages/${messageId}/pin-context`,
      {
        method: 'POST',
      },
    )
  },

  unpinMessageContext(
    conversationId: string,
    messageId: string,
  ): Promise<Message> {
    return requestJson<Message>(
      `/api/conversations/${conversationId}/messages/${messageId}/pin-context`,
      {
        method: 'DELETE',
      },
    )
  },

  regenerateMessageStream(
    conversationId: string,
    messageId: string,
    onEvent: (event: MessageStreamEvent) => void,
  ): Promise<void> {
    return requestSse(
      `/api/conversations/${conversationId}/messages/${messageId}/regenerate/stream`,
      {
        method: 'POST',
      },
      onEvent,
    )
  },

  /**
   * 获取 Agent 联系人列表。
   * 由 FastAPI 后端返回可用 Agent 列表。
   */
  listAgents(): Promise<Agent[]> {
    return requestJson<Agent[]>('/api/agents')
  },

  listCustomAgents(): Promise<CustomAgent[]> {
    return requestJson<CustomAgent[]>('/api/agents/custom')
  },

  createCustomAgent(input: CustomAgentCreateInput): Promise<CustomAgent> {
    return requestJson<CustomAgent>('/api/agents/custom', {
      method: 'POST',
      body: JSON.stringify(input),
    })
  },

  updateCustomAgent(
    agentId: string,
    input: CustomAgentUpdateInput,
  ): Promise<CustomAgent> {
    return requestJson<CustomAgent>(`/api/agents/custom/${agentId}`, {
      method: 'PATCH',
      body: JSON.stringify(input),
    })
  },

  deleteCustomAgent(agentId: string): Promise<CustomAgentDeleteResult> {
    return requestJson<CustomAgentDeleteResult>(
      `/api/agents/custom/${agentId}`,
      {
        method: 'DELETE',
      },
    )
  },

  testCustomAgent(agentId: string, message: string): Promise<AgentRunResult> {
    return requestJson<AgentRunResult>(`/api/agents/custom/${agentId}/test`, {
      method: 'POST',
      body: JSON.stringify({ message }),
    })
  },

  getAgentRuntime(): Promise<AgentRuntimeInfo> {
    return requestJson<AgentRuntimeInfo>('/api/agents/runtime')
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

  getWorkspacePreviewPageUrl(
    workspaceId: string,
    path?: string,
    refreshToken?: number,
  ): string {
    const params: string[] = []
    if (path) {
      params.push(`path=${path.split('/').map(encodeURIComponent).join('/')}`)
    }
    if (refreshToken !== undefined) {
      params.push(`_v=${encodeURIComponent(String(refreshToken))}`)
    }

    const query = params.length > 0 ? `?${params.join('&')}` : ''
    return `${API_BASE_URL}/api/workspaces/${encodeURIComponent(workspaceId)}/preview-page${query}`
  },

  /**
   * 获取 workspace 文件列表。
   * 右侧 Workspace 面板用它展示当前会话真实文件状态。
   */
  listWorkspaceFiles(workspaceId: string): Promise<WorkspaceFile[]> {
    return requestJson<WorkspaceFile[]>(`/api/workspaces/${workspaceId}/files`)
  },

  /**
   * 读取 workspace 中某个真实文件的内容。
   * 右侧 Workspace 面板用它做文件预览弹窗。
   */
  getWorkspaceFileContent(
    workspaceId: string,
    path: string,
  ): Promise<WorkspaceFileContent> {
    return requestJson<WorkspaceFileContent>(
      `/api/workspaces/${workspaceId}/files/content?path=${encodeURIComponent(path)}`,
    )
  },

  /**
   * 删除 workspace 中某个真实文件。
   * 后端会做路径越权检查，并清理对应文件元数据。
   */
  deleteWorkspaceFile(
    workspaceId: string,
    path: string,
  ): Promise<WorkspaceFileDeleteResult> {
    return requestJson<WorkspaceFileDeleteResult>(
      `/api/workspaces/${workspaceId}/files?path=${encodeURIComponent(path)}`,
      {
        method: 'DELETE',
      },
    )
  },

  /**
   * 获取 workspace 已应用 Diff 历史。
   * 右侧 Workspace 面板用它展示用户已经确认过的变更。
   */
  listAppliedDiffs(workspaceId: string): Promise<AppliedDiffRecord[]> {
    return requestJson<AppliedDiffRecord[]>(
      `/api/workspaces/${workspaceId}/applied-diffs`,
    )
  },

  /**
   * 应用 workspace 中的 Diff。
   * 当前前端按 ApplyDiffInput 发送，FastAPI 后端会记录应用结果并刷新 preview 状态。
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

  revertAppliedDiff(
    workspaceId: string,
    recordId: string,
  ): Promise<RevertDiffResult> {
    return requestJson<RevertDiffResult>(
      `/api/workspaces/${workspaceId}/applied-diffs/${recordId}/revert`,
      {
        method: 'POST',
      },
    )
  },
}
