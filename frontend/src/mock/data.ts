import type { Agent, Conversation, Message, WorkspacePreview } from '../types/api'

/**
 * Demo 可用 Agent 清单。
 * 这些字段严格对齐 Agent 类型，后续 @Agent 菜单和联系人列表都从这里读取。
 */
export const mockAgents: Agent[] = [
  {
    // Orchestrator 负责拆解任务和协调多个子 Agent。
    id: 'orchestrator',
    name: 'Orchestrator',
    role: 'orchestrator',
    description: '拆解开发需求，协调多个 Agent 完成任务。',
    capabilities: ['task-planning', 'routing', 'summary'],
    adapter_type: 'mock',
  },
  {
    // Code Agent 负责生成代码和 Diff，是 Demo 主链路中的第一个子 Agent。
    id: 'code-agent',
    name: 'Code Agent',
    role: 'code',
    description: '生成页面代码、组件和文件变更。',
    capabilities: ['code', 'diff', 'file-generation'],
    adapter_type: 'mock',
  },
  {
    // Review Agent 负责检查代码质量和风险。
    id: 'review-agent',
    name: 'Review Agent',
    role: 'review',
    description: '检查代码质量、风险和可维护性。',
    capabilities: ['review', 'quality', 'risk'],
    adapter_type: 'mock',
  },
  {
    // Preview Agent 负责反馈 workspace 预览状态。
    id: 'preview-agent',
    name: 'Preview Agent',
    role: 'preview',
    description: '生成预览信息并反馈页面效果。',
    capabilities: ['preview', 'workspace-status'],
    adapter_type: 'mock',
  },
]

/**
 * Demo 初始会话列表。
 * conv_001 是比赛演示主线；conv_002 用于证明左侧会话切换和单聊模式能工作。
 */
export const mockConversations: Conversation[] = [
  {
    // Todo App Development 对应 docs/demo-script.md 中推荐的演示会话。
    id: 'conv_001',
    title: 'Todo App Development',
    mode: 'group',
    agent_ids: ['orchestrator', 'code-agent', 'review-agent', 'preview-agent'],
    workspace_id: 'ws_001',
    created_at: '2026-06-01T10:00:00Z',
    updated_at: '2026-06-01T10:05:00Z',
  },
  {
    // 单 Agent review 会话，用于展示 single 模式。
    id: 'conv_002',
    title: 'Landing Page Review',
    mode: 'single',
    agent_ids: ['review-agent'],
    workspace_id: 'ws_002',
    created_at: '2026-06-01T09:30:00Z',
    updated_at: '2026-06-01T09:42:00Z',
  },
]

/**
 * 按 conversation_id 分组的消息表。
 * 这样 mock API 可以快速模拟 GET /api/conversations/{conversation_id}/messages。
 */
export const mockMessagesByConversationId: Record<string, Message[]> = {
  conv_001: [
    {
      // 用户提出开发需求，触发 Orchestrator 调度。
      id: 'msg_001',
      conversation_id: 'conv_001',
      role: 'user',
      sender_id: 'user',
      content: '@Orchestrator 帮我做一个简洁的 Todo List 网页',
      artifacts: [],
      created_at: '2026-06-01T10:01:00Z',
    },
    {
      // Orchestrator 回复任务拆解，使用 file artifact 暂存计划信息。
      id: 'msg_002',
      conversation_id: 'conv_001',
      role: 'agent',
      sender_id: 'orchestrator',
      content:
        '我会先拆解任务：Code Agent 生成页面代码，Review Agent 检查实现风险，Preview Agent 返回预览状态。',
      artifacts: [
        {
          id: 'artifact_plan_001',
          type: 'file',
          title: 'Task Breakdown',
          data: {
            // summary/steps 是计划卡片需要的数据；后端若补充 OrchestratorPlan，可再对齐。
            summary: 'Rule-based MVP plan',
            steps: ['生成 Todo 页面', '检查代码质量', '准备页面预览'],
          },
          created_at: '2026-06-01T10:01:10Z',
        },
      ],
      created_at: '2026-06-01T10:01:10Z',
    },
    {
      // Code Agent 输出代码和 Diff 两类产物，覆盖 P0 Artifact 展示需求。
      id: 'msg_003',
      conversation_id: 'conv_001',
      role: 'agent',
      sender_id: 'code-agent',
      content: 'Code Agent 已生成 Todo List 的 React 页面骨架和样式。',
      artifacts: [
        {
          id: 'artifact_code_001',
          type: 'code',
          title: 'Todo App Component',
          data: {
            // code artifact 的最小渲染字段：文件名、语言、代码内容。
            filename: 'src/App.tsx',
            language: 'tsx',
            content:
              "export default function App() {\n  return <main className=\"todo-app\">Todo List</main>\n}\n",
          },
          created_at: '2026-06-01T10:02:00Z',
        },
        {
          id: 'artifact_diff_001',
          type: 'diff',
          title: 'Todo App Diff',
          data: {
            // diff artifact 使用 unified diff 字符串，后续 Apply Diff 直接消费该内容。
            filename: 'src/App.tsx',
            diff:
              '--- a/src/App.tsx\n+++ b/src/App.tsx\n@@\n-export default function App() { return null }\n+export default function App() {\n+  return <main className="todo-app">Todo List</main>\n+}\n',
          },
          created_at: '2026-06-01T10:02:05Z',
        },
      ],
      created_at: '2026-06-01T10:02:00Z',
    },
    {
      // Preview Agent 输出预览产物；当前没有真实 preview_url，所以只展示状态。
      id: 'msg_004',
      conversation_id: 'conv_001',
      role: 'agent',
      sender_id: 'preview-agent',
      content: 'Preview Agent 已准备好工作区预览，等待应用 Diff 后刷新。',
      artifacts: [
        {
          id: 'artifact_preview_001',
          type: 'preview',
          title: 'Workspace Preview',
          data: {
            // preview artifact 与 workspace preview 接口都通过 workspace_id 关联。
            workspace_id: 'ws_001',
            status: 'not_started',
          },
          created_at: '2026-06-01T10:03:00Z',
        },
      ],
      created_at: '2026-06-01T10:03:00Z',
    },
  ],
  conv_002: [
    {
      // 第二个会话的用户消息，用于验证切换会话后消息流会变化。
      id: 'msg_005',
      conversation_id: 'conv_002',
      role: 'user',
      sender_id: 'user',
      content: '@ReviewAgent 帮我检查首页交互风险',
      artifacts: [],
      created_at: '2026-06-01T09:40:00Z',
    },
    {
      // Review Agent 的普通文本回复，用于验证没有 artifact 的消息也能渲染。
      id: 'msg_006',
      conversation_id: 'conv_002',
      role: 'agent',
      sender_id: 'review-agent',
      content: '建议优先检查按钮状态、空状态和移动端文本换行。',
      artifacts: [],
      created_at: '2026-06-01T09:41:00Z',
    },
  ],
}

/**
 * workspace 预览状态表。
 * key 是 workspace_id，value 对齐 WorkspacePreview；后续 Apply Diff mock 会更新这里。
 */
export const mockPreviewByWorkspaceId: Record<string, WorkspacePreview> = {
  ws_001: {
    // 主 Demo 会话初始未应用 Diff，因此预览未启动。
    workspace_id: 'ws_001',
    status: 'not_started',
  },
  ws_002: {
    // 单聊 review 示例给一个 ready 状态，便于右侧预览状态展示差异。
    workspace_id: 'ws_002',
    status: 'ready',
  },
}
