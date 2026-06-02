import { ThunderboltOutlined, SendOutlined } from '@ant-design/icons'
import { Alert, Button, Input, Tag } from 'antd'
import { useState, type FormEvent } from 'react'
import type { Agent } from '../../types/api'
import {
  getActiveMentionQuery,
  getAgentMentionLabel,
  insertAgentMention,
} from '../../utils/agentRouting'
import { MentionMenu } from './MentionMenu'

/** Demo Prompt 的业务文本；真正的 @Agent 标签会根据当前会话成员动态选择。 */
const DEMO_TASK = '帮我做一个简洁的 Todo List 网页'

/**
 * 根据当前会话成员生成演示 Prompt。
 * 如果会话里有 Orchestrator，就走完整多 Agent Demo；否则使用当前会话第一个 Agent，避免越权 @。
 */
const createDemoPrompt = (agents: Agent[]) => {
  const orchestrator = agents.find((agent) => agent.id === 'orchestrator')
  const targetAgent = orchestrator ?? agents[0]
  return targetAgent ? `${getAgentMentionLabel(targetAgent)} ${DEMO_TASK}` : ''
}

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
  /** 当前会话可用的 Demo Prompt；只会使用当前会话成员中的 Agent。 */
  const demoPrompt = createDemoPrompt(agents)

  /** 把用户选择的 Agent 以 @ 标签形式插入输入框。 */
  const handleSelectAgent = (agent: Agent) => {
    if (disabled || sending) {
      return
    }

    setContent((currentContent) =>
      insertAgentMention(currentContent, getAgentMentionLabel(agent)),
    )
    setComposerError(null)
  }

  /** 一键填入 Demo Prompt，减少现场演示输入成本。 */
  const handleUseDemoPrompt = () => {
    setContent(demoPrompt)
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
        {agents.length > 0 ? (
          agents.map((agent) => (
            <Tag
              className="mention-chip"
              key={agent.id}
              onClick={() => handleSelectAgent(agent)}
            >
              {getAgentMentionLabel(agent)}
            </Tag>
          ))
        ) : (
          <Tag className="mention-chip is-disabled">当前会话暂无 Agent</Tag>
        )}
      </div>
      <div className="composer-input-wrap">
        <MentionMenu
          agents={agents}
          query={mentionQuery}
          onSelectAgent={handleSelectAgent}
        />
        <Input.TextArea
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
          placeholder="输入开发需求，@ 菜单只会显示当前会话成员"
          rows={3}
          value={content}
        />
      </div>
      <div className="composer-footer">
        <span className="composer-hint">
          输入 @ 可选择当前会话成员；调整成员后 @ 菜单会同步变化
        </span>
        <Button
          className="secondary-button demo-prompt-button"
          disabled={disabled || sending || !demoPrompt}
          icon={<ThunderboltOutlined />}
          onClick={handleUseDemoPrompt}
        >
          使用 Demo Prompt
        </Button>
        <Button
          className="primary-button"
          disabled={disabled || sending}
          htmlType="submit"
          icon={<SendOutlined />}
          loading={sending}
          type="primary"
        >
          {sending ? '发送中...' : '发送'}
        </Button>
      </div>
      {composerError ? (
        <Alert
          className="form-error"
          message={composerError}
          showIcon
          type="error"
        />
      ) : null}
    </form>
  )
}
