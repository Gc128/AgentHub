import { useEffect, useState, type FormEvent } from 'react'
import { Alert, Button, Checkbox, Input, Modal } from 'antd'
import type {
  Agent,
  ConversationMode,
  CreateConversationInput,
} from '../../types/api'

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
 * 会话成员会成为后续 @Agent 的可用边界；mode 根据成员数量自动推导。
 */
export function NewConversationModal({
  open,
  agents,
  onClose,
  onCreateConversation,
}: NewConversationModalProps) {
  // 新会话标题，默认贴近 Demo 主线，方便比赛演示快速创建。
  const [title, setTitle] = useState('Todo App Development')
  // 默认成员会在弹窗打开时按当前全局 Agent 列表重置，便于 Demo 新会话直接具备完整协作链路。
  const [selectedAgentIds, setSelectedAgentIds] = useState<string[]>([])
  // 提交中的 loading 状态，防止连续点击创建重复会话。
  const [submitting, setSubmitting] = useState(false)
  // 表单错误，主要处理空标题或没有选择 Agent。
  const [formError, setFormError] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      setSelectedAgentIds(agents.map((agent) => agent.id))
      setFormError(null)
    }
  }, [agents, open])

  if (!open) {
    return null
  }

  /** 勾选或取消某个 Agent；取消最后一个成员时立即阻止，保证会话至少有一个 Agent。 */
  const toggleAgent = (agentId: string) => {
    setSelectedAgentIds((currentAgentIds) => {
      const removing = currentAgentIds.includes(agentId)

      if (removing && currentAgentIds.length === 1) {
        setFormError('请至少选择一个 Agent')
        return currentAgentIds
      }

      setFormError(null)
      return removing
        ? currentAgentIds.filter((currentAgentId) => currentAgentId !== agentId)
        : [...currentAgentIds, agentId]
    })
  }

  const selectAllAgents = () => {
    setSelectedAgentIds(agents.map((agent) => agent.id))
    setFormError(null)
  }

  const clearSelectedAgents = () => {
    setSelectedAgentIds([])
    setFormError(null)
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
    <Modal
      centered
      footer={null}
      onCancel={onClose}
      open={open}
      title="新建会话"
    >
      <form className="modal-form" onSubmit={handleSubmit}>
        <p className="modal-subtitle">
          创建一个绑定 workspace 的 AgentHub 会话，后续消息和产物都会保存在这里。
        </p>

        <label className="field-label">
          会话标题
          <Input
            className="text-input"
            onChange={(event) => setTitle(event.target.value)}
            placeholder="例如：Todo App Development"
            value={title}
          />
        </label>

        <div className="field-label">
          <span className="field-label-row">
            选择 Agent
            <span className="field-label-actions">
              <Button size="small" type="text" onClick={selectAllAgents}>
                全选
              </Button>
              <Button size="small" type="text" onClick={clearSelectedAgents}>
                取消全选
              </Button>
            </span>
          </span>
          <div className="agent-checkbox-list">
            {agents.map((agent) => (
              <label className="agent-checkbox" key={agent.id}>
                <Checkbox
                  checked={selectedAgentIds.includes(agent.id)}
                  onChange={() => toggleAgent(agent.id)}
                />
                <span>
                  <strong>{agent.name}</strong>
                  <small>{agent.description}</small>
                </span>
              </label>
            ))}
          </div>
        </div>

        {formError ? (
          <Alert
            className="form-error"
            showIcon
            title={formError}
            type="error"
          />
        ) : null}

        <footer className="modal-actions">
          <Button className="secondary-button" onClick={onClose}>
            取消
          </Button>
          <Button
            className="primary-button"
            htmlType="submit"
            loading={submitting}
            type="primary"
          >
            {submitting ? '创建中...' : '创建会话'}
          </Button>
        </footer>
      </form>
    </Modal>
  )
}
