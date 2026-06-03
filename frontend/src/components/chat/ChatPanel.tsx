import { useEffect, useRef } from 'react'
import { TeamOutlined } from '@ant-design/icons'
import { Avatar, Button, Empty, Spin, Tag } from 'antd'
import type { Agent, Artifact, Conversation, Message } from '../../types/api'
import { MarkdownMessage } from './MarkdownMessage'
import { MessageArtifactActions } from './MessageArtifactActions'
import { MessageComposer } from './MessageComposer'

/** 聊天主面板组件的入参。 */
type ChatPanelProps = {
  /** Agent 列表，用于把 message.sender_id 翻译成可读名称。 */
  agents: Agent[]
  /** 当前会话成员 Agent；输入框和 @ 菜单只能使用这批 Agent。 */
  availableAgents: Agent[]
  /** 当前会话；为空时展示空状态。 */
  conversation: Conversation | null
  /** 当前会话消息流。 */
  messages: Message[]
  /** 消息和 preview 加载状态。 */
  loading: boolean
  /** Agent 是否正在生成回复。 */
  agentRunning: boolean
  /** 已经成功应用的 diff artifact ID 集合。 */
  appliedDiffIds: ReadonlySet<string>
  /** 当前正在应用的 diff artifact ID。 */
  applyingDiffId: string | null
  /** 点击 Apply Diff 时调用，父组件负责请求 API 和刷新 Preview。 */
  onApplyDiff: (artifact: Artifact, diff: string) => Promise<void>
  /** 用户发送消息时调用，父组件负责创建 Message 并刷新状态。 */
  onSendMessage: (content: string) => Promise<void>
  /** 打开当前会话成员管理弹窗。 */
  onOpenMemberManager: () => void
}

/**
 * 根据 sender_id 获取消息发送者名称。
 * user 是前端固定发送者；Agent 消息用 agents 表查展示名称，查不到时回退 ID。
 */
const getSenderName = (senderId: string, agents: Agent[]) => {
  if (senderId === 'user') {
    return 'You'
  }
  return agents.find((agent) => agent.id === senderId)?.name ?? senderId
}

/** 生成消息头像首字母；用户固定 Y，Agent 使用名称首字母。 */
const getSenderInitial = (senderId: string, agents: Agent[]) =>
  getSenderName(senderId, agents).slice(0, 1).toUpperCase()

/** 把 ISO 时间格式化为聊天气泡中的时分。 */
const formatTime = (value: string) =>
  new Intl.DateTimeFormat('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))

/**
 * 中间聊天主界面。
 * 负责展示会话头、消息流、Artifact 内联卡片、生成中状态和消息输入。
 */
export function ChatPanel({
  agents,
  availableAgents,
  conversation,
  messages,
  loading,
  agentRunning,
  appliedDiffIds,
  applyingDiffId,
  onApplyDiff,
  onSendMessage,
  onOpenMemberManager,
}: ChatPanelProps) {
  // messageListRef 用于第六天的演示体验：新消息和 Agent 生成状态出现时自动滚动到底部。
  const messageListRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    messageListRef.current?.scrollTo({
      top: messageListRef.current.scrollHeight,
      behavior: 'smooth',
    })
  }, [messages, agentRunning, loading])

  // 没有选中会话时不展示旧消息，避免用户误以为仍在上一个会话。
  if (!conversation) {
    return (
      <section className="chat-panel empty-panel">
        <Empty description="暂无会话" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      </section>
    )
  }

  return (
    <section className="chat-panel">
      {/* 会话头：展示当前会话标题和绑定 workspace，帮助用户理解产物归属。 */}
      <header className="chat-header">
        <div>
          <p className="eyebrow">AgentHub Demo</p>
          <h1>{conversation.title}</h1>
        </div>
        <div className="chat-header-actions">
          {/* 成员数量来自 conversation.agent_ids，用于提示当前会话的 @Agent 边界。 */}
          <Tag className="member-count-tag">{availableAgents.length} Agents</Tag>
          <Button
            className="secondary-button member-manage-button"
            icon={<TeamOutlined />}
            onClick={onOpenMemberManager}
            size="small"
          >
            管理成员
          </Button>
          <span className="workspace-badge">{conversation.workspace_id}</span>
        </div>
      </header>

      <div className="message-list" ref={messageListRef}>
        {loading ? (
          <Spin className="loading-state" tip="加载消息中..." />
        ) : messages.length === 0 ? (
          <Empty
            className="empty-chat-state"
            description="使用下方 Demo Prompt 或输入 @Agent 开始协作。"
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        ) : (
          messages.map((message) => (
            <article
              // role 直接进入 className，用于区分 user/agent/system 气泡样式。
              className={`message-bubble message-${message.role}`}
              key={message.id}
            >
              <Avatar className="message-avatar" shape="square">
                {getSenderInitial(message.sender_id, agents)}
              </Avatar>
              <div className="message-meta">
                <span>{getSenderName(message.sender_id, agents)}</span>
                <time dateTime={message.created_at}>
                  {formatTime(message.created_at)}
                </time>
              </div>
              <MarkdownMessage content={message.content} />
              <MessageArtifactActions
                appliedDiffIds={appliedDiffIds}
                applyingDiffId={applyingDiffId}
                artifacts={message.artifacts}
                onApplyDiff={onApplyDiff}
              />
            </article>
          ))
        )}
        {agentRunning ? (
          <article className="message-bubble message-system">
            <Avatar className="message-avatar" shape="square">
              A
            </Avatar>
            <div className="message-meta">
              <span>AgentHub</span>
              <span>生成中</span>
            </div>
            <p>
              Agent 正在根据 @Agent 路由生成回复
              <span className="typing-dots" aria-hidden="true">
                ...
              </span>
            </p>
          </article>
        ) : null}
      </div>

      <footer className="composer-shell">
        {/* 第二天接入真实输入组件；第三天会在此基础上增加 @Agent 菜单和 Agent 回复。 */}
        <MessageComposer
          agents={availableAgents}
          disabled={!conversation || agentRunning}
          onSendMessage={onSendMessage}
        />
      </footer>
    </section>
  )
}
