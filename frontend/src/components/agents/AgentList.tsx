import {
  ApartmentOutlined,
  AuditOutlined,
  CodeOutlined,
  EyeOutlined,
  ToolOutlined,
} from '@ant-design/icons'
import { Button, Tag, Tooltip } from 'antd'
import type { Agent, AgentRole } from '../../types/api'

type AgentListProps = {
  agents: Agent[]
  onOpenAgentManager: () => void
}

const ROLE_CONFIG: Record<
  AgentRole,
  { icon: React.ReactNode; color: string; bg: string }
> = {
  orchestrator: {
    icon: <ApartmentOutlined />,
    color: '#f0bb3f',
    bg: 'rgba(240,187,63,0.15)',
  },
  code: {
    icon: <CodeOutlined />,
    color: '#5cb88a',
    bg: 'rgba(92,184,138,0.15)',
  },
  review: {
    icon: <AuditOutlined />,
    color: '#6baad8',
    bg: 'rgba(107,170,216,0.15)',
  },
  preview: {
    icon: <EyeOutlined />,
    color: '#b07ed4',
    bg: 'rgba(176,126,212,0.15)',
  },
  custom: {
    icon: <ToolOutlined />,
    color: '#d4855a',
    bg: 'rgba(212,133,90,0.15)',
  },
}

const ROLE_LABELS: Record<AgentRole, string> = {
  orchestrator: '协调',
  code: '代码',
  review: '审查',
  preview: '预览',
  custom: '自定义',
}

/** 悬浮卡片内容：名称 + 角色标签 + 描述 + 能力标签，无图标 */
function AgentTooltipCard({ agent }: { agent: Agent }) {
  return (
    <div className="agent-card-tooltip">
      <div className="agent-card-tooltip-header">
        <span className="agent-card-tooltip-name">{agent.name}</span>
        <Tag className="agent-card-tooltip-role">
          {ROLE_LABELS[agent.role]}
        </Tag>
      </div>
      <p className="agent-card-tooltip-desc">{agent.description}</p>
      <div className="agent-card-tooltip-tags">
        {agent.capabilities.slice(0, 4).map((cap) => (
          <Tag className="agent-card-tooltip-tag" key={cap}>
            {cap}
          </Tag>
        ))}
      </div>
    </div>
  )
}

/**
 * 左侧 Agent 图标区。
 * Agent 图标并排，hover 时在图标上方弹出卡片式说明。
 */
export function AgentList({ agents, onOpenAgentManager }: AgentListProps) {
  return (
    <section className="agent-icon-section">
      <div className="agent-icon-heading">
        <span className="agent-icon-label">AGENTS</span>
        <Button size="small" type="text" onClick={onOpenAgentManager}>
          管理
        </Button>
      </div>
      <div className="agent-icon-row">
        {agents.map((agent) => {
          const cfg = ROLE_CONFIG[agent.role] ?? ROLE_CONFIG.custom
          return (
            <Tooltip
              key={agent.id}
              arrow={false}
              placement="top"
              title={<AgentTooltipCard agent={agent} />}
              overlayClassName="agent-card-tooltip-overlay"
              overlayInnerStyle={{
                padding: 0,
                background: 'transparent',
                boxShadow: 'none',
              }}
            >
              <button
                aria-label={agent.name}
                className="agent-icon-btn"
                style={
                  {
                    '--agent-color': cfg.color,
                    '--agent-bg': cfg.bg,
                  } as React.CSSProperties
                }
                type="button"
              >
                {cfg.icon}
              </button>
            </Tooltip>
          )
        })}
      </div>
    </section>
  )
}
