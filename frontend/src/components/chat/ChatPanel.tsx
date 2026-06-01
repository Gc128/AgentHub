import type { Agent, Conversation, Message } from '../../types/api'
import { MessageComposer } from './MessageComposer'

/** 聊天主面板组件的入参。 */
type ChatPanelProps = {
  /** Agent 列表，用于把 message.sender_id 翻译成可读名称。 */
  agents: Agent[]
  /** 当前会话；为空时展示空状态。 */
  conversation: Conversation | null
  /** 当前会话消息流。 */
  messages: Message[]
  /** 消息和 preview 加载状态。 */
  loading: boolean
  /** mock Agent 是否正在生成回复。 */
  agentRunning: boolean
  /** 用户发送消息时调用，父组件负责创建 Message 并刷新状态。 */
  onSendMessage: (content: string) => Promise<void>
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

/** 把 ISO 时间格式化为聊天气泡中的时分。 */
const formatTime = (value: string) =>
  new Intl.DateTimeFormat('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))

/**
 * 中间聊天主界面。
 * 首日负责展示会话头、消息列表、Artifact 摘要和输入区占位；发送逻辑在后续任务接入。
 */
export function ChatPanel({
  agents,
  conversation,
  messages,
  loading,
  agentRunning,
  onSendMessage,
}: ChatPanelProps) {
  // 没有选中会话时不展示旧消息，避免用户误以为仍在上一个会话。
  if (!conversation) {
    return (
      <section className="chat-panel empty-panel">
        <p>暂无会话</p>
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
        <span className="workspace-badge">{conversation.workspace_id}</span>
      </header>

      <div className="message-list">
        {loading ? (
          <div className="loading-state">加载消息中...</div>
        ) : (
          messages.map((message) => (
            <article
              // role 直接进入 className，用于区分 user/agent/system 气泡样式。
              className={`message-bubble message-${message.role}`}
              key={message.id}
            >
              <div className="message-meta">
                <span>{getSenderName(message.sender_id, agents)}</span>
                <time dateTime={message.created_at}>
                  {formatTime(message.created_at)}
                </time>
              </div>
              <p>{message.content}</p>
              {message.artifacts.length > 0 ? (
                <div className="message-artifact-strip">
                  {/* 聊天气泡内只放 Artifact 摘要，详细内容由右侧 ArtifactPanel 聚合展示。 */}
                  {message.artifacts.map((artifact) => (
                    <span className="artifact-chip" key={artifact.id}>
                      {artifact.type} / {artifact.title}
                    </span>
                  ))}
                </div>
              ) : null}
            </article>
          ))
        )}
        {agentRunning ? (
          <article className="message-bubble message-system">
            <div className="message-meta">
              <span>AgentHub</span>
              <span>生成中</span>
            </div>
            <p>Mock Agent 正在根据 @Agent 路由生成回复...</p>
          </article>
        ) : null}
      </div>

      <footer className="composer-shell">
        {/* 第二天接入真实输入组件；第三天会在此基础上增加 @Agent 菜单和 Agent 回复。 */}
        <MessageComposer
          agents={agents}
          disabled={!conversation || agentRunning}
          onSendMessage={onSendMessage}
        />
      </footer>
    </section>
  )
}
