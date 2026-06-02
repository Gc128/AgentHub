import type { Agent } from '../types/api'

/**
 * Agent ID 到 @ 提及文案的固定映射。
 * 这些文案和后端 orchestrator/router.py 中的 @Agent 规则保持一致。
 */
export const AGENT_MENTION_LABELS: Record<string, string> = {
  orchestrator: '@Orchestrator',
  'code-agent': '@CodeAgent',
  'review-agent': '@ReviewAgent',
  'preview-agent': '@PreviewAgent',
}

/**
 * 根据 Agent 返回它在输入框中展示和插入的 @ 标签。
 * 如果后续出现自定义 Agent，就退回到去空格的 name，保持菜单仍可用。
 */
export const getAgentMentionLabel = (agent: Pick<Agent, 'id' | 'name'>) =>
  AGENT_MENTION_LABELS[agent.id] ?? `@${agent.name.replace(/\s+/g, '')}`

/**
 * 读取输入框末尾正在输入的 @ 查询。
 * 例如 "帮我 @Co" 返回 "co"，没有正在输入 @ 时返回 null。
 */
export const getActiveMentionQuery = (content: string): string | null => {
  const match = content.match(/(?:^|\s)@([A-Za-z]*)$/)
  return match ? match[1].toLowerCase() : null
}

/**
 * 把选中的 @Agent 插入输入内容。
 * 如果光标前正在输入 "@Co"，就替换这段；否则追加到末尾。
 */
export const insertAgentMention = (content: string, mentionLabel: string) => {
  const hasActiveMention = /(?:^|\s)@[A-Za-z]*$/.test(content)
  if (hasActiveMention) {
    return `${content.replace(/(?:^|\s)@[A-Za-z]*$/, (segment) =>
      segment.startsWith(' ') ? ` ${mentionLabel}` : mentionLabel,
    )} `
  }
  return `${content}${content.endsWith(' ') || content.length === 0 ? '' : ' '}${mentionLabel} `
}

/**
 * 从用户消息中解析显式 @ 的 Agent。
 * 既支持 @Orchestrator 这种固定标签，也兼容直接写 Agent name 的情况。
 */
const resolveMentionedAgentIds = (content: string, agents: Agent[]) => {
  const normalizedContent = content.toLowerCase()
  return agents
    .filter((agent) => {
      const mentionLabel = getAgentMentionLabel(agent).toLowerCase()
      return (
        normalizedContent.includes(mentionLabel) ||
        normalizedContent.includes(`@${agent.name.toLowerCase()}`)
      )
    })
    .map((agent) => agent.id)
}

/** 按给定顺序去重，避免用户同时 @Orchestrator 和 @CodeAgent 时重复调用。 */
const uniqueInOrder = (agentIds: string[]) =>
  agentIds.filter((agentId, index) => agentIds.indexOf(agentId) === index)

/** 判断某个 Agent 是否存在于当前会话成员中。 */
const hasAgent = (agentId: string, agents: Agent[]) =>
  agents.some((agent) => agent.id === agentId)

/** 返回当前会话中第一个可用 Agent，用于关键词路由没有匹配成员时兜底。 */
const getFallbackAgentId = (agents: Agent[]) =>
  hasAgent('orchestrator', agents) ? 'orchestrator' : agents[0]?.id

/**
 * 根据消息内容决定 mock Agent 调用顺序。
 * 这里传入的 agents 必须是“当前会话成员”，不是全局 Agent 列表；
 * 因此 @ 菜单和自动调度都不会越过 conversation.agent_ids 的成员边界。
 */
export const resolveAgentRunOrder = (content: string, agents: Agent[]) => {
  const mentionedAgentIds = resolveMentionedAgentIds(content, agents)

  if (mentionedAgentIds.includes('orchestrator')) {
    return uniqueInOrder([
      'orchestrator',
      'code-agent',
      'review-agent',
      'preview-agent',
    ]).filter((agentId) => hasAgent(agentId, agents))
  }

  if (mentionedAgentIds.length > 0) {
    return uniqueInOrder(mentionedAgentIds)
  }

  if (/[写实现生成页面组件]/.test(content) && hasAgent('code-agent', agents)) {
    return ['code-agent']
  }

  if (/检查|优化|问题|review|bug/i.test(content) && hasAgent('review-agent', agents)) {
    return ['review-agent']
  }

  if (/预览|效果|页面展示/.test(content) && hasAgent('preview-agent', agents)) {
    return ['preview-agent']
  }

  const fallbackAgentId = getFallbackAgentId(agents)
  return fallbackAgentId ? [fallbackAgentId] : []
}
