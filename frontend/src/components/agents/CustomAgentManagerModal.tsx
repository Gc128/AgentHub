import { useEffect, useState, type FormEvent } from 'react'
import {
  Alert,
  Button,
  Empty,
  Input,
  Modal,
  Popconfirm,
  Select,
  Switch,
  Tag,
} from 'antd'
import { apiClient } from '../../api/client'
import { MarkdownMessage } from '../chat/MarkdownMessage'
import type { AgentBackend, AgentRunResult, CustomAgent } from '../../types/api'

type CustomAgentManagerModalProps = {
  open: boolean
  onClose: () => void
  onAgentsChanged: () => Promise<void>
}

type CustomAgentFormState = {
  name: string
  description: string
  systemPrompt: string
  backendId: string
  capabilitiesText: string
  isEnabled: boolean
}

const defaultFormState = (): CustomAgentFormState => ({
  name: '',
  description: '',
  systemPrompt: '你是一个 AgentHub 自建 Agent。请根据用户消息给出清晰、可执行的回复。',
  backendId: 'openai-compatible',
  capabilitiesText: 'custom',
  isEnabled: true,
})

const formStateFromAgent = (agent: CustomAgent): CustomAgentFormState => ({
  name: agent.name,
  description: agent.description,
  systemPrompt: agent.system_prompt,
  backendId: agent.backend_id || 'openai-compatible',
  capabilitiesText: agent.capabilities.join(', '),
  isEnabled: agent.is_enabled,
})

const parseCapabilities = (value: string) =>
  value
    .split(/[,，\n]/)
    .map((item) => item.trim())
    .filter(Boolean)

const cleanCustomAgentOutput = (content: string, agentId?: string) => {
  if (!agentId) {
    return content
  }
  return content
    .replace(
      new RegExp(`^\\s*${agentId.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*[:：]\\s*`),
      '',
    )
    .trimStart()
}

export function CustomAgentManagerModal({
  open,
  onClose,
  onAgentsChanged,
}: CustomAgentManagerModalProps) {
  const [customAgents, setCustomAgents] = useState<CustomAgent[]>([])
  const [agentBackends, setAgentBackends] = useState<AgentBackend[]>([])
  const [editingAgentId, setEditingAgentId] = useState<string | null>(null)
  const [formState, setFormState] = useState<CustomAgentFormState>(() =>
    defaultFormState(),
  )
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testMessage, setTestMessage] = useState('请介绍一下你能做什么。')
  const [testResult, setTestResult] = useState<AgentRunResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const loadCustomAgents = async () => {
    setLoading(true)
    try {
      const nextAgents = await apiClient.listCustomAgents()
      setCustomAgents(nextAgents)
      setError(null)
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : '加载自建 Agent 失败',
      )
    } finally {
      setLoading(false)
    }
  }

  const loadAgentBackends = async () => {
    try {
      const nextBackends = await apiClient.listAgentBackends()
      setAgentBackends(nextBackends)
    } catch {
      setAgentBackends([])
    }
  }

  useEffect(() => {
    if (open) {
      void loadCustomAgents()
      void loadAgentBackends()
      setEditingAgentId(null)
      setFormState(defaultFormState())
      setTestResult(null)
      setError(null)
    }
  }, [open])

  if (!open) {
    return null
  }

  const selectedAgent = editingAgentId
    ? customAgents.find((agent) => agent.id === editingAgentId) ?? null
    : null

  const handleSelectAgent = (agent: CustomAgent) => {
    setEditingAgentId(agent.id)
    setFormState(formStateFromAgent(agent))
    setTestResult(null)
    setError(null)
  }

  const handleNewAgent = () => {
    setEditingAgentId(null)
    setFormState(defaultFormState())
    setTestResult(null)
    setError(null)
  }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const name = formState.name.trim()
    const systemPrompt = formState.systemPrompt.trim()
    if (!name) {
      setError('请输入 Agent 名称')
      return
    }
    if (!systemPrompt) {
      setError('请输入系统提示词')
      return
    }

    setSaving(true)
    try {
      const payload = {
        name,
        description: formState.description.trim(),
        system_prompt: systemPrompt,
        backend_id: formState.backendId,
        capabilities: parseCapabilities(formState.capabilitiesText),
        is_enabled: formState.isEnabled,
      }
      const savedAgent = editingAgentId
        ? await apiClient.updateCustomAgent(editingAgentId, payload)
        : await apiClient.createCustomAgent(payload)
      setEditingAgentId(savedAgent.id)
      setFormState(formStateFromAgent(savedAgent))
      await loadCustomAgents()
      await onAgentsChanged()
      setError(null)
    } catch (caughtError) {
      setError(
        caughtError instanceof Error ? caughtError.message : '保存自建 Agent 失败',
      )
    } finally {
      setSaving(false)
    }
  }

  const handleDeleteAgent = async (agent: CustomAgent) => {
    try {
      await apiClient.deleteCustomAgent(agent.id)
      if (editingAgentId === agent.id) {
        handleNewAgent()
      }
      await loadCustomAgents()
      await onAgentsChanged()
      setError(null)
    } catch (caughtError) {
      setError(
        caughtError instanceof Error ? caughtError.message : '删除自建 Agent 失败',
      )
    }
  }

  const handleTestAgent = async () => {
    if (!editingAgentId) {
      setError('请先保存自建 Agent，再进行测试')
      return
    }
    const message = testMessage.trim()
    if (!message) {
      setError('请输入测试消息')
      return
    }

    setTesting(true)
    try {
      const result = await apiClient.testCustomAgent(editingAgentId, message)
      setTestResult(result)
      setError(null)
    } catch (caughtError) {
      setError(
        caughtError instanceof Error ? caughtError.message : '测试自建 Agent 失败',
      )
    } finally {
      setTesting(false)
    }
  }

  return (
    <Modal
      centered
      footer={null}
      onCancel={onClose}
      open={open}
      title="自建 Agent 管理"
      width={860}
    >
      <div className="custom-agent-manager">
        <aside className="custom-agent-list">
          <div className="custom-agent-list-header">
            <strong>自建 Agent</strong>
            <Button size="small" type="text" onClick={handleNewAgent}>
              新建
            </Button>
          </div>
          {customAgents.length === 0 ? (
            <Empty
              className="custom-agent-empty"
              description={loading ? '加载中...' : '暂无自建 Agent'}
              image={Empty.PRESENTED_IMAGE_SIMPLE}
            />
          ) : (
            customAgents.map((agent) => (
              <button
                className={
                  agent.id === editingAgentId
                    ? 'custom-agent-list-item is-active'
                    : 'custom-agent-list-item'
                }
                key={agent.id}
                onClick={() => handleSelectAgent(agent)}
                type="button"
              >
                <span>
                  <strong>{agent.name}</strong>
                  <small>{agent.description || agent.id}</small>
                </span>
                <Tag className="agent-card-tooltip-tag">
                  {agent.is_enabled ? '启用' : '禁用'}
                </Tag>
              </button>
            ))
          )}
        </aside>

        <form className="modal-form custom-agent-form" onSubmit={handleSubmit}>
          <p className="modal-subtitle">
            自建 Agent 默认复用当前后端 LLM，也可以选择本机 Codex 或 Claude Code CLI。
          </p>

          <label className="field-label">
            Agent 名称
            <Input
              className="text-input"
              onChange={(event) =>
                setFormState((current) => ({
                  ...current,
                  name: event.target.value,
                }))
              }
              placeholder="例如：需求澄清 Agent"
              value={formState.name}
            />
          </label>

          <label className="field-label">
            描述
            <Input
              className="text-input"
              onChange={(event) =>
                setFormState((current) => ({
                  ...current,
                  description: event.target.value,
                }))
              }
              placeholder="用于会话成员列表和 hover 说明"
              value={formState.description}
            />
          </label>

          <label className="field-label">
            系统提示词
            <Input.TextArea
              className="text-input custom-agent-prompt-input"
              onChange={(event) =>
                setFormState((current) => ({
                  ...current,
                  systemPrompt: event.target.value,
                }))
              }
              placeholder="定义这个 Agent 的身份、边界、输出格式和工作方式"
              rows={6}
              value={formState.systemPrompt}
            />
          </label>

          <label className="field-label">
            执行后端
            <Select
              className="text-input"
              onChange={(value) =>
                setFormState((current) => ({ ...current, backendId: value }))
              }
              options={agentBackends.map((backend) => ({
                value: backend.id,
                label: `${backend.name}${backend.available ? '' : '（不可用）'}`,
                disabled: !backend.available && backend.id !== formState.backendId,
              }))}
              placeholder="选择 Agent 执行后端"
              value={formState.backendId}
            />
          </label>

          <label className="field-label">
            能力标签
            <Input
              className="text-input"
              onChange={(event) =>
                setFormState((current) => ({
                  ...current,
                  capabilitiesText: event.target.value,
                }))
              }
              placeholder="用逗号分隔，例如：需求澄清, 文案, 产品"
              value={formState.capabilitiesText}
            />
          </label>

          <div className="custom-agent-switch-row">
            <span>启用后可加入会话并出现在 @ 菜单中</span>
            <Switch
              checked={formState.isEnabled}
              onChange={(checked) =>
                setFormState((current) => ({ ...current, isEnabled: checked }))
              }
            />
          </div>

          {error ? (
            <Alert className="form-error" showIcon title={error} type="error" />
          ) : null}

          <div className="custom-agent-test-box">
            <Input.TextArea
              className="text-input"
              onChange={(event) => setTestMessage(event.target.value)}
              rows={2}
              value={testMessage}
            />
            <Button
              className="secondary-button"
              loading={testing}
              onClick={handleTestAgent}
            >
              测试 Agent
            </Button>
            {testResult ? (
              <div className="custom-agent-test-result">
                <strong>{selectedAgent?.name ?? formState.name}</strong>
                <MarkdownMessage
                  content={cleanCustomAgentOutput(
                    testResult.content,
                    testResult.agent_id,
                  )}
                />
              </div>
            ) : null}
          </div>

          <footer className="modal-actions">
            {selectedAgent ? (
              <Popconfirm
                cancelText="取消"
                description="删除后不会清理历史消息，但新会话不能再选择它。"
                okButtonProps={{ danger: true }}
                okText="删除"
                onConfirm={() => void handleDeleteAgent(selectedAgent)}
                title="删除这个自建 Agent？"
              >
                <Button danger type="text">
                  删除
                </Button>
              </Popconfirm>
            ) : null}
            <Button className="secondary-button" onClick={onClose}>
              关闭
            </Button>
            <Button
              className="primary-button"
              htmlType="submit"
              loading={saving}
              type="primary"
            >
              {editingAgentId ? '保存 Agent' : '创建 Agent'}
            </Button>
          </footer>
        </form>
      </div>
    </Modal>
  )
}
