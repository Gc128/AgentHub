import { useEffect, useState, type FormEvent } from 'react'
import type { Agent, ConversationMode, CreateConversationInput } from '../../types/api'

type NewConversationModalProps = {
  /** 是否显示新建会话弹窗。 */
  open: boolean
  /** 可选 Agent 列表，用于选择新会话参与者。 */
  agents: Agent[]
  /** 关闭弹窗；取消或创建成功后都会调用。 */
  onClose: () => void
  /** 提交新会话输入，父组件负责调用 apiClient.createConversation。 */
  onCreateConversation: (input: CreateConversationInput) => Promise<void>
}

/** 根据用户选择的 Agent 自动推导会话模式。 */
const inferMode = (agentIds: string[]): ConversationMode =>
  agentIds.length > 1 ? 'group' : 'single'

/**
 * 新建会话弹窗。
 * 第二天只实现最小可用输入：标题 + 参与 Agent；置顶/归档等字段文档未明确，暂不加入。
 */
export function NewConversationModal({
  open,
  agents,
  onClose,
  onCreateConversation,
}: NewConversationModalProps) {
  // 新会话标题，默认贴近 Demo 主线，方便比赛演示快速创建。
  const [title, setTitle] = useState('Todo App Development')
  // 默认选择 Orchestrator，让新会话天然服务多 Agent 协作主链路。
  const [selectedAgentIds, setSelectedAgentIds] = useState<string[]>([
    'orchestrator',
  ])
  // 提交中的 loading 状态，防止连续点击创建重复会话。
  const [submitting, setSubmitting] = useState(false)
  // 表单错误，主要处理空标题或没有选择 Agent。
  const [formError, setFormError] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      setFormError(null)
    }
  }, [open])

  if (!open) {
    return null
  }

  /** 勾选或取消某个 Agent，并保持至少由提交校验兜底。 */
  const toggleAgent = (agentId: string) => {
    setSelectedAgentIds((currentAgentIds) =>
      currentAgentIds.includes(agentId)
        ? currentAgentIds.filter((currentAgentId) => currentAgentId !== agentId)
        : [...currentAgentIds, agentId],
    )
  }

  /** 提交新建会话，输入结构严格使用 CreateConversationInput。 */
  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const normalizedTitle = title.trim()

    if (!normalizedTitle) {
      setFormError('请输入会话标题')
      return
    }

    if (selectedAgentIds.length === 0) {
      setFormError('请至少选择一个 Agent')
      return
    }

    setSubmitting(true)
    setFormError(null)

    try {
      await onCreateConversation({
        title: normalizedTitle,
        mode: inferMode(selectedAgentIds),
        agent_ids: selectedAgentIds,
      })
      onClose()
    } catch (caughtError) {
      setFormError(
        caughtError instanceof Error ? caughtError.message : '创建会话失败',
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <form className="modal-card" onSubmit={handleSubmit}>
        <header className="modal-header">
          <div>
            <p className="eyebrow">New Conversation</p>
            <h2>新建会话</h2>
          </div>
          <button
            className="icon-button"
            onClick={onClose}
            type="button"
            aria-label="关闭新建会话弹窗"
          >
            ×
          </button>
        </header>

        <label className="field-label">
          会话标题
          <input
            className="text-input"
            onChange={(event) => setTitle(event.target.value)}
            value={title}
          />
        </label>

        <div className="field-label">
          选择 Agent
          <div className="agent-checkbox-list">
            {agents.map((agent) => (
              <label className="agent-checkbox" key={agent.id}>
                <input
                  checked={selectedAgentIds.includes(agent.id)}
                  onChange={() => toggleAgent(agent.id)}
                  type="checkbox"
                />
                <span>
                  <strong>{agent.name}</strong>
                  <small>{agent.description}</small>
                </span>
              </label>
            ))}
          </div>
        </div>

        {formError ? <div className="form-error">{formError}</div> : null}

        <footer className="modal-actions">
          <button className="secondary-button" onClick={onClose} type="button">
            取消
          </button>
          <button className="primary-button" disabled={submitting} type="submit">
            {submitting ? '创建中...' : '创建会话'}
          </button>
        </footer>
      </form>
    </div>
  )
}
