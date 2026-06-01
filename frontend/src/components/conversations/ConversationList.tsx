import {
  DeleteOutlined,
  MessageOutlined,
  PlusOutlined,
  PushpinFilled,
  PushpinOutlined,
  SearchOutlined,
} from '@ant-design/icons'
import { Badge, Button, Empty, Input, Popconfirm, Tag, Tooltip } from 'antd'
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
  /** 点击置顶按钮时通知父组件 PATCH is_pinned。 */
  onTogglePinConversation: (
    conversationId: string,
    nextPinned: boolean,
  ) => Promise<void>
  /** 点击删除确认后通知父组件 DELETE 会话。 */
  onDeleteConversation: (conversationId: string) => Promise<void>
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
  onTogglePinConversation,
  onDeleteConversation,
}: ConversationListProps) {
  return (
    <section className="sidebar-section conversation-section">
      <div className="section-heading">
        <span>会话</span>
        {/* 新建会话入口，点击后由 App 打开 NewConversationModal。 */}
        <Button
          className="icon-button"
          icon={<PlusOutlined />}
          onClick={onOpenNewConversation}
          type="text"
          aria-label="新建会话"
        />
      </div>

      {/* 搜索接口文档未明确，先在前端按标题做本地过滤。 */}
      <Input
        className="search-box"
        onChange={(event) => onSearchTermChange(event.target.value)}
        placeholder="搜索会话"
        prefix={<SearchOutlined />}
        allowClear
        value={searchTerm}
      />

      <div className="conversation-list">
        {conversations.length === 0 ? (
          <Empty
            className="conversation-empty"
            description="没有匹配的会话"
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        ) : (
          conversations.map((conversation) => (
            <article
              // 当前选中的会话使用 is-active 高亮，让用户明确聊天区来源。
              className={
                conversation.id === selectedConversationId
                  ? 'conversation-item is-active'
                  : 'conversation-item'
              }
              key={conversation.id}
            >
              <button
                className="conversation-main"
                onClick={() => onSelectConversation(conversation.id)}
                type="button"
              >
                <span className="conversation-title-row">
                  <span className="conversation-title">{conversation.title}</span>
                  {/* is_pinned 是本轮新增字段，只用于排序和展示置顶标记。 */}
                  {conversation.is_pinned ? (
                    <Tag className="conversation-pin-tag" icon={<PushpinFilled />}>
                      置顶
                    </Tag>
                  ) : null}
                </span>
                <span className="conversation-meta">
                  {/* mode 字段来自后端 schema，前端只做文案映射。 */}
                  <Badge
                    color={conversation.mode === 'group' ? '#235b54' : '#7a5c22'}
                    text={conversation.mode === 'group' ? '群聊协作' : '单聊'}
                  />
                  <MessageOutlined />
                  <span>{formatTime(conversation.updated_at)}</span>
                </span>
              </button>

              <div className="conversation-actions">
                <Tooltip title={conversation.is_pinned ? '取消置顶' : '置顶会话'}>
                  <Button
                    aria-label={conversation.is_pinned ? '取消置顶' : '置顶会话'}
                    className="conversation-action-button"
                    icon={
                      conversation.is_pinned ? (
                        <PushpinFilled />
                      ) : (
                        <PushpinOutlined />
                      )
                    }
                    onClick={() =>
                      void onTogglePinConversation(
                        conversation.id,
                        !conversation.is_pinned,
                      )
                    }
                    size="small"
                    type="text"
                  />
                </Tooltip>
                <Popconfirm
                  cancelText="取消"
                  description="删除后会同步移除该会话的 mock 消息和预览状态。"
                  okButtonProps={{ danger: true }}
                  okText="删除"
                  onConfirm={() => void onDeleteConversation(conversation.id)}
                  title="删除会话？"
                >
                  <Button
                    aria-label="删除会话"
                    className="conversation-action-button"
                    danger
                    icon={<DeleteOutlined />}
                    size="small"
                    type="text"
                  />
                </Popconfirm>
              </div>
            </article>
          ))
        )}
      </div>
    </section>
  )
}
