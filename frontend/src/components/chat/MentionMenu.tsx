import type { Agent } from '../../types/api'
import { getAgentMentionLabel } from '../../utils/agentRouting'

type MentionMenuProps = {
  /** 可被 @ 的 Agent 列表。 */
  agents: Agent[]
  /** 当前输入的 @ 查询；例如 @Co 对应 co。 */
  query: string | null
  /** 点击某个 Agent 后把 @ 标签插入输入框。 */
  onSelectAgent: (agent: Agent) => void
}

/** 判断 Agent 是否匹配当前 @ 查询，支持名称、ID 和固定 @ 标签。 */
const matchesQuery = (agent: Agent, query: string) => {
  const normalizedQuery = query.toLowerCase()
  return (
    agent.name.toLowerCase().includes(normalizedQuery) ||
    agent.id.toLowerCase().includes(normalizedQuery) ||
    getAgentMentionLabel(agent).toLowerCase().includes(normalizedQuery)
  )
}

/**
 * @Agent 候选菜单。
 * 该组件只负责展示和选择，不处理输入框文本替换，文本替换由 MessageComposer 完成。
 */
export function MentionMenu({ agents, query, onSelectAgent }: MentionMenuProps) {
  if (query === null) {
    return null
  }

  const visibleAgents = query
    ? agents.filter((agent) => matchesQuery(agent, query))
    : agents

  if (visibleAgents.length === 0) {
    return (
      <div className="mention-menu">
        <div className="mention-empty">没有匹配的 Agent</div>
      </div>
    )
  }

  return (
    <div className="mention-menu">
      {visibleAgents.map((agent) => (
        <button
          className="mention-option"
          key={agent.id}
          onClick={() => onSelectAgent(agent)}
          type="button"
        >
          <span className="mention-option-label">
            {getAgentMentionLabel(agent)}
          </span>
          <span className="mention-option-copy">{agent.description}</span>
        </button>
      ))}
    </div>
  )
}
