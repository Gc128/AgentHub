import { Avatar, Tag } from 'antd'
import type { Agent } from '../../types/api'

/** Agent 联系人列表组件的入参。 */
type AgentListProps = {
  /** 当前可用 Agent；首日来自 mock，后续可来自 GET /api/agents。 */
  agents: Agent[]
}

/** Agent.role 到中文短标签的映射，用于联系人卡片右上角。 */
const roleLabels: Record<Agent['role'], string> = {
  orchestrator: '协调',
  code: '代码',
  review: '审查',
  preview: '预览',
  custom: '自定义',
}

/**
 * 左侧 Agent 联系人列表。
 * 这个组件让用户一眼看到可 @ 的 Agent 及其能力，后续 MentionMenu 也会复用同一批数据。
 */
export function AgentList({ agents }: AgentListProps) {
  return (
    <section className="sidebar-section agent-section">
      <div className="section-heading">
        <span>Agents</span>
      </div>

      <div className="agent-list">
        {agents.map((agent) => (
          <article className="agent-item" key={agent.id}>
            {/* 使用 Ant Design Avatar 提升联系人识别度；数据仍来自原 Agent.name。 */}
            <Avatar className="agent-avatar" shape="square">
              {agent.name.slice(0, 1)}
            </Avatar>
            <div className="agent-copy">
              <div className="agent-row">
                <span className="agent-name">{agent.name}</span>
                {/* role 是结构化字段，显示时映射成短中文标签。 */}
                <Tag className="agent-role" color="gold">
                  {roleLabels[agent.role]}
                </Tag>
              </div>
              <p>{agent.description}</p>
              <div className="capability-row">
                {/* 能力标签可能很多，列表卡片里只展示前三个以保持密度。 */}
                {agent.capabilities.slice(0, 3).map((capability) => (
                  <Tag className="capability-pill" key={capability}>
                    {capability}
                  </Tag>
                ))}
              </div>
            </div>
          </article>
        ))}
      </div>
    </section>
  )
}
