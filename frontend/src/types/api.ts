/**
 * 会话模式，对齐后端 Conversation.mode。
 * single 表示用户和一个 Agent 单聊；group 表示多个 Agent 在同一会话协作。
 */
export type ConversationMode = 'single' | 'group'

/**
 * 消息角色，对齐后端 Message.role。
 * user 是用户消息；agent 是 Agent 回复；system 是系统状态或流程提示。
 */
export type MessageRole = 'user' | 'agent' | 'system'

/**
 * Agent 的业务角色，对齐后端 Agent.role。
 * 前端用它决定头像标签、能力说明和后续 @Agent 菜单分组。
 */
export type AgentRole =
  | 'orchestrator'
  | 'code'
  | 'review'
  | 'preview'
  | 'custom'

/**
 * Agent 的适配器类型，对齐后端 Agent.adapter_type。
 * MVP 默认 mock；真实接入时再使用 codex、claude、opencode 或 custom。
 */
export type AgentAdapterType =
  | 'mock'
  | 'codex'
  | 'claude'
  | 'opencode'
  | 'custom'

/**
 * 结构化产物类型，对齐后端 ArtifactType。
 * code/diff/preview 是 Demo 主链路优先展示的三类产物。
 */
export type ArtifactType = 'code' | 'diff' | 'preview' | 'file' | 'deploy'

/**
 * 会话对象，对齐后端 schemas/conversation.py。
 * 一个会话绑定一组 Agent 和一个 workspace，聊天历史和产物都挂在会话下。
 */
export type Conversation = {
  /** 会话唯一 ID，例如 conv_001。 */
  id: string
  /** 会话标题，展示在左侧会话列表和聊天头部。 */
  title: string
  /** 会话模式：单聊 single 或群聊 group。 */
  mode: ConversationMode
  /** 当前会话参与的 Agent ID 列表。 */
  agent_ids: string[]
  /**
   * 是否置顶。
   * 这是本轮为会话列表操作补充的字段，后端 schema 需同步持久化；置顶会话在列表中优先展示。
   */
  is_pinned: boolean
  /** 会话绑定的 workspace ID，用于文件、Diff 和预览接口。 */
  workspace_id: string
  /** 创建时间，使用 ISO 字符串，便于前端格式化。 */
  created_at: string
  /** 最近更新时间，左侧会话列表按该字段排序。 */
  updated_at: string
}

/**
 * Agent 产物对象，对齐后端 schemas/artifact.py。
 * 前端只依赖 type/title/data 渲染不同卡片，不在顶层随意新增业务字段。
 */
export type Artifact = {
  /** 产物唯一 ID，用作 React key 和后续 Apply Diff 等操作的定位值。 */
  id: string
  /** 产物类型，决定由 code/diff/preview/file/deploy 哪种卡片渲染。 */
  type: ArtifactType
  /** 产物标题，展示在 Artifact 卡片头部。 */
  title: string
  /** 产物内容载荷；具体字段由 type 决定，例如 code 使用 filename/language/content。 */
  data: Record<string, unknown>
  /** 产物创建时间，使用 ISO 字符串。 */
  created_at: string
}

/**
 * 聊天消息对象，对齐后端 schemas/message.py。
 * 每条消息可以携带多个 Artifact，从而在聊天流中内联展示结构化产物。
 */
export type Message = {
  /** 消息唯一 ID，例如 msg_001。 */
  id: string
  /** 消息所属会话 ID。 */
  conversation_id: string
  /** 消息角色：用户、Agent 或系统。 */
  role: MessageRole
  /** 发送者 ID；用户固定 user，Agent 使用 agent.id。 */
  sender_id: string
  /** 消息正文，展示在聊天气泡中。 */
  content: string
  /** 消息携带的结构化产物列表。 */
  artifacts: Artifact[]
  /** 消息创建时间，使用 ISO 字符串。 */
  created_at: string
}

/**
 * Agent 联系人对象，对齐后端 schemas/agent.py。
 * 前端用它展示 Agent 列表、能力标签和 @Agent 候选项。
 */
export type Agent = {
  /** Agent 唯一 ID，例如 code-agent。 */
  id: string
  /** Agent 展示名称，例如 Code Agent。 */
  name: string
  /** Agent 角色，用于分组、标签和调度语义展示。 */
  role: AgentRole
  /** Agent 能力说明，展示在联系人列表中。 */
  description: string
  /** 能力标签列表，例如 code、diff、preview。 */
  capabilities: string[]
  /** 背后的适配器类型；当前前端 mock 数据默认 mock。 */
  adapter_type: AgentAdapterType
}

/**
 * 调用 Agent 的请求体，对齐当前后端 AgentRunInput。
 * 注意：项目文档里曾出现 agent_id/message 示例，当前仓库以后端 schema 为准。
 */
export type AgentRunInput = {
  /** 本次调用所属会话 ID。 */
  conversation_id: string
  /** 本次调用使用的 workspace ID。 */
  workspace_id: string
  /** 用户原始消息内容，包含 @Agent 文本也原样传入。 */
  user_message: string
  /** 当前会话历史，后端 Agent 可基于上下文继续生成。 */
  history: Message[]
  /** 扩展上下文；当前约定 context.agent_id 表示目标 Agent。 */
  context: Record<string, string>
}

/**
 * Agent 调用结果，对齐当前后端 AgentRunResult。
 * 前端收到后可追加成 Agent 消息，也可抽取 artifacts 展示到右侧产物面板。
 */
export type AgentRunResult = {
  /** 实际返回结果的 Agent ID。 */
  agent_id: string
  /** Agent 的自然语言回复。 */
  content: string
  /** Agent 生成的结构化产物列表。 */
  artifacts: Artifact[]
  /** 建议的后续动作，例如 review、preview。 */
  next_actions: string[]
}

/**
 * workspace 预览状态。
 * 后端当前只返回 workspace_id/status；preview_url 是文档未明确但预览 iframe 需要的可选字段。
 */
export type WorkspacePreview = {
  /** workspace 唯一 ID。 */
  workspace_id: string
  /** 预览生命周期状态：未开始、运行中、已就绪或失败。 */
  status: 'not_started' | 'running' | 'ready' | 'error'
  /** 可选预览 URL；后端补充后可直接用于 iframe。 */
  preview_url?: string
}

/**
 * 新建会话的前端输入。
 * 后端文档尚未明确 POST /api/conversations 请求体，先采用最小必要字段。
 */
export type CreateConversationInput = {
  /** 新会话标题。 */
  title: string
  /** 新会话模式。 */
  mode: ConversationMode
  /** 初始参与的 Agent ID 列表。 */
  agent_ids: string[]
  /**
   * 是否创建后直接置顶。
   * 该字段可选，当前 UI 新建会话默认不置顶，mock 会兜底为 false。
   */
  is_pinned?: boolean
}

/**
 * 更新会话的前端请求体。
 * 当前只开放置顶状态，保留 title/mode/agent_ids 是为了后续编辑会话时复用 PATCH 接口。
 */
export type UpdateConversationInput = {
  /** 可选新标题；未传时不修改。 */
  title?: string
  /** 可选会话模式；未传时不修改。 */
  mode?: ConversationMode
  /** 可选 Agent ID 列表；未传时不修改。 */
  agent_ids?: string[]
  /** 可选置顶状态；未传时不修改。 */
  is_pinned?: boolean
}

/**
 * 删除会话的响应体。
 * 后端当前未明确 DELETE 返回结构，前端 mock 使用最小可读结果。
 */
export type DeleteConversationResult = {
  /** 被删除的会话 ID。 */
  id: string
  /** 是否删除成功。 */
  deleted: boolean
}

/**
 * 新建消息的前端输入。
 * 后端文档尚未明确 POST /api/conversations/{conversation_id}/messages 请求体，
 * 这里先采用最小必要字段：谁发送了什么内容。
 */
export type CreateMessageInput = {
  /** 消息发送者 ID；用户消息固定传 user，Agent 消息后续会传 agent.id。 */
  sender_id: string
  /** 消息正文，来自聊天输入框。 */
  content: string
  /**
   * 可选结构化产物。
   * 后端请求体尚未明确，当前只在前端 mock 中用于保存 Agent 回复生成的 artifacts。
   */
  artifacts?: Artifact[]
}

/**
 * Apply Diff 的前端请求体。
 * 后端文档只声明 POST /api/workspaces/{workspace_id}/apply-diff，未明确请求体；
 * 当前前端 mock 使用 artifact_id 定位按钮状态，使用 diff 字符串模拟应用内容。
 */
export type ApplyDiffInput = {
  /** 被应用的 diff artifact ID，用于让同一张 Diff 卡片展示 applied 状态。 */
  artifact_id: string
  /** unified diff 字符串，来自 diff artifact 的 data.diff。 */
  diff: string
}

/**
 * Apply Diff 的前端响应体。
 * 后端文档未明确返回结构，当前 mock 返回 workspace 状态和应用时间，方便刷新 Preview。
 */
export type ApplyDiffResult = {
  /** 本次应用变更所属 workspace。 */
  workspace_id: string
  /** 应用后的预览状态；mock 中成功应用后会变为 ready。 */
  status: WorkspacePreview['status']
  /** 成功应用的 diff artifact ID。 */
  applied_artifact_id: string
  /** 应用时间，使用 ISO 字符串。 */
  applied_at: string
}
