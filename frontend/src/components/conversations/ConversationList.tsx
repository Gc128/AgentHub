import type { Conversation } from '../../types/api'

/** 会话列表组件的入参。 */
type ConversationListProps = {
  /** 左侧展示的会话数组，通常已经按 updated_at 倒序排列。 */
  conversations: Conversation[]
  /** 当前选中的会话 ID，用于高亮列表项。 */
  selectedConversationId: string | null
  /** 会话搜索关键词；第二天先做前端本地过滤。 */
  searchTerm: string
  /** 点击会话时通知父组件切换当前会话。 */
  onSelectConversation: (conversationId: string) => void
  /** 搜索框输入变化时通知父组件更新过滤条件。 */
  onSearchTermChange: (nextSearchTerm: string) => void
  /** 点击加号时打开新建会话弹窗。 */
  onOpenNewConversation: () => void
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
  searchTerm,
  onSelectConversation,
  onSearchTermChange,
  onOpenNewConversation,
}: ConversationListProps) {
  return (
    <section className="sidebar-section">
      <div className="section-heading">
        <span>会话</span>
        {/* 新建会话入口，点击后由 App 打开 NewConversationModal。 */}
        <button
          className="icon-button"
          onClick={onOpenNewConversation}
          type="button"
          aria-label="新建会话"
        >
          +
        </button>
      </div>

      {/* 搜索接口文档未明确，先在前端按标题做本地过滤。 */}
      <input
        className="search-box"
        onChange={(event) => onSearchTermChange(event.target.value)}
        placeholder="搜索会话"
        value={searchTerm}
      />

      <div className="conversation-list">
        {conversations.length === 0 ? (
          <div className="conversation-empty">没有匹配的会话</div>
        ) : (
          conversations.map((conversation) => (
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
          ))
        )}
      </div>
    </section>
  )
}
