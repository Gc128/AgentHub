# AgentHub Product Spec

AgentHub 是一个 IM 聊天式多 Agent 协作平台。用户像使用飞书/微信一样创建会话、选择 Agent、发送消息，并通过 `@Agent` 让多个 AI Agent 在同一会话中协作完成开发任务。

## 目标用户

- 希望用对话方式完成前端页面、工具页或小型工作流开发的开发者。
- 需要可观察多 Agent 协作过程的团队或课程评审者。
- 需要稳定演示“需求 -> 代码 -> Diff -> Apply -> Preview -> 继续迭代”的 Demo 使用者。

## 核心流程

1. 用户创建或选择一个会话，选择参与会话的 Agent。
2. 用户发送普通消息、`@Orchestrator` 任务，或直接 `@CodeAgent`、`@ReviewAgent`、`@PreviewAgent`、自建 Agent。
3. 后端保存用户消息，并通过 SSE 流式返回 Agent 进度和正文。
4. Orchestrator 对开发任务进行任务拆解，执行 `plan -> run -> verify -> retry/fail` harness。
5. Code Agent 返回代码与 diff artifact；用户点击 Apply Diff 写入真实 workspace。
6. Workspace Preview 打开当前代码入口；用户可查看文件、回退已应用 diff。
7. 会话保留完整协作历史，支持引用、复制、软删除、pin 长期上下文和重新生成。

## 已实现能力

- IM 会话：创建、切换、置顶、归档/恢复、删除、按 active/archived/all 筛选。
- 消息体验：用户消息与 Agent 消息展示、SSE 流式输出、按会话隔离生成状态、自动滚动到底部。
- 消息操作：引用回复、复制、软删除、pin/unpin 长期上下文、基于用户消息重新生成。
- Agent 调度：无 `@` 默认进入 Orchestrator；显式 `@Agent` 优先运行目标 Agent。
- Orchestrator：真实 LLM 决策优先，schema 失败时做安全兜底；开发任务进入 harness。
- 内置 Agent：Orchestrator、Code Agent、Review Agent、Preview Agent。
- 自建 Agent：前端可创建、编辑、启用/禁用、删除、测试；支持名称、描述、能力标签和系统提示词。
- Workspace：真实文件读写、文件列表、文件内容查看、Apply Diff、Revert Diff。
- Preview：Apply Diff 后返回真实 `preview_url` 和 `entry_path`，支持指定 HTML 文件预览。
- Runtime Guard：前端可展示当前是否连接 Mock Agent 后端，避免误用模拟数据。

## 当前边界

- 自建 Agent 第一版复用全局 LLM 配置，不支持为每个 Agent 单独配置 API Key、模型或 base URL。
- 自建 Agent 只在用户显式 `@` 或会话成员中直接使用，不参与 Orchestrator 自动开发计划。
- 当前重点是本地 Demo 和课程项目交付，不包含企业权限、多人实时协同或部署平台。
- 历史 Flask demo 仅作为兼容参考；默认演示链路是 React + FastAPI。

## 后续方向

- 多后端配置：按 Agent 选择 OpenAI-compatible、Anthropic-compatible、CLI coding agent 等后端。
- 更完整的 Agent 市场：导入/导出 Agent 配置、模板库、能力分组和版本管理。
- 更强 preview 验证：浏览器自动交互测试、截图回传、可访问性检查。
- 部署闭环：把 workspace 产物发布到可分享 URL，并记录部署 artifact。
