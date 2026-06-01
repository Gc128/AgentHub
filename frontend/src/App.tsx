import { useEffect, useMemo, useState } from 'react'
import { apiClient } from './api/client'
import { AgentList } from './components/agents/AgentList'
import { ArtifactPanel } from './components/artifactCards/ArtifactPanel'
import { ChatPanel } from './components/chat/ChatPanel'
import { ConversationList } from './components/conversations/ConversationList'
import { NewConversationModal } from './components/conversations/NewConversationModal'
import { AppLayout } from './components/layout/AppLayout'
import type {
  Agent,
  AgentRunResult,
  Artifact,
  Conversation,
  CreateConversationInput,
  Message,
  WorkspacePreview,
} from './types/api'
import { resolveAgentRunOrder } from './utils/agentRouting'
import './App.css'

/** 会话按最近更新时间倒序排序，保持 IM 左侧列表的常见体验。 */
const sortConversationsByUpdatedAt = (items: Conversation[]) =>
  [...items].sort(
    (left, right) =>
      new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime(),
  )

/**
 * 判断 Agent 返回结果是否携带 preview artifact。
 * 如果有，前端会重新拉取 workspace preview，保持右侧状态和聊天产物一致。
 */
const hasPreviewArtifact = (result: AgentRunResult) =>
  result.artifacts.some((artifact) => artifact.type === 'preview')

/**
 * AgentHub 前端根组件。
 * 这里负责把首日 Demo 的核心数据串起来：会话列表、聊天消息、Agent 联系人和右侧产物预览。
 */
function App() {
  // 可用 Agent 列表，来自 apiClient；当前默认走 mock，后续可切到真实 /api。
  const [agents, setAgents] = useState<Agent[]>([])
  // 左侧会话列表，Conversation 字段严格对齐后端 schema。
  const [conversations, setConversations] = useState<Conversation[]>([])
  // 当前选中的会话 ID；用 ID 而不是对象，方便列表刷新后重新计算选中会话。
  const [selectedConversationId, setSelectedConversationId] = useState<
    string | null
  >(null)
  // 当前会话的消息列表；切换会话时会重新加载。
  const [messages, setMessages] = useState<Message[]>([])
  // 当前会话 workspace 的预览状态，用于右侧 ArtifactPanel 顶部状态卡。
  const [preview, setPreview] = useState<WorkspacePreview | null>(null)
  // 消息区 loading 状态，只作用于当前会话消息和 preview 加载。
  const [loadingMessages, setLoadingMessages] = useState(false)
  // 会话搜索关键词；搜索接口文档未明确，第二天先做前端本地过滤。
  const [conversationSearchTerm, setConversationSearchTerm] = useState('')
  // 控制新建会话弹窗是否打开。
  const [newConversationOpen, setNewConversationOpen] = useState(false)
  // mock Agent 回复生成状态；生成中禁用输入框并展示一条系统态消息。
  const [agentRunning, setAgentRunning] = useState(false)
  // 已成功应用的 diff artifact ID；聊天流和右侧产物栏共享这份状态。
  const [appliedDiffIds, setAppliedDiffIds] = useState<ReadonlySet<string>>(
    () => new Set(),
  )
  // 当前正在应用的 diff artifact ID；用于让同一张卡片展示“应用中”。
  const [applyingDiffId, setApplyingDiffId] = useState<string | null>(null)
  // 页面级错误提示；首日先集中展示，后续可以拆成更细的错误状态。
  const [error, setError] = useState<string | null>(null)

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
        // 默认选中最近活跃的第一条会话，mock API 已按 updated_at 倒序返回。
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

  useEffect(() => {
    // 没有选中会话时清空中间消息区和右侧预览，避免展示上一个会话的数据。
    if (!selectedConversation) {
      setMessages([])
      setPreview(null)
      return
    }

    let ignore = false
    setLoadingMessages(true)

    /**
     * 切换会话后的数据加载：
     * 消息流和 workspace preview 都依赖当前会话，所以放在同一个 effect 中同步刷新。
     */
    const loadConversationData = async () => {
      try {
        const [nextMessages, nextPreview] = await Promise.all([
          apiClient.listMessages(selectedConversation.id),
          apiClient.getWorkspacePreview(selectedConversation.workspace_id),
        ])

        if (ignore) {
          return
        }

        setMessages(nextMessages)
        setPreview(nextPreview)
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
   * 从当前消息流中提取所有 Artifact，交给右侧面板集中展示。
   * 聊天气泡内仍保留 artifact 摘要，右侧面板负责跨消息聚合。
   */
  const artifacts = useMemo(
    () => messages.flatMap((message) => message.artifacts),
    [messages],
  )

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
   * 把 AgentRunResult 保存为聊天消息。
   * 这里仍走 createMessage，让 mock 内存消息表和前端状态保持一致。
   */
  const appendAgentResult = async (
    conversationId: string,
    result: AgentRunResult,
  ) => {
    const message = await apiClient.createMessage(conversationId, {
      sender_id: result.agent_id,
      content: result.content,
      artifacts: result.artifacts,
    })

    setMessages((currentMessages) => [...currentMessages, message])
    return message
  }

  /**
   * 应用某个 Diff Artifact。
   * 这是第五天的关键闭环：Diff 卡片按钮 → mock apply-diff → workspace preview 刷新。
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
      setPreview(nextPreview)
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
   * 在当前会话中发送用户消息。
   * 第三天在保存用户消息后，会根据 @Agent 或关键词触发 mock Agent 回复。
   */
  const handleSendMessage = async (content: string) => {
    if (!selectedConversation) {
      throw new Error('请先选择一个会话')
    }

    setAgentRunning(true)

    try {
      const message = await apiClient.createMessage(selectedConversation.id, {
        sender_id: 'user',
        content,
      })

      setMessages((currentMessages) => [...currentMessages, message])
      setConversations((currentConversations) =>
        sortConversationsByUpdatedAt(
          currentConversations.map((conversation) =>
            conversation.id === selectedConversation.id
              ? { ...conversation, updated_at: message.created_at }
              : conversation,
          ),
        ),
      )

      const agentRunOrder = resolveAgentRunOrder(content, agents)
      let hasPreviewUpdate = false

      for (const agentId of agentRunOrder) {
        const result = await apiClient.runAgent({
          conversation_id: selectedConversation.id,
          workspace_id: selectedConversation.workspace_id,
          user_message: content,
          history: [...messages, message],
          context: {
            agent_id: agentId,
          },
        })

        await appendAgentResult(selectedConversation.id, result)
        hasPreviewUpdate = hasPreviewUpdate || hasPreviewArtifact(result)
      }

      if (hasPreviewUpdate) {
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
    <>
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
              onSearchTermChange={setConversationSearchTerm}
              onSelectConversation={setSelectedConversationId}
            />
            {/* 左侧下半区：可用 Agent 联系人和能力标签。 */}
            <AgentList agents={agents} />
          </>
        }
        main={
          <>
            {/* 页面级错误兜底，避免接口失败时静默空白。 */}
            {error ? (
              <div className="error-banner">
                <span>{error}</span>
                <button
                  className="error-dismiss"
                  onClick={() => setError(null)}
                  type="button"
                  aria-label="关闭错误提示"
                >
                  ×
                </button>
              </div>
            ) : null}
            {/* 中间主区域：当前会话的消息流和消息输入。 */}
            <ChatPanel
              agents={agents}
              conversation={selectedConversation}
              agentRunning={agentRunning}
              appliedDiffIds={appliedDiffIds}
              applyingDiffId={applyingDiffId}
              loading={loadingMessages}
              messages={messages}
              onApplyDiff={handleApplyDiff}
              onSendMessage={handleSendMessage}
            />
          </>
        }
        aside={
          /* 右侧产物区：聚合当前会话所有 artifacts，并展示 workspace preview 状态。 */
          <ArtifactPanel
            appliedDiffIds={appliedDiffIds}
            applyingDiffId={applyingDiffId}
            artifacts={artifacts}
            conversation={selectedConversation}
            onApplyDiff={handleApplyDiff}
            preview={preview}
          />
        }
      />
      <NewConversationModal
        agents={agents}
        open={newConversationOpen}
        onClose={() => setNewConversationOpen(false)}
        onCreateConversation={handleCreateConversation}
      />
    </>
  )
}

export default App
