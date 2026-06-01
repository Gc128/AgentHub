import type { Conversation } from '../../types/api'

/** 会话列表组件的入参。 */
type ConversationListProps = {
  /** 左侧展示的会话数组，通常已经按 updated_at 倒序排列。 */
  conversations: Conversation[]
  /** 当前选中的会话 ID，用于高亮列表项。 */
  selectedConversationId: string | null
  /** 点击会话时通知父组件切换当前会话。 */
  onSelectConversation: (conversationId: string) => void
}

/** 把 ISO 时间格式化成 IM 列表中更紧凑的时分显示。 */
const formatTime = (value: string) =>
  new Intl.DateTimeFormat('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))

/**
 * 左侧会话列表。
 * 首日只实现展示和切换；新建会话按钮和搜索框先作为第二天功能入口。
 */
export function ConversationList({
  conversations,
  selectedConversationId,
  onSelectConversation,
}: ConversationListProps) {
  return (
    <section className="sidebar-section">
      <div className="section-heading">
        <span>会话</span>
        {/* 第二天会接入 NewConversationModal；现在保留入口按钮。 */}
        <button className="icon-button" type="button" aria-label="新建会话">
          +
        </button>
      </div>

      {/* 搜索接口和过滤逻辑文档未明确，首日先展示静态入口。 */}
      <div className="search-box">搜索会话</div>

      <div className="conversation-list">
        {conversations.map((conversation) => (
          <button
            // 当前选中的会话使用 is-active 高亮，让用户明确聊天区来源。
            className={
              conversation.id === selectedConversationId
                ? 'conversation-item is-active'
                : 'conversation-item'
            }
            key={conversation.id}
            onClick={() => onSelectConversation(conversation.id)}
            type="button"
          >
            <span className="conversation-title">{conversation.title}</span>
            <span className="conversation-meta">
              {/* mode 字段来自后端 schema，前端只做文案映射。 */}
              {conversation.mode === 'group' ? '群聊协作' : '单聊'}
              <span>{formatTime(conversation.updated_at)}</span>
            </span>
          </button>
        ))}
      </div>
    </section>
  )
}
