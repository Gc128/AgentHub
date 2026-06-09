import { useEffect, useMemo, useRef, useState } from 'react'
import { Alert, ConfigProvider, theme } from 'antd'
import { apiClient } from './api/client'
import { AgentList } from './components/agents/AgentList'
import { ChatPanel } from './components/chat/ChatPanel'
import { ConversationMembersModal } from './components/conversations/ConversationMembersModal'
import { ConversationList } from './components/conversations/ConversationList'
import { NewConversationModal } from './components/conversations/NewConversationModal'
import { AppLayout } from './components/layout/AppLayout'
import { WorkspacePanel } from './components/workspace/WorkspacePanel'
import type {
  Agent,
  AgentRuntimeInfo,
  AppliedDiffRecord,
  Artifact,
  Conversation,
  CreateConversationInput,
  Message,
  MessageStreamEvent,
  ConversationMode,
  WorkspaceFile,
  WorkspaceFileContent,
  WorkspacePreview,
} from './types/api'
import './App.css'

/** 会话按最近更新时间倒序排序，保持 IM 左侧列表的常见体验。 */
const sortConversationsByUpdatedAt = (items: Conversation[]) =>
  [...items].sort(
    (left, right) => {
      if (left.is_pinned !== right.is_pinned) {
        return left.is_pinned ? -1 : 1
      }

      return (
        new Date(right.updated_at).getTime() -
        new Date(left.updated_at).getTime()
      )
    },
  )

/**
 * 判断消息序列是否携带 preview artifact。
 * 如果有，前端会重新拉取 workspace preview，保持右侧状态和聊天产物一致。
 */
const hasPreviewArtifact = (items: Message[]) =>
  items.some((message) =>
    message.artifacts.some((artifact) => artifact.type === 'preview'),
  )

/** 从 workspace 变更历史恢复已应用 diff id 集合，保证切换会话后按钮状态不丢。 */
const getAppliedDiffIds = (records: AppliedDiffRecord[]) =>
  new Set(
    records
      .filter((record) => !record.reverted_at)
      .map((record) => record.artifact_id),
  )

/** 会话模式由成员数量推导，避免 UI 手动选择后和 agent_ids 语义不一致。 */
const inferConversationMode = (agentIds: string[]): ConversationMode =>
  agentIds.length > 1 ? 'group' : 'single'

const createDraftMessage = (
  id: string,
  conversationId: string,
  agentId: string,
): Message => ({
  id,
  conversation_id: conversationId,
  role: 'agent',
  sender_id: agentId,
  content: '',
  artifacts: [],
  created_at: new Date().toISOString(),
})

const STREAM_VISUAL_CHUNK_SIZE = 14
const STREAM_VISUAL_DELAY_MS = 28

const sleep = (milliseconds: number) =>
  new Promise((resolve) => window.setTimeout(resolve, milliseconds))

const splitVisualDelta = (delta: string) => {
  if (delta.length <= STREAM_VISUAL_CHUNK_SIZE) {
    return [delta]
  }

  const chunks: string[] = []
  for (let index = 0; index < delta.length; index += STREAM_VISUAL_CHUNK_SIZE) {
    chunks.push(delta.slice(index, index + STREAM_VISUAL_CHUNK_SIZE))
  }
  return chunks
}

/**
 * AgentHub 前端根组件。
 * 这里负责把首日 Demo 的核心数据串起来：会话列表、聊天消息、Agent 联系人和右侧产物预览。
 */
function App() {
  // 可用 Agent 列表，来自 FastAPI 后端 /api/agents。
  const [agents, setAgents] = useState<Agent[]>([])
  const [agentRuntime, setAgentRuntime] = useState<AgentRuntimeInfo | null>(null)
  // 左侧会话列表，Conversation 字段严格对齐后端 schema。
  const [conversations, setConversations] = useState<Conversation[]>([])
  // 当前选中的会话 ID；用 ID 而不是对象，方便列表刷新后重新计算选中会话。
  const [selectedConversationId, setSelectedConversationId] = useState<
    string | null
  >(null)
  // 消息按会话隔离缓存，避免一个会话的流式 draft 污染另一个会话。
  const [messagesByConversationId, setMessagesByConversationId] = useState<
    Record<string, Message[]>
  >({})
  // 当前会话 workspace 的预览状态，用于右侧 Workspace 面板。
  const [preview, setPreview] = useState<WorkspacePreview | null>(null)
  // 当前 workspace 文件列表。
  const [workspaceFiles, setWorkspaceFiles] = useState<WorkspaceFile[]>([])
  // 当前 workspace 已应用 Diff 历史。
  const [appliedDiffRecords, setAppliedDiffRecords] = useState<
    AppliedDiffRecord[]
  >([])
  // 消息区 loading 状态，只作用于当前会话消息和 preview 加载。
  const [loadingMessages, setLoadingMessages] = useState(false)
  // 会话搜索关键词；搜索接口文档未明确，第二天先做前端本地过滤。
  const [conversationSearchTerm, setConversationSearchTerm] = useState('')
  // 控制新建会话弹窗是否打开。
  const [newConversationOpen, setNewConversationOpen] = useState(false)
  // 控制当前会话成员管理弹窗是否打开。
  const [memberManagerOpen, setMemberManagerOpen] = useState(false)
  // Agent 运行状态按会话隔离；切换会话时只展示当前会话的生成状态。
  const [agentRunningByConversationId, setAgentRunningByConversationId] =
    useState<Record<string, boolean>>({})
  const [harnessStatusByConversationId, setHarnessStatusByConversationId] =
    useState<Record<string, string | null>>({})
  // 已成功应用的 diff artifact ID；聊天流和右侧产物栏共享这份状态。
  const [appliedDiffIds, setAppliedDiffIds] = useState<ReadonlySet<string>>(
    () => new Set(),
  )
  // 当前正在应用的 diff artifact ID；用于让同一张卡片展示“应用中”。
  const [applyingDiffId, setApplyingDiffId] = useState<string | null>(null)
  const [revertingDiffRecordId, setRevertingDiffRecordId] = useState<
    string | null
  >(null)
  // 当前正在删除的 workspace 文件路径，用于文件行按钮 loading。
  const [deletingWorkspaceFilePath, setDeletingWorkspaceFilePath] = useState<
    string | null
  >(null)
  // 页面级错误提示；首日先集中展示，后续可以拆成更细的错误状态。
  const [error, setError] = useState<string | null>(null)
  const selectedConversationIdRef = useRef<string | null>(selectedConversationId)

  useEffect(() => {
    selectedConversationIdRef.current = selectedConversationId
  }, [selectedConversationId])

  useEffect(() => {
    // ignore 用于避免组件卸载后异步请求继续 setState。
    let ignore = false

    /**
     * 首屏初始化数据：
     * 1. 拉会话列表，决定左侧列表和默认选中会话；
     * 2. 拉 Agent 列表，供联系人区和消息发送者名称解析使用。
     */
    const loadInitialData = async () => {
      try {
        const [nextConversations, nextAgents, nextRuntime] = await Promise.all([
          apiClient.listConversations(),
          apiClient.listAgents(),
          apiClient.getAgentRuntime(),
        ])

        if (ignore) {
          return
        }

        setConversations(nextConversations)
        setAgents(nextAgents)
        setAgentRuntime(nextRuntime)
        setError(null)
        // 默认选中最近活跃的第一条会话，后端已按置顶和 updated_at 排序返回。
        setSelectedConversationId(nextConversations[0]?.id ?? null)
      } catch (caughtError) {
        if (!ignore) {
          setError(
            caughtError instanceof Error
              ? caughtError.message
              : '加载初始化数据失败',
          )
        }
      }
    }

    void loadInitialData()

    return () => {
      ignore = true
    }
  }, [])

  /**
   * 根据 selectedConversationId 推导完整会话对象。
   * useMemo 避免每次渲染都重复查找，也让下方 effect 依赖更清晰。
   */
  const selectedConversation = useMemo(
    () =>
      conversations.find(
        (conversation) => conversation.id === selectedConversationId,
      ) ?? null,
    [conversations, selectedConversationId],
  )

  const selectedMessages = selectedConversationId
    ? messagesByConversationId[selectedConversationId] ?? []
    : []
  const selectedAgentRunning = selectedConversationId
    ? agentRunningByConversationId[selectedConversationId] ?? false
    : false
  const selectedHarnessStatus = selectedConversationId
    ? harnessStatusByConversationId[selectedConversationId] ?? null
    : null

  const setConversationMessages = (
    conversationId: string,
    updater: (messages: Message[]) => Message[],
  ) => {
    setMessagesByConversationId((currentMessagesByConversationId) => ({
      ...currentMessagesByConversationId,
      [conversationId]: updater(
        currentMessagesByConversationId[conversationId] ?? [],
      ),
    }))
  }

  const setConversationRunning = (
    conversationId: string,
    running: boolean,
  ) => {
    setAgentRunningByConversationId((current) => ({
      ...current,
      [conversationId]: running,
    }))
  }

  const setConversationHarnessStatus = (
    conversationId: string,
    status: string | null,
  ) => {
    setHarnessStatusByConversationId((current) => ({
      ...current,
      [conversationId]: status,
    }))
  }

  /**
   * 当前会话实际可用的 Agent。
   * 这里严格按 conversation.agent_ids 取成员，聊天输入和 @ 路由都只能使用这批 Agent。
   */
  const selectedConversationAgents = useMemo(() => {
    if (!selectedConversation) {
      return []
    }

    return selectedConversation.agent_ids
      .map((agentId) => agents.find((agent) => agent.id === agentId))
      .filter((agent): agent is Agent => Boolean(agent))
  }, [agents, selectedConversation])

  const mockAgentWarning = useMemo(() => {
    const coreAgentIds = new Set([
      'orchestrator',
      'code-agent',
      'review-agent',
      'preview-agent',
    ])
    const hasMockCoreAgent = agents.some(
      (agent) => coreAgentIds.has(agent.id) && agent.adapter_type === 'mock',
    )
    if (agentRuntime?.agent_mode === 'mock' || hasMockCoreAgent) {
      return '当前前端连接的是 Mock Agent 后端，回复会使用固定模拟数据。请确认 VITE_API_BASE_URL 指向真实 FastAPI 服务，例如 http://127.0.0.1:8000。'
    }
    if (agentRuntime && !agentRuntime.api_key_configured) {
      return `当前后端是 Real Agent 模式，但没有配置 API Key。Provider: ${agentRuntime.provider}，Model: ${agentRuntime.model}。`
    }
    return null
  }, [agentRuntime, agents])

  useEffect(() => {
    // 没有选中会话时清空中间消息区和右侧预览，避免展示上一个会话的数据。
    if (!selectedConversation) {
      setPreview(null)
      setWorkspaceFiles([])
      setAppliedDiffRecords([])
      setAppliedDiffIds(new Set())
      return
    }

    let ignore = false
    setLoadingMessages(true)

    /**
     * 切换会话后的数据加载：
     * 消息流和 workspace 面板都依赖当前会话，所以放在同一个 effect 中同步刷新。
     */
    const loadConversationData = async () => {
      try {
        const [
          nextMessages,
          nextPreview,
          nextWorkspaceFiles,
          nextAppliedDiffRecords,
        ] = await Promise.all([
          apiClient.listMessages(selectedConversation.id),
          apiClient.getWorkspacePreview(selectedConversation.workspace_id),
          apiClient.listWorkspaceFiles(selectedConversation.workspace_id),
          apiClient.listAppliedDiffs(selectedConversation.workspace_id),
        ])
        if (ignore) {
          return
        }

        setConversationMessages(selectedConversation.id, () => nextMessages)
        setPreview(nextPreview)
        setWorkspaceFiles(nextWorkspaceFiles)
        setAppliedDiffRecords(nextAppliedDiffRecords)
        setAppliedDiffIds(getAppliedDiffIds(nextAppliedDiffRecords))
        setError(null)
      } catch (caughtError) {
        if (!ignore) {
          setError(
            caughtError instanceof Error
              ? caughtError.message
              : '加载会话数据失败',
          )
        }
      } finally {
        if (!ignore) {
          setLoadingMessages(false)
        }
      }
    }

    void loadConversationData()

    return () => {
      ignore = true
    }
  }, [selectedConversation?.id, selectedConversation?.workspace_id])

  /**
   * 按搜索关键词过滤会话列表。
   * 目前只按标题过滤，不向 Conversation 模型增加文档未定义的搜索字段。
   */
  const filteredConversations = useMemo(() => {
    const normalizedSearchTerm = conversationSearchTerm.trim().toLowerCase()
    if (!normalizedSearchTerm) {
      return conversations
    }

    return conversations.filter((conversation) =>
      conversation.title.toLowerCase().includes(normalizedSearchTerm),
    )
  }, [conversations, conversationSearchTerm])

  /**
   * 创建新会话。
   * 成功后立即放到左侧列表顶部并选中，让用户可以马上开始发消息。
   */
  const handleCreateConversation = async (input: CreateConversationInput) => {
    const conversation = await apiClient.createConversation(input)
    setConversations((currentConversations) =>
      sortConversationsByUpdatedAt([conversation, ...currentConversations]),
    )
    setConversationSearchTerm('')
    setSelectedConversationId(conversation.id)
  }

  /**
   * 置顶或取消置顶会话。
   * 这里只 PATCH is_pinned 字段，不改 updated_at，避免置顶操作污染“最近消息时间”。
   */
  const handleTogglePinConversation = async (
    conversationId: string,
    nextPinned: boolean,
  ) => {
    try {
      const updatedConversation = await apiClient.updateConversation(
        conversationId,
        {
          is_pinned: nextPinned,
        },
      )

      setConversations((currentConversations) =>
        sortConversationsByUpdatedAt(
          currentConversations.map((conversation) =>
            conversation.id === conversationId
              ? updatedConversation
              : conversation,
          ),
        ),
      )
      setError(null)
    } catch (caughtError) {
      setError(
        caughtError instanceof Error ? caughtError.message : '更新会话失败',
      )
    }
  }

  /**
   * 更新当前会话成员。
   * 保存 agent_ids 的同时同步推导 mode，保证一个成员就是单聊，多个成员就是群聊。
   */
  const handleUpdateConversationMembers = async (
    conversationId: string,
    nextAgentIds: string[],
  ) => {
    if (nextAgentIds.length === 0) {
      throw new Error('当前会话至少需要保留一个 Agent')
    }

    try {
      const updatedConversation = await apiClient.updateConversation(
        conversationId,
        {
          agent_ids: nextAgentIds,
          mode: inferConversationMode(nextAgentIds),
        },
      )

      setConversations((currentConversations) =>
        sortConversationsByUpdatedAt(
          currentConversations.map((conversation) =>
            conversation.id === conversationId
              ? updatedConversation
              : conversation,
          ),
        ),
      )
      setError(null)
    } catch (caughtError) {
      const message =
        caughtError instanceof Error ? caughtError.message : '更新成员失败'
      setError(message)
      throw new Error(message)
    }
  }

  /**
   * 删除会话。
   * 如果删除的是当前会话，自动切到排序后的第一条会话；没有会话时进入空状态。
   */
  const handleDeleteConversation = async (conversationId: string) => {
    try {
      await apiClient.deleteConversation(conversationId)

      const nextConversations = sortConversationsByUpdatedAt(
        conversations.filter(
          (conversation) => conversation.id !== conversationId,
        ),
      )
      setConversations(nextConversations)
      setMessagesByConversationId((current) => {
        const next = { ...current }
        delete next[conversationId]
        return next
      })
      setAgentRunningByConversationId((current) => {
        const next = { ...current }
        delete next[conversationId]
        return next
      })
      setHarnessStatusByConversationId((current) => {
        const next = { ...current }
        delete next[conversationId]
        return next
      })

      if (selectedConversationId === conversationId) {
        setSelectedConversationId(nextConversations[0]?.id ?? null)
      }

      setError(null)
    } catch (caughtError) {
      setError(
        caughtError instanceof Error ? caughtError.message : '删除会话失败',
      )
    }
  }

  /**
   * 应用某个 Diff Artifact。
   * 这是核心闭环：Diff 卡片按钮 → 后端 apply-diff → workspace preview 刷新。
   */
  const handleApplyDiff = async (artifact: Artifact, diff: string) => {
    if (!selectedConversation) {
      throw new Error('请先选择一个会话')
    }

    setApplyingDiffId(artifact.id)

    try {
      const result = await apiClient.applyDiff(selectedConversation.workspace_id, {
        artifact_id: artifact.id,
        diff,
      })
      setAppliedDiffIds((currentDiffIds) => {
        const nextDiffIds = new Set(currentDiffIds)
        nextDiffIds.add(result.applied_artifact_id)
        return nextDiffIds
      })

      const [nextWorkspaceFiles, nextAppliedDiffRecords] = await Promise.all([
        apiClient.listWorkspaceFiles(selectedConversation.workspace_id),
        apiClient.listAppliedDiffs(selectedConversation.workspace_id),
      ])
      setPreview({
        workspace_id: result.workspace_id,
        status: result.status,
        preview_url: result.preview_url ?? null,
        entry_path: result.entry_path ?? null,
      })
      setWorkspaceFiles(nextWorkspaceFiles)
      setAppliedDiffRecords(nextAppliedDiffRecords)
      setAppliedDiffIds(getAppliedDiffIds(nextAppliedDiffRecords))
      setError(null)
    } catch (caughtError) {
      const message =
        caughtError instanceof Error ? caughtError.message : '应用 Diff 失败'
      setError(message)
      throw new Error(message)
    } finally {
      setApplyingDiffId(null)
    }
  }

  const handleRevertAppliedDiff = async (record: AppliedDiffRecord) => {
    if (!selectedConversation) {
      throw new Error('请先选择一个会话')
    }

    setRevertingDiffRecordId(record.id)

    try {
      const result = await apiClient.revertAppliedDiff(
        selectedConversation.workspace_id,
        record.id,
      )
      const [nextWorkspaceFiles, nextAppliedDiffRecords] = await Promise.all([
        apiClient.listWorkspaceFiles(selectedConversation.workspace_id),
        apiClient.listAppliedDiffs(selectedConversation.workspace_id),
      ])
      setPreview({
        workspace_id: result.workspace_id,
        status: result.status,
        preview_url: result.preview_url ?? null,
        entry_path: result.entry_path ?? null,
      })
      setWorkspaceFiles(nextWorkspaceFiles)
      setAppliedDiffRecords(nextAppliedDiffRecords)
      setAppliedDiffIds(getAppliedDiffIds(nextAppliedDiffRecords))
      setError(null)
    } catch (caughtError) {
      const message =
        caughtError instanceof Error ? caughtError.message : '回退 Diff 失败'
      setError(message)
      throw new Error(message)
    } finally {
      setRevertingDiffRecordId(null)
    }
  }

  /**
   * 读取当前 workspace 文件内容。
   * WorkspacePanel 用它打开预览弹窗；后端仍负责路径安全校验。
   */
  const handlePreviewWorkspaceFile = async (
    file: WorkspaceFile,
  ): Promise<WorkspaceFileContent> => {
    if (!selectedConversation) {
      throw new Error('请先选择一个会话')
    }

    try {
      const fileContent = await apiClient.getWorkspaceFileContent(
        selectedConversation.workspace_id,
        file.path,
      )
      setError(null)
      return fileContent
    } catch (caughtError) {
      const message =
        caughtError instanceof Error ? caughtError.message : '读取文件失败'
      setError(message)
      throw new Error(message)
    }
  }

  /**
   * 删除当前 workspace 文件。
   * 删除成功后刷新 preview、文件列表和变更历史，保持右侧面板同步。
   */
  const handleDeleteWorkspaceFile = async (file: WorkspaceFile) => {
    if (!selectedConversation) {
      throw new Error('请先选择一个会话')
    }

    setDeletingWorkspaceFilePath(file.path)

    try {
      await apiClient.deleteWorkspaceFile(
        selectedConversation.workspace_id,
        file.path,
      )
      const [nextPreview, nextWorkspaceFiles, nextAppliedDiffRecords] =
        await Promise.all([
          apiClient.getWorkspacePreview(selectedConversation.workspace_id),
          apiClient.listWorkspaceFiles(selectedConversation.workspace_id),
          apiClient.listAppliedDiffs(selectedConversation.workspace_id),
        ])
      setPreview(nextPreview)
      setWorkspaceFiles(nextWorkspaceFiles)
      setAppliedDiffRecords(nextAppliedDiffRecords)
      setAppliedDiffIds(getAppliedDiffIds(nextAppliedDiffRecords))
      setError(null)
    } catch (caughtError) {
      const message =
        caughtError instanceof Error ? caughtError.message : '删除文件失败'
      setError(message)
      throw new Error(message)
    } finally {
      setDeletingWorkspaceFilePath(null)
    }
  }

  /**
   * 在当前会话中发送用户消息。
   * 保存用户消息后，由 FastAPI 后端识别 @Agent 并完成 Agent 编排。
   */
  const handleSendMessage = async (content: string) => {
    if (!selectedConversation) {
      throw new Error('请先选择一个会话')
    }

    const conversationId = selectedConversation.id
    const workspaceId = selectedConversation.workspace_id
    if (agentRunningByConversationId[conversationId]) {
      throw new Error('当前会话已有 Agent 正在回复')
    }

    setConversationRunning(conversationId, true)
    setConversationHarnessStatus(conversationId, '正在连接 AgentHub harness...')

    try {
      const draftIds = new Map<string, string>()
      const deltaChains = new Map<string, Promise<void>>()
      const animatedTasks: Promise<void>[] = []
      let draftCounter = 0
      let shouldRefreshPreview = false

      const ensureDraft = (agentId: string) => {
        const existingId = draftIds.get(agentId)
        if (existingId) {
          return existingId
        }
        draftCounter += 1
        const draftId = `draft-${agentId}-${Date.now()}-${draftCounter}`
        draftIds.set(agentId, draftId)
        setConversationMessages(conversationId, (currentMessages) => [
          ...currentMessages,
          createDraftMessage(draftId, conversationId, agentId),
        ])
        return draftId
      }

      const updateConversationTimestamp = (message: Message) => {
        setConversations((currentConversations) =>
          sortConversationsByUpdatedAt(
            currentConversations.map((conversation) =>
              conversation.id === conversationId
                ? { ...conversation, updated_at: message.created_at }
                : conversation,
            ),
          ),
        )
      }

      const appendAnimatedDelta = (agentId: string, delta: string) => {
        const draftId = ensureDraft(agentId)
        const previousChain = deltaChains.get(agentId) ?? Promise.resolve()
        const nextChain = previousChain.then(async () => {
          for (const chunk of splitVisualDelta(delta)) {
            setConversationMessages(conversationId, (currentMessages) =>
              currentMessages.map((message) =>
                message.id === draftId
                  ? {
                      ...message,
                      content: message.content + chunk,
                    }
                  : message,
              ),
            )
            await sleep(STREAM_VISUAL_DELAY_MS)
          }
        })
        deltaChains.set(agentId, nextChain)
        animatedTasks.push(nextChain)
      }

      const finalizeAgentMessage = (message: Message) => {
        const previousChain =
          deltaChains.get(message.sender_id) ?? Promise.resolve()
        const nextChain = previousChain.then(() => {
          const draftId = draftIds.get(message.sender_id)
          setConversationMessages(conversationId, (currentMessages) => {
            if (!draftId) {
              return [...currentMessages, message]
            }
            return currentMessages.map((currentMessage) =>
              currentMessage.id === draftId ? message : currentMessage,
            )
          })
          draftIds.delete(message.sender_id)
          updateConversationTimestamp(message)
        })
        deltaChains.set(message.sender_id, nextChain)
        animatedTasks.push(nextChain)
      }

      const handleStreamEvent = (event: MessageStreamEvent) => {
        if (event.event === 'user_message') {
          setConversationMessages(conversationId, (currentMessages) => [
            ...currentMessages,
            event.data.message,
          ])
          updateConversationTimestamp(event.data.message)
          return
        }

        if (event.event === 'harness_step') {
          setConversationHarnessStatus(
            conversationId,
            event.data.message ?? event.data.status,
          )
          return
        }

        if (event.event === 'agent_started') {
          ensureDraft(event.data.agent_id)
          return
        }

        if (event.event === 'agent_delta') {
          appendAnimatedDelta(event.data.agent_id, event.data.delta)
          return
        }

        if (event.event === 'artifact') {
          const draftId = ensureDraft(event.data.agent_id)
          setConversationMessages(conversationId, (currentMessages) =>
            currentMessages.map((message) =>
              message.id === draftId
                ? {
                    ...message,
                    artifacts: [...message.artifacts, event.data.artifact],
                  }
                : message,
            ),
          )
          return
        }

        if (event.event === 'agent_done') {
          const message = event.data.message
          shouldRefreshPreview =
            shouldRefreshPreview || message.artifacts.some((artifact) => artifact.type === 'preview')
          finalizeAgentMessage(message)
          return
        }

        if (event.event === 'error') {
          setError(event.data.message)
          return
        }

        if (event.event === 'done') {
          shouldRefreshPreview =
            shouldRefreshPreview ||
            hasPreviewArtifact(event.data.agent_messages ?? [])
        }
      }

      await apiClient.streamMessage(
        conversationId,
        {
          sender_id: 'user',
          content,
        },
        handleStreamEvent,
      )
      await Promise.all(animatedTasks)

      if (shouldRefreshPreview) {
        const nextPreview = await apiClient.getWorkspacePreview(workspaceId)
        if (selectedConversationIdRef.current === conversationId) {
          setPreview(nextPreview)
        }
      }

      setError(null)
    } catch (caughtError) {
      setError(
        caughtError instanceof Error ? caughtError.message : 'Agent 回复失败',
      )
    } finally {
      setConversationRunning(conversationId, false)
      setConversationHarnessStatus(conversationId, null)
    }
  }

  return (
    <ConfigProvider
      theme={{
        algorithm: theme.defaultAlgorithm,
        token: {
          borderRadius: 8,
          colorPrimary: '#235b54',
          colorInfo: '#235b54',
          fontFamily:
            'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
        },
      }}
    >
      <AppLayout
        sidebar={
          <>
            {/* 品牌区：只展示产品身份，不承担数据逻辑。 */}
            <div className="brand-block">
              <div className="brand-mark">A</div>
              <div>
                <strong>AgentHub</strong>
                <span>Multi-Agent Workspace</span>
              </div>
            </div>
            {/* 左侧上半区：会话列表、搜索和新建入口。 */}
            <ConversationList
              conversations={filteredConversations}
              selectedConversationId={selectedConversationId}
              searchTerm={conversationSearchTerm}
              onOpenNewConversation={() => setNewConversationOpen(true)}
              onDeleteConversation={handleDeleteConversation}
              onSearchTermChange={setConversationSearchTerm}
              onSelectConversation={setSelectedConversationId}
              onTogglePinConversation={handleTogglePinConversation}
            />
            {/* 左侧下半区：可用 Agent 联系人和能力标签。 */}
            <AgentList agents={agents} />
          </>
        }
        main={
          <>
            {/* 页面级错误兜底，避免接口失败时静默空白。 */}
            {error ? (
              <Alert
                className="error-banner"
                closable
                onClose={() => setError(null)}
                showIcon
                title={error}
                type="error"
              />
            ) : null}
            {mockAgentWarning ? (
              <Alert
                className="error-banner"
                showIcon
                title={mockAgentWarning}
                type="warning"
              />
            ) : null}
            {/* 中间主区域：当前会话的消息流和消息输入。 */}
            <ChatPanel
              agents={agents}
              availableAgents={selectedConversationAgents}
              conversation={selectedConversation}
              agentRunning={selectedAgentRunning}
              appliedDiffIds={appliedDiffIds}
              applyingDiffId={applyingDiffId}
              harnessStatus={selectedHarnessStatus}
              loading={loadingMessages && selectedMessages.length === 0}
              messages={selectedMessages}
              workspacePreviewUrl={preview?.preview_url ?? null}
              onApplyDiff={handleApplyDiff}
              onOpenMemberManager={() => setMemberManagerOpen(true)}
              onSendMessage={handleSendMessage}
            />
          </>
        }
        aside={
          /* 右侧 Workspace 区：展示预览、文件和已应用 Diff 历史。 */
          <WorkspacePanel
            appliedDiffs={appliedDiffRecords}
            conversation={selectedConversation}
            deletingFilePath={deletingWorkspaceFilePath}
            files={workspaceFiles}
            preview={preview}
            revertingDiffRecordId={revertingDiffRecordId}
            getFilePreviewUrl={(path) =>
              selectedConversation
                ? apiClient.getWorkspacePreviewPageUrl(
                    selectedConversation.workspace_id,
                    path,
                  )
                : ''
            }
            onDeleteFile={handleDeleteWorkspaceFile}
            onPreviewFile={handlePreviewWorkspaceFile}
            onRevertAppliedDiff={handleRevertAppliedDiff}
          />
        }
      />
      <NewConversationModal
        agents={agents}
        open={newConversationOpen}
        onClose={() => setNewConversationOpen(false)}
        onCreateConversation={handleCreateConversation}
      />
      <ConversationMembersModal
        agents={agents}
        conversation={selectedConversation}
        open={memberManagerOpen}
        onClose={() => setMemberManagerOpen(false)}
        onUpdateMembers={handleUpdateConversationMembers}
      />
    </ConfigProvider>
  )
}

export default App
