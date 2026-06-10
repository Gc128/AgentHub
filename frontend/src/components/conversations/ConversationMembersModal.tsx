import { useEffect, useState, type FormEvent } from 'react'
import { Alert, Button, Checkbox, Modal } from 'antd'
import type { Agent, Conversation } from '../../types/api'

type ConversationMembersModalProps = {
  /** 是否显示当前会话成员管理弹窗。 */
  open: boolean
  /** 当前正在编辑成员的会话；为空时弹窗不展示。 */
  conversation: Conversation | null
  /** 全局可用 Agent 列表，用户可以从中添加到当前会话。 */
  agents: Agent[]
  /** 关闭弹窗；取消或保存成功后都会调用。 */
  onClose: () => void
  /** 保存新的成员 Agent ID 列表，父组件负责调用 PATCH /api/conversations/{id}。 */
  onUpdateMembers: (
    conversationId: string,
    nextAgentIds: string[],
  ) => Promise<void>
}

/**
 * 当前会话成员管理弹窗。
 * 它只修改 Conversation.agent_ids，mode 由父组件根据成员数量自动推导。
 */
export function ConversationMembersModal({
  open,
  conversation,
  agents,
  onClose,
  onUpdateMembers,
}: ConversationMembersModalProps) {
  // selectedAgentIds 是弹窗内的临时选择，只有点击保存后才会同步到会话。
  const [selectedAgentIds, setSelectedAgentIds] = useState<string[]>([])
  // 保存中的 loading 状态，避免用户连续点击造成重复 PATCH。
  const [submitting, setSubmitting] = useState(false)
  // 成员数量校验或保存失败提示。
  const [formError, setFormError] = useState<string | null>(null)

  useEffect(() => {
    if (open && conversation) {
      setSelectedAgentIds(conversation.agent_ids)
      setFormError(null)
    }
  }, [conversation, open])

  if (!open || !conversation) {
    return null
  }

  /** 勾选或移除 Agent；移除最后一个成员时立即阻止，保证会话至少有一个 Agent。 */
  const toggleAgent = (agentId: string) => {
    setSelectedAgentIds((currentAgentIds) => {
      const removing = currentAgentIds.includes(agentId)

      if (removing && currentAgentIds.length === 1) {
        setFormError('当前会话至少需要保留一个 Agent')
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

  /** 提交成员变更；请求体只传 agent_ids，mode 由父组件按数量推导。 */
  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()

    if (selectedAgentIds.length === 0) {
      setFormError('当前会话至少需要保留一个 Agent')
      return
    }

    setSubmitting(true)
    setFormError(null)

    try {
      await onUpdateMembers(conversation.id, selectedAgentIds)
      onClose()
    } catch (caughtError) {
      setFormError(
        caughtError instanceof Error ? caughtError.message : '更新成员失败',
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
      title="管理会话成员"
    >
      <form className="modal-form" onSubmit={handleSubmit}>
        <p className="modal-subtitle">
          当前会话只能 @ 已加入的 Agent；历史消息会保留，不受成员变化影响。
        </p>

        <div className="field-label">
          <span className="field-label-row">
            会话 Agent
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
            {agents.map((agent) => {
              const checked = selectedAgentIds.includes(agent.id)
              const lastSelected = checked && selectedAgentIds.length === 1

              return (
                <label
                  className={
                    lastSelected
                      ? 'agent-checkbox is-required-member'
                      : 'agent-checkbox'
                  }
                  key={agent.id}
                >
                  <Checkbox
                    checked={checked}
                    onChange={() => toggleAgent(agent.id)}
                  />
                  <span>
                    <strong>{agent.name}</strong>
                    <small>
                      {agent.description}
                      {lastSelected ? ' · 至少保留一个' : ''}
                    </small>
                  </span>
                </label>
              )
            })}
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
            {submitting ? '保存中...' : '保存成员'}
          </Button>
        </footer>
      </form>
    </Modal>
  )
}
