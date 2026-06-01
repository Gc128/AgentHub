import { useState, type FormEvent } from 'react'
import type { Agent } from '../../types/api'
import {
  getActiveMentionQuery,
  getAgentMentionLabel,
  insertAgentMention,
} from '../../utils/agentRouting'
import { MentionMenu } from './MentionMenu'

type MessageComposerProps = {
  /** 可 @ 的 Agent 列表，用于快捷标签和 MentionMenu。 */
  agents: Agent[]
  /** 当前是否有可发送的会话；没有会话时输入框禁用。 */
  disabled: boolean
  /** 消息提交回调，父组件负责调用 apiClient.createMessage。 */
  onSendMessage: (content: string) => Promise<void>
}

/**
 * 聊天输入组件。
 * 第三天增加 @Agent 菜单；发送后父组件会根据 @ 触发 mock Agent 回复。
 */
export function MessageComposer({
  agents,
  disabled,
  onSendMessage,
}: MessageComposerProps) {
  // 输入框文本，提交成功后清空。
  const [content, setContent] = useState('')
  // 发送 loading 状态，防止连续提交重复消息。
  const [sending, setSending] = useState(false)
  // 输入校验或发送失败提示。
  const [composerError, setComposerError] = useState<string | null>(null)

  /** 当前正在输入的 @ 查询；为 null 时不显示 MentionMenu。 */
  const mentionQuery = getActiveMentionQuery(content)

  /** 把用户选择的 Agent 以 @ 标签形式插入输入框。 */
  const handleSelectAgent = (agent: Agent) => {
    setContent((currentContent) =>
      insertAgentMention(currentContent, getAgentMentionLabel(agent)),
    )
    setComposerError(null)
  }

  /** 提交用户消息；空白内容不会发送到 mock API。 */
  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const normalizedContent = content.trim()

    if (!normalizedContent) {
      setComposerError('请输入消息内容')
      return
    }

    setSending(true)
    setComposerError(null)

    try {
      await onSendMessage(normalizedContent)
      setContent('')
    } catch (caughtError) {
      setComposerError(
        caughtError instanceof Error ? caughtError.message : '发送消息失败',
      )
    } finally {
      setSending(false)
    }
  }

  return (
    <form className="message-composer" onSubmit={handleSubmit}>
      {/* 快捷 @ 标签：适合 Demo 时不用键盘输入也能快速指定 Agent。 */}
      <div className="mention-bar" aria-label="Agent 快捷提及">
        {agents.map((agent) => (
          <button
            className="mention-chip"
            disabled={disabled || sending}
            key={agent.id}
            onClick={() => handleSelectAgent(agent)}
            type="button"
          >
            {getAgentMentionLabel(agent)}
          </button>
        ))}
      </div>
      <div className="composer-input-wrap">
        <MentionMenu
          agents={agents}
          query={mentionQuery}
          onSelectAgent={handleSelectAgent}
        />
        <textarea
          className="composer-input"
          disabled={disabled || sending}
          onChange={(event) => {
            setContent(event.target.value)
            setComposerError(null)
          }}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              event.currentTarget.form?.requestSubmit()
            }
          }}
          placeholder="输入开发需求，例如：@Orchestrator 帮我做一个简洁的 Todo List 网页"
          rows={3}
          value={content}
        />
      </div>
      <div className="composer-footer">
        <span className="composer-hint">
          输入 @ 可选择 Agent；@Orchestrator 会触发多 Agent 模拟协作
        </span>
        <button
          className="primary-button"
          disabled={disabled || sending}
          type="submit"
        >
          {sending ? '发送中...' : '发送'}
        </button>
      </div>
      {composerError ? <div className="form-error">{composerError}</div> : null}
    </form>
  )
}
