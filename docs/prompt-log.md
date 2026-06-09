# AgentHub Prompt Log

本文件记录重要 AI Coding 提示、产品决策和实现结果，便于复盘 AgentHub 的迭代过程。

## 2026-06-09：流式体验与 Orchestrator Harness

- Tool：Codex
- Task：修复一次性输出、无 `@Agent` 不响应、Orchestrator 任务拆解复制用户原话、Preview Agent 职责不清。
- Prompt：要求新增 SSE 流式接口、默认 Orchestrator 入口、角色化任务拆解、Preview Agent 预览验证、执行 harness。
- Result：实现 `/messages/stream`，前端 draft 气泡按 `agent_delta` 更新；无 `@` 走 Orchestrator；harness 输出 `harness_step`；Preview Agent 保留为预览验证角色。
- Review notes：前端必须按 conversationId 隔离流式状态，否则切换会话会出现回复污染。

## 2026-06-09：真实 LLM 与 Schema 鲁棒性

- Tool：Codex
- Task：检查后端是否误用 Mock Agent，修复结构化输出不可用和错误提示误导。
- Prompt：Orchestrator 任务拆解必须调用大模型；schema 错误不能提示 `.env`；结构化 JSON 不裸露给用户。
- Result：RealAgent 增加 repair、归一化和 Markdown/HTML artifact salvage；API runtime 返回 provider/model/key 配置状态；前端展示 Mock 后端警告。
- Review notes：最终 schema 失败要分类为模型输出结构不合法，配置/网络错误才提示 `.env`。

## 2026-06-09：Todo 固定模板与 Preview 路由

- Tool：Codex
- Task：修复 Todo 输出被固定模板覆盖、Preview 打开错误 URL、workspace preview 与代码不一致。
- Prompt：移除固定 Todo 模板；Apply Diff 后 preview_url 必须指向本次代码入口。
- Result：Code Agent 保留模型产物优先，缺交互时 repair；Apply Diff 返回 `preview_url` 和 `entry_path`；preview-page 支持 `?path=`。
- Review notes：不要用兜底模板掩盖模型真实输出差异。

## 2026-06-09：Phase 1 IM 核心补齐

- Tool：Codex
- Task：补齐会话归档、消息引用、复制、软删除、重新生成、长期上下文 pin。
- Prompt：要求不破坏流式消息、Agent 执行、workspace preview、Apply/Revert Diff。
- Result：Conversation 增加 `status`；Message 增加 `reply_to_id`、`regenerated_from_id`、`is_context_pinned`、`deleted_at`；新增软删除、pin、regenerate stream API；前端补消息操作区。
- Review notes：regenerate 不重复创建用户消息，只追加新的 Agent 回复。

## 2026-06-10：Phase 3 自建 Agent

- Tool：Codex
- Task：实现前端可自建 Agent，并更新交付材料。
- Prompt：用户要求前端自建 Agent 时可以输入系统提示词；交付物根据现有项目已实现内容整理。
- Result：新增 CustomAgent 模型、repository、SQLite 表、管理 API、CustomAgentAdapter；前端新增自建 Agent 管理弹窗；启用后的自建 Agent 可加入会话并通过 `@名称` 调用。
- Review notes：第一版自建 Agent 复用全局 LLM 配置，不保存 API Key；不进入 Orchestrator 自动开发计划，避免影响内置开发链路。

## 验证记录模板

- Date:
- Command:
- Result:
- Notes:
