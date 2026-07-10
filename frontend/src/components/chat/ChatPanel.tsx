import { useEffect, useRef } from 'react'
import {
  CopyOutlined,
  DeleteOutlined,
  PushpinFilled,
  PushpinOutlined,
  RedoOutlined,
  RollbackOutlined,
  TeamOutlined,
} from '@ant-design/icons'
import { Avatar, Button, Empty, Popconfirm, Spin, Tag, Tooltip } from 'antd'
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
  /** 输入框当前引用的消息。 */
  replyTarget: Message | null
  /** 消息和 preview 加载状态。 */
  loading: boolean
  /** 当前会话是否仍有流式请求在进行，用于禁用输入。 */
  agentRunning: boolean
  /** 当前生成提示；只控制底部黄色状态卡片展示。 */
  generationNotice: string | null
  /** 当前 workspace 的可打开 preview URL。 */
  workspacePreviewUrl?: string | null
  /** 已经成功应用的 diff artifact ID 集合。 */
  appliedDiffIds: ReadonlySet<string>
  /** 当前正在应用的 diff artifact ID。 */
  applyingDiffId: string | null
  /** 点击 Apply Diff 时调用，父组件负责请求 API 和刷新 Preview。 */
  onApplyDiff: (artifact: Artifact, diff: string) => Promise<void>
  /** 用户发送消息时调用，父组件负责创建 Message 并刷新状态。 */
  onSendMessage: (content: string, replyToId?: string | null) => Promise<void>
  /** 引用某条消息。 */
  onReplyToMessage: (message: Message) => void
  /** 取消输入框引用态。 */
  onCancelReply: () => void
  /** 复制消息内容。 */
  onCopyMessage: (message: Message) => Promise<void>
  /** 基于用户消息重新生成 Agent 回复。 */
  onRegenerateMessage: (message: Message) => Promise<void>
  /** Pin/Unpin 长期上下文。 */
  onToggleMessagePin: (message: Message, nextPinned: boolean) => Promise<void>
  /** 软删除消息。 */
  onDeleteMessage: (message: Message) => Promise<void>
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
  replyTarget,
  loading,
  agentRunning,
  generationNotice,
  workspacePreviewUrl,
  appliedDiffIds,
  applyingDiffId,
  onApplyDiff,
  onSendMessage,
  onReplyToMessage,
  onCancelReply,
  onCopyMessage,
  onRegenerateMessage,
  onToggleMessagePin,
  onDeleteMessage,
  onOpenMemberManager,
}: ChatPanelProps) {
  // messageListRef 用于第六天的演示体验：新消息和 Agent 生成状态出现时自动滚动到底部。
  const messageListRef = useRef<HTMLDivElement | null>(null)
  const messageEndRef = useRef<HTMLDivElement | null>(null)
  const lastMessage = messages[messages.length - 1]
  const lastMessageContentLength = lastMessage?.content.length ?? 0

  useEffect(() => {
    messageEndRef.current?.scrollIntoView({
      block: 'end',
      behavior: 'smooth',
    })
  }, [
    messages.length,
    lastMessage?.id,
    lastMessageContentLength,
    agentRunning,
    generationNotice,
    loading,
  ])

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
          <Spin className="loading-state" description="加载消息中..." />
        ) : messages.length === 0 ? (
          <Empty
            className="empty-chat-state"
            description="输入开发需求，或使用 @Agent 指定当前会话成员开始协作。"
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        ) : (
          messages.map((message) => {
            const isDeleted = Boolean(message.deleted_at)
            const replySource = message.reply_to_id
              ? messages.find((item) => item.id === message.reply_to_id)
              : null
            return (
              <article
                // role 直接进入 className，用于区分 user/agent/system 气泡样式。
                className={`message-bubble message-${message.role}${
                  isDeleted ? ' is-deleted' : ''
                }`}
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
                  <div className="message-actions">
                    <Tooltip title="回复">
                      <Button
                        aria-label="回复消息"
                        className="message-action-button"
                        disabled={isDeleted}
                        icon={<RollbackOutlined />}
                        onClick={() => onReplyToMessage(message)}
                        size="small"
                        type="text"
                      />
                    </Tooltip>
                    <Tooltip title="复制">
                      <Button
                        aria-label="复制消息"
                        className="message-action-button"
                        disabled={isDeleted}
                        icon={<CopyOutlined />}
                        onClick={() => void onCopyMessage(message)}
                        size="small"
                        type="text"
                      />
                    </Tooltip>
                    {message.role === 'user' ? (
                      <Tooltip title="重新生成">
                        <Button
                          aria-label="重新生成"
                          className="message-action-button"
                          disabled={isDeleted || agentRunning}
                          icon={<RedoOutlined />}
                          onClick={() => void onRegenerateMessage(message)}
                          size="small"
                          type="text"
                        />
                      </Tooltip>
                    ) : null}
                    <Tooltip
                      title={
                        message.is_context_pinned
                          ? '取消长期上下文'
                          : '固定为长期上下文'
                      }
                    >
                      <Button
                        aria-label={
                          message.is_context_pinned
                            ? '取消长期上下文'
                            : '固定为长期上下文'
                        }
                        className="message-action-button"
                        disabled={isDeleted}
                        icon={
                          message.is_context_pinned ? (
                            <PushpinFilled />
                          ) : (
                            <PushpinOutlined />
                          )
                        }
                        onClick={() =>
                          void onToggleMessagePin(
                            message,
                            !message.is_context_pinned,
                          )
                        }
                        size="small"
                        type="text"
                      />
                    </Tooltip>
                    <Popconfirm
                      cancelText="取消"
                      description="删除后会保留时间线位置，但隐藏正文和产物。"
                      okButtonProps={{ danger: true }}
                      okText="删除"
                      onConfirm={() => void onDeleteMessage(message)}
                      title="删除消息？"
                    >
                      <Button
                        aria-label="删除消息"
                        className="message-action-button"
                        danger
                        disabled={isDeleted}
                        icon={<DeleteOutlined />}
                        size="small"
                        type="text"
                      />
                    </Popconfirm>
                  </div>
                </div>
                {replySource ? (
                  <blockquote className="message-reply-preview">
                    {getSenderName(replySource.sender_id, agents)}：
                    {replySource.deleted_at
                      ? '消息已删除'
                      : replySource.content.slice(0, 80)}
                  </blockquote>
                ) : null}
                {isDeleted ? (
                  <p className="message-deleted-text">消息已删除</p>
                ) : (
                  <>
                    <MarkdownMessage content={message.content} />
                    <MessageArtifactActions
                      appliedDiffIds={appliedDiffIds}
                      applyingDiffId={applyingDiffId}
                      artifacts={message.artifacts}
                      workspacePreviewUrl={workspacePreviewUrl}
                      onApplyDiff={onApplyDiff}
                    />
                  </>
                )}
              </article>
            )
          })
        )}
        {generationNotice ? (
          <article className="message-bubble message-system message-generation">
            <Avatar className="message-avatar" shape="square">
              A
            </Avatar>
            <div className="message-meta">
              <span>AgentHub</span>
              <span>生成中</span>
            </div>
            <p>
              {generationNotice}
              <span className="typing-dots" aria-hidden="true">
                ...
              </span>
            </p>
          </article>
        ) : null}
        <div ref={messageEndRef} />
      </div>

      <footer className="composer-shell">
        {/* 第二天接入真实输入组件；第三天会在此基础上增加 @Agent 菜单和 Agent 回复。 */}
        <MessageComposer
          agents={availableAgents}
          disabled={!conversation || agentRunning}
          replyTarget={replyTarget}
          onCancelReply={onCancelReply}
          onSendMessage={onSendMessage}
        />
      </footer>
    </section>
  )
}
