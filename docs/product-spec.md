# AgentHub 产品设计文档

最后更新：2026-06-10  
阶段：课程项目 / 可演示 MVP  
交付定位：IM 聊天式多 Agent 协作平台

## 1. 产品定位

AgentHub 是一个以 IM 聊天为核心交互范式的多 Agent 协作平台。用户不需要进入复杂的 IDE 或工作流编排器，只要像在飞书、微信里发消息一样创建会话、选择 Agent、发送需求，就可以让 Orchestrator、Code Agent、Review Agent、Preview Agent、Codex、Claude Code 或自建 Agent 在同一个对话中协作完成开发任务。

项目要证明的核心能力不是“单次生成一段代码”，而是把开发协作拆成一条可观察、可回放、可确认的产品链路：

```txt
用户提出需求
-> Orchestrator 理解和拆解任务
-> 多个 Agent 分工输出
-> 聊天流中展示 Markdown、代码、Diff、Preview 等产物
-> 用户点击 Apply Diff 确认写入 workspace
-> Workspace Preview 展示真实页面效果
-> 用户继续对话迭代或 Revert 回退变更
-> 聊天历史保留完整协作过程
```

这条链路对应评审中的功能完整度、生成效果质量、代码理解度和产品感，也让 AI 协作过程从“黑箱调用模型”变成“有规则、有记录、有产物、有校验”的工程流程。

## 2. 背景与问题

传统 AI Coding 工具通常以命令行、IDE 插件或单 Agent 聊天为入口。它们在个人开发效率上很强，但对课程展示和多人理解有几个问题：

- 过程不可见：模型如何拆任务、哪个 Agent 负责什么、是否经过 Review 和 Preview，很难在 UI 中看清。
- 产物和对话割裂：模型回复、代码文件、Diff、预览 URL 分散在不同工具中，用户需要手动切换。
- 多会话容易混乱：不同任务的历史、产物、workspace 状态容易相互污染。
- Agent 接入差异大：OpenAI-compatible、Codex CLI、Claude Code CLI、自建 Agent 的调用方式不同，业务层如果直接耦合平台会很难扩展。
- AI 生成结果不稳定：结构化输出、预览路由、代码可交互性、Schema 错误都需要产品层和工程层的兜底设计。

AgentHub 的产品答案是：用 IM 作为统一入口，用 Artifact 作为统一产物抽象，用 Workspace 作为真实代码载体，用 Adapter 作为多 Agent 接入协议。

## 3. 目标用户

### 3.1 课程评审者

评审者希望快速判断系统是否从 0 到 1 跑通，而不是只看局部代码。AgentHub 为评审者提供：

- 清晰的三栏界面：会话、聊天、workspace/产物。
- 可演示主链路：需求、拆解、代码、Diff、Apply、Preview、Revert。
- 可解释的架构：FastAPI 服务层、Agent Adapter、Orchestrator harness、WorkspaceService。
- AI 协作记录：Prompt Log、AGENTS 规则、审查清单和决策记录。

### 3.2 使用 AI 完成小型开发任务的开发者

开发者可以把 AgentHub 当成本地开发工作台，用自然语言生成工具页、网页 Demo、组件或代码修改，并在 Apply Diff 前确认变更。

### 3.3 需要管理多个角色 Agent 的团队

团队可以把不同能力的 Agent 加入同一会话，例如需求澄清、代码实现、代码审查、预览验证、文案写作等，并通过自建 Agent 的 system prompt 固化角色。

## 4. 产品目标与非目标

### 4.1 当前目标

- 提供完整 IM 基础体验：会话列表、创建会话、成员管理、消息发送、引用、复制、删除、pin、重新生成、归档。
- 跑通多 Agent 开发主链路：Orchestrator 拆解，Code/Review/Preview 依次产出。
- 支持真实 LLM 与 Mock 切换，并在前端提示当前运行模式。
- 用 SSE 实现可感知流式体验，避免用户长时间等待后一次性看到整段回复。
- 将模型产物结构化为 artifact：`code`、`diff`、`preview`、`file`、`deploy`。
- 让 Apply Diff 写入真实 workspace，并支持 preview 和 revert。
- 支持自建 Agent，允许用户输入名称、描述、能力标签、系统提示词，并选择后端。
- 接入 Codex 和 Claude Code 作为独立 Agent，不破坏 Orchestrator 的内置开发链路。
- 沉淀 AI 协作规范、Prompt 记录、审查清单和技术决策，支撑答辩解释。

### 4.2 当前非目标

- 不做企业级用户、权限、租户、审计系统。
- 不做多人实时协同编辑。
- 不做复杂部署平台和生产级发布流水线。
- 不把 Orchestrator 扩展成任意图式并行调度平台；MVP 以稳定演示链路优先。
- 不在前端保存供应商 API Key；敏感配置只在后端 `.env`。

## 5. 信息架构与界面

AgentHub 前端采用三栏结构：

```txt
左栏：会话列表 + Agent 联系人
中栏：聊天流 + 消息操作 + 输入框
右栏：Workspace 文件 + Preview + Applied Diff 历史 + Artifact 面板
```

### 5.1 左栏：会话与 Agent

- 会话按置顶和更新时间排序，支持搜索。
- 会话支持 active/archived/all 筛选，归档不会删除消息或 workspace。
- 新建会话时选择参与 Agent；会话成员决定当前输入框 `@` 菜单范围。
- Agent 列表展示内置 Agent、Codex、Claude Code 和启用中的自建 Agent。
- 自建 Agent 管理弹窗支持创建、编辑、启用/禁用、删除、测试。

### 5.2 中栏：聊天流

- 用户消息立即出现。
- Agent 回复通过 SSE 逐段展示，前端再做视觉分块，形成更自然的打字体验。
- 生成中状态按 conversationId 隔离，切换会话不会显示其他会话正在回复。
- 每条消息提供回复、复制、重新生成、pin/unpin、软删除。
- Markdown 正文用于承载自然语言说明，artifact 卡片用于承载可执行操作。

### 5.3 右栏：Workspace 与产物

- Workspace 文件列表展示当前会话绑定的真实文件。
- HTML 文件可在弹窗或 preview-page 中预览。
- Apply Diff 后更新真实文件，刷新 `preview_url` 和 `entry_path`。
- Applied Diff 历史支持 Revert，恢复到应用前状态。
- Artifact 面板聚合当前会话所有结构化产物，方便演示时定位代码、Diff、预览。

## 6. 核心用户流程

### 6.1 开发任务主流程

1. 用户新建会话，例如 `Todo App Development`。
2. 选择 Orchestrator、Code Agent、Review Agent、Preview Agent。
3. 用户发送：`@Orchestrator 帮我做一个简洁的 Todo List 网页，支持新增、完成、删除和筛选。`
4. 后端保存用户消息，前端立刻展示。
5. Orchestrator 输出任务拆解，明确每个 Agent 的职责和依赖。
6. Code Agent 输出 Markdown 说明、代码 artifact 和 diff artifact。
7. Review Agent 检查前序代码和 diff，输出风险和建议。
8. Preview Agent 检查 workspace preview 状态，说明用户需要 Apply Diff 后查看效果。
9. 用户点击 Apply Diff，后端将 diff 写入真实 workspace。
10. 右侧 Preview 指向本次 HTML 入口，用户打开即可看到代码效果。
11. 用户继续要求改动或点击 Revert 回退。

### 6.2 普通聊天流程

1. 用户不 `@` 任何 Agent，直接发送 `你好`。
2. 后端默认进入 Orchestrator 智能入口。
3. Orchestrator 判断为普通对话，返回自然回复，不进入开发 harness。

这个设计解决了早期“没有 @Agent 时系统无响应”的体验断点。

### 6.3 直接指定 Agent

用户可以直接发送：

- `@CodeAgent 修改页面交互`
- `@ReviewAgent 帮我检查这段实现风险`
- `@PreviewAgent 看看当前 workspace preview 是否可用`
- `@Codex 帮我完成一个小型代码任务`
- `@ClaudeCode 分析这个 workspace`
- `@自建Agent名称 按你的角色提示词回答`

显式 `@Agent` 的优先级高于 Orchestrator 自动调度。

### 6.4 自建 Agent 流程

1. 用户打开“管理 Agent”。
2. 输入 Agent 名称、描述、能力标签、system prompt。
3. 选择后端：OpenAI-compatible、Codex、Claude Code。
4. 点击测试，测试结果以 Markdown 渲染。
5. 启用并加入会话成员。
6. 在聊天输入中通过 `@名称` 调用。

自建 Agent 不自动进入 Orchestrator 的开发计划，避免影响内置主链路；它更适合作为显式角色助手。

## 7. 功能完整度矩阵

| 模块 | 当前状态 | 说明 |
| --- | --- | --- |
| 会话列表 | 已实现 | 创建、切换、搜索、置顶、归档/恢复、删除 |
| 会话成员 | 已实现 | 新建会话选择 Agent，已有会话管理成员，支持全选/取消全选 |
| 消息流 | 已实现 | SSE 流式、draft 气泡、视觉分块、自动滚动到底部 |
| 消息操作 | 已实现 | 引用、复制、重新生成、pin/unpin、软删除 |
| 无 @ 默认响应 | 已实现 | 默认进入 Orchestrator 智能入口 |
| Orchestrator | 已实现 | LLM 决策优先，结构化失败时 repair/归一化/安全兜底 |
| Harness | 已实现 | plan -> run -> verify -> retry/fail；前端显示阶段状态 |
| Code Agent | 已实现 | 输出 Markdown、code artifact、diff artifact；支持交互性修复策略 |
| Review Agent | 已实现 | 输出 findings、risk_level 等审查结果 |
| Preview Agent | 已实现 | 验证 preview 状态，输出 preview artifact |
| Workspace 文件 | 已实现 | 文件列表、文本读取、删除、真实文件写入 |
| Apply Diff | 已实现 | 写入 workspace，记录 AppliedDiffRecord |
| Revert Diff | 已实现 | 基于 before/after 快照回退 |
| Preview URL | 已实现 | 支持 `preview-page?path=` 和嵌套资源 base 注入 |
| 自建 Agent | 已实现 | CRUD、测试、system prompt、启用状态、会话调用 |
| Codex / Claude Code | 已实现 | 作为独立内置 Agent 和可选自建 Agent 后端 |
| 二进制复杂产物 | 待增强 | 当前 CLI 产物采集偏向文本 diff，PDF/图片类附件需要后续 file artifact 打开链路 |
| 一键部署 | 未实现 | 保留 `deploy` artifact 类型，当前不做真实部署 |

## 8. 生成效果质量设计

### 8.1 流式体验

后端 SSE 事件保持稳定：

```txt
user_message -> harness_step -> agent_started -> agent_delta -> artifact -> agent_done -> done
```

前端收到 `agent_delta` 后不会整段瞬间刷出，而是按小块延迟追加，保证视觉体验接近真实打字。生成状态只显示在当前会话，避免跨会话污染。

### 8.2 Artifact 体验

Artifact 是 AgentHub 的关键产品抽象。用户不必从长文本里复制代码，而是直接看到：

- `code`：代码文件卡片，可复制代码。
- `diff`：分色 diff，可 Apply Diff。
- `preview`：预览状态和打开按钮。
- `file`：文件/计划/审查类产物的详情展示。
- `deploy`：为后续部署状态预留。

### 8.3 Preview 一致性

Apply Diff 后后端返回 `preview_url` 和 `entry_path`。前端右侧 Workspace 顶部预览、文件列表 HTML 预览、聊天 preview artifact 都尽量指向同一份代码对应的入口，避免“代码卡片是一份、打开预览是另一份”的错位。

## 9. AI 协作能力沉淀

评审权重最高的是 AI 协作能力。AgentHub 不只用 AI 生成代码，还把 AI 协作方法固化为项目资产：

- `AGENTS.md`：仓库级 AI Coding 指令，规定目标、技术栈、目录、Adapter、Orchestrator、Artifact、Git、安全和验收。
- `CODEX_TASK_TEMPLATE.md`：任务提示模板，帮助把需求拆成可执行开发任务。
- `CODEX_REVIEW_CHECKLIST.md`：AI 生成代码后的人工审查清单，覆盖运行、功能、安全、文档。
- `DECISION_LOG.md`：架构决策记录，用于答辩解释为什么选择 Python-first、FastAPI、Adapter 等。
- `docs/prompt-log.md`：记录关键 Prompt、问题、修复和验证结果。
- `docs/ai-rules.md`：精简 AI 协作原则，强调 Demo 主线、结构化产物和安全审查。
- 测试集：用 pytest 固化协作产物的行为边界，防止反复修同一类问题。

这些文档让 AI 从“临时写代码的工具”变成项目协作流程的一部分。

## 10. 评审维度映射

| 评审维度 | 权重 | AgentHub 对应设计 |
| --- | --- | --- |
| AI 协作能力 | 30% | AGENTS 规则、Prompt Log、Review Checklist、Decision Log、结构化计划、Adapter 协议、测试闭环 |
| 功能完整度 | 25% | IM 会话、消息操作、流式输出、多 Agent 调度、Apply/Revert Diff、Workspace Preview、自建 Agent |
| 生成效果质量 | 20% | Markdown 渲染、artifact 卡片、SSE 视觉分块、真实 preview、diff 分色、Mock guard |
| 代码理解度 | 15% | Python-first 分层架构、FastAPI route/service/repository、Agent Adapter、Orchestrator harness、WorkspaceService |
| 创新与产品感 | 10% | IM 化多 Agent 协作、自建 Agent、Codex/Claude 接入、会话级运行状态隔离、长期上下文 pin |


