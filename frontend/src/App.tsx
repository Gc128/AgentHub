import { useCallback, useEffect, useMemo, useState } from 'react'
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
  AppliedDiffRecord,
  Artifact,
  Conversation,
  CreateConversationInput,
  Message,
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
  new Set(records.map((record) => record.artifact_id))

/** 会话模式由成员数量推导，避免 UI 手动选择后和 agent_ids 语义不一致。 */
const inferConversationMode = (agentIds: string[]): ConversationMode =>
  agentIds.length > 1 ? 'group' : 'single'

/**
 * AgentHub 前端根组件。
 * 这里负责把首日 Demo 的核心数据串起来：会话列表、聊天消息、Agent 联系人和右侧产物预览。
 */
function App() {
  // 可用 Agent 列表，来自 FastAPI 后端 /api/agents。
  const [agents, setAgents] = useState<Agent[]>([])
  // 左侧会话列表，Conversation 字段严格对齐后端 schema。
  const [conversations, setConversations] = useState<Conversation[]>([])
  // 当前选中的会话 ID；用 ID 而不是对象，方便列表刷新后重新计算选中会话。
  const [selectedConversationId, setSelectedConversationId] = useState<
    string | null
  >(null)
  // 当前会话的消息列表；切换会话时会重新加载。
  const [messages, setMessages] = useState<Message[]>([])
  // 当前会话 workspace 的预览状态，用于右侧 Workspace 面板。
  const [preview, setPreview] = useState<WorkspacePreview | null>(null)
  // 当前 workspace 文件列表。
  const [workspaceFiles, setWorkspaceFiles] = useState<WorkspaceFile[]>([])
  // 当前 workspace 展示刷新版本号，用于让 iframe 预览在应用内变更后重新挂载。
  const [workspaceRefreshToken, setWorkspaceRefreshToken] = useState(0)
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
  // Agent 回复生成状态；生成中禁用输入框并展示一条系统态消息。
  const [agentRunning, setAgentRunning] = useState(false)
  // 已成功应用的 diff artifact ID；聊天流和右侧产物栏共享这份状态。
  const [appliedDiffIds, setAppliedDiffIds] = useState<ReadonlySet<string>>(
    () => new Set(),
  )
  // 当前正在应用的 diff artifact ID；用于让同一张卡片展示“应用中”。
  const [applyingDiffId, setApplyingDiffId] = useState<string | null>(null)
  // 当前正在删除的 workspace 文件路径，用于文件行按钮 loading。
  const [deletingWorkspaceFilePath, setDeletingWorkspaceFilePath] = useState<
    string | null
  >(null)
  // 页面级错误提示；首日先集中展示，后续可以拆成更细的错误状态。
  const [error, setError] = useState<string | null>(null)

  const bumpWorkspaceRefreshToken = () => {
    setWorkspaceRefreshToken((currentToken) => currentToken + 1)
  }

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
        const [nextConversations, nextAgents] = await Promise.all([
          apiClient.listConversations(),
          apiClient.listAgents(),
        ])

        if (ignore) {
          return
        }

        setConversations(nextConversations)
        setAgents(nextAgents)
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

  useEffect(() => {
    // 没有选中会话时清空中间消息区和右侧预览，避免展示上一个会话的数据。
    if (!selectedConversation) {
      setMessages([])
      setPreview(null)
      setWorkspaceFiles([])
      setAppliedDiffRecords([])
      setAppliedDiffIds(new Set())
      bumpWorkspaceRefreshToken()
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

        setMessages(nextMessages)
        setPreview(nextPreview)
        setWorkspaceFiles(nextWorkspaceFiles)
        setAppliedDiffRecords(nextAppliedDiffRecords)
        setAppliedDiffIds(getAppliedDiffIds(nextAppliedDiffRecords))
        bumpWorkspaceRefreshToken()
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
  }, [selectedConversation])

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

      const nextPreview = await apiClient.getWorkspacePreview(
        selectedConversation.workspace_id,
      )
      const [nextWorkspaceFiles, nextAppliedDiffRecords] = await Promise.all([
        apiClient.listWorkspaceFiles(selectedConversation.workspace_id),
        apiClient.listAppliedDiffs(selectedConversation.workspace_id),
      ])
      setPreview(nextPreview)
      setWorkspaceFiles(nextWorkspaceFiles)
      setAppliedDiffRecords(nextAppliedDiffRecords)
      setAppliedDiffIds(getAppliedDiffIds(nextAppliedDiffRecords))
      bumpWorkspaceRefreshToken()
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

  /**
   * 读取当前 workspace 文件内容。
   * WorkspacePanel 用它打开预览弹窗；后端仍负责路径安全校验。
   */
  const handlePreviewWorkspaceFile = useCallback(async (
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
  }, [selectedConversation])

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
      bumpWorkspaceRefreshToken()
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

    setAgentRunning(true)

    try {
      const response = await apiClient.sendMessage(selectedConversation.id, {
        sender_id: 'user',
        content,
      })
      const nextConversationMessages = [
        response.user_message,
        ...response.agent_messages,
      ]

      setMessages((currentMessages) => [
        ...currentMessages,
        ...nextConversationMessages,
      ])
      const lastMessage =
        nextConversationMessages[nextConversationMessages.length - 1] ??
        response.user_message
      setConversations((currentConversations) =>
        sortConversationsByUpdatedAt(
          currentConversations.map((conversation) =>
            conversation.id === selectedConversation.id
              ? { ...conversation, updated_at: lastMessage.created_at }
              : conversation,
          ),
        ),
      )

      if (hasPreviewArtifact(response.agent_messages)) {
        const nextPreview = await apiClient.getWorkspacePreview(
          selectedConversation.workspace_id,
        )
        setPreview(nextPreview)
      }

      setError(null)
    } catch (caughtError) {
      setError(
        caughtError instanceof Error ? caughtError.message : 'Agent 回复失败',
      )
    } finally {
      setAgentRunning(false)
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
            {/* 中间主区域：当前会话的消息流和消息输入。 */}
            <ChatPanel
              agents={agents}
              availableAgents={selectedConversationAgents}
              conversation={selectedConversation}
              agentRunning={agentRunning}
              appliedDiffIds={appliedDiffIds}
              applyingDiffId={applyingDiffId}
              loading={loadingMessages}
              messages={messages}
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
            key={selectedConversation?.workspace_id ?? 'no-workspace'}
            preview={preview}
            workspaceRefreshToken={workspaceRefreshToken}
            onDeleteFile={handleDeleteWorkspaceFile}
            onPreviewFile={handlePreviewWorkspaceFile}
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
