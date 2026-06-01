import { useState, type FormEvent } from 'react'

type MessageComposerProps = {
  /** 当前是否有可发送的会话；没有会话时输入框禁用。 */
  disabled: boolean
  /** 消息提交回调，父组件负责调用 apiClient.createMessage。 */
  onSendMessage: (content: string) => Promise<void>
}

/**
 * 聊天输入组件。
 * 第二天只负责本地发送用户消息；@Agent 菜单和 Agent 回复会在第三天接入。
 */
export function MessageComposer({
  disabled,
  onSendMessage,
}: MessageComposerProps) {
  // 输入框文本，提交成功后清空。
  const [content, setContent] = useState('')
  // 发送 loading 状态，防止连续提交重复消息。
  const [sending, setSending] = useState(false)
  // 输入校验或发送失败提示。
  const [composerError, setComposerError] = useState<string | null>(null)

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
      {/* @Agent 快捷提示；第三天会升级为真正的 MentionMenu。 */}
      <div className="mention-bar">
        @Orchestrator @CodeAgent @ReviewAgent @PreviewAgent
      </div>
      <textarea
        className="composer-input"
        disabled={disabled || sending}
        onChange={(event) => setContent(event.target.value)}
        placeholder="输入开发需求，例如：@Orchestrator 帮我做一个简洁的 Todo List 网页"
        rows={3}
        value={content}
      />
      <div className="composer-footer">
        <span className="composer-hint">
          当前阶段先保存用户消息，Agent 回复将在下一步接入
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
