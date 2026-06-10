# AgentHub AI 协作开发 Prompt Log

最后更新：2026-06-10  
记录范围：2026-05-22 至 2026-06-10  
文档定位：展示 AgentHub 在 AI Coding 中如何使用 Prompt、Rules、Spec、Skill 和人工 Review，把一个 IM 多 Agent 协作平台从 0 到 1 做出来。

## 1. 文档概览

AgentHub 的 AI 协作开发不是简单地把需求丢给模型，而是逐步形成了一套可复用的工作方式：

```txt
需求文档
-> 规则文件 AGENTS.md
-> 分阶段开发计划
-> 市面 / GitHub Skill 辅助理解
-> 自建 AgentHub Skill 固化项目经验
-> Codex / Claude / LLM 执行
-> 人工 Review
-> 测试验证
-> Prompt Log 复盘
```

本文件重点回答三个问题：

1. 我们用什么 Prompt 驱动 AI 开发？
2. 我们使用或参考了哪些市面 / GitHub Skill？
3. 我们沉淀了哪些适合 AgentHub 项目的自建 Skill？

这些内容对应评审中的“AI 协作能力”维度，证明项目不只是功能堆叠，而是把 AI 协作过程本身产品化、规范化和可复盘化。

## 2. AI 协作资产总览

| 类型 | 文件或 Skill | 作用 |
| --- | --- | --- |
| 项目规则 | `AGENTS.md` | 仓库级 AI Coding 指令，规定主线、目录、接口、安全和验证 |
| AI 规则 | `docs/ai-rules.md` | 团队使用 AI Coding 的详细规则 |
| Prompt 记录 | `PROMPT_LOG.md`、`docs/prompt-log.md` | 记录关键 Prompt、问题、修复和复盘 |
| Review 清单 | `CODEX_REVIEW_CHECKLIST.md` | 人工检查 AI 生成代码的 checklist |
| 决策记录 | `DECISION_LOG.md` | 记录 Python-first、Adapter 等技术取舍 |
| GitHub Skill | `understand-anything` | 分析代码库、生成知识图谱、辅助架构理解 |
| 平台 Skill | Browser / Docs 类 Skill | 辅助前端验收、文档查询和交付物整理 |
| 自建 Skill | AgentHub 系列 Skill | 固化本项目专属工作流，例如 Orchestrator、SSE、Workspace Preview |

## 3. Prompt 方法论

### 3.1 先定边界，再让 AI 开发

AgentHub 中几乎所有复杂任务都采用“计划先行”的方式。Prompt 必须明确允许修改和禁止修改的范围。

推荐 Prompt：

```txt
请完成以下任务：

目标：
- 修复 AgentHub 中消息软删除功能。

允许修改：
- agenthub/services/message_service.py
- agenthub/api/messages.py
- agenthub/schemas/message.py
- tests/test_api.py

禁止修改：
- 不改 AgentService 调度逻辑。
- 不改 WorkspaceService。
- 不改 SSE 事件名。

验收标准：
- 删除后消息仍在时间线中。
- deleted_at 存在。
- artifacts 清空。
- 被删除消息不进入 Agent history。
```

效果：

- AI 不会无边界重构。
- Review 时能按文件范围检查。
- 测试目标清晰。

### 3.2 用用户截图和现象驱动修复

很多高价值修复不是来自测试失败，而是来自真实 UI 截图。

典型 Prompt：

```txt
我在会话 A 中让 AgentHub 执行一个长任务，立即切到会话 B。
会话 B 也显示“Agent 正在生成回复”，说明生成状态被全局复用了。
请检查前端状态结构，把 messages、draft、agentRunning、generationNotice
全部按 conversationId 隔离。不要改变 SSE 事件名。
```

效果：

- 修复了会话状态污染。
- 形成 `messagesByConversationId`、`agentRunningByConversationId` 等状态设计。

### 3.3 要求 AI 解释原因，而不是只改表象

典型 Prompt：

```txt
自建 Agent 回复中出现 custom-agent_xxx 字段。
请先查清这个字段来自后端 content、sender_id、agent_id 还是前端展示名称映射。
查清原因后，以最小改动修复聊天消息、生成中状态和测试 Agent 输出。
```

效果：

- 修复了内部 id 泄漏。
- 保留历史消息的 sender_id，但展示层使用 Agent name。
- 测试 Agent 输出改为 Markdown 渲染。

### 3.4 明确禁止“假成功”

早期为了保证 Todo Demo 成功，系统曾有固定 Todo 兜底模板。后来用户发现不同需求生成相同页面。

改进 Prompt：

```txt
不要再用固定 Todo 模板覆盖模型输出。
Code Agent 必须保留真实模型产物；如果缺少交互，优先在原代码基础上 repair。
只有模型完全不可用时才说明失败，不能静默套最小兜底模板。
```

效果：

- 提升生成差异化。
- 避免 demo 看起来成功但实际不响应用户需求。

## 4. 高质量 Prompt 库

### Prompt A：项目初始化与架构规划

```txt
请基于“AgentHub 多 Agent 协作平台”的需求，设计 Python-first MVP 架构。

要求：
1. 核心交互是 IM 聊天，不是传统表单工具。
2. 主链路必须是：用户需求 -> Orchestrator -> 多 Agent -> code/diff/preview artifact -> Apply Diff -> Preview。
3. 后端使用 FastAPI、Pydantic、SQLite、httpx、pytest、ruff、mypy。
4. 前端可以使用 React/Vite/TypeScript/Ant Design。
5. 输出目录结构、核心模型、API、Agent Adapter 协议、测试计划和暂缓功能。
```

使用阶段：项目 0 到 1 初始化。  
产出影响：形成 Python-first、三层后端、React IM 前端和 Adapter 架构。

### Prompt B：流式输出体验

```txt
当前前端等待很久后一次性展示 Agent 回复，体验不好。
请新增 /messages/stream SSE 接口，事件必须保持：
user_message、harness_step、agent_started、agent_delta、artifact、agent_done、error、done。
前端发送消息后立即展示用户消息，并创建 Agent draft 气泡，随着 agent_delta 一段段更新。
最终用 agent_done 中落盘的消息替换 draft。
```

使用阶段：流式体验改造。  
产出影响：实现 SSE 主链路和前端视觉分块。

### Prompt C：Orchestrator 真实 LLM 决策

```txt
Orchestrator 的任务拆解不能是规则式复制用户需求。
请让 Orchestrator 调用真实 LLM，输出 OrchestratorDecision：
mode = chat | plan；
plan 中只能调度 code-agent、review-agent、preview-agent。
每个任务 instruction 要角色化，不能复制用户原文。
结构化失败时可以 repair 和归一化，但不要把 schema 错误裸露给用户。
```

使用阶段：真实 LLM 接入和 Orchestrator 稳定性。  
产出影响：LLM 决策优先，规则计划变成安全兜底。

### Prompt D：Schema 错误鲁棒性

```txt
模型经常返回不符合 AgentRunResult schema 的内容。
请增强 RealAgent：
1. 支持 JSON fence、顶层 list、content 内嵌 JSON。
2. 第一次失败后请求同一模型 repair。
3. repair 失败后从 Markdown code block 和 HTML 文档中 salvage artifact。
4. 最终错误按 schema/config/network 分类。
```

使用阶段：真实模型联调。  
产出影响：减少“结构化输出不可用”的用户可见错误。

### Prompt E：Workspace Preview 一致性

```txt
生成代码后，Preview 打开的不是当前代码对应页面。
请检查 apply_diff、WorkspacePreviewResponse、preview-page 和前端打开按钮。
要求 Apply Diff 后返回 preview_url 和 entry_path；
preview-page 支持 ?path=；
嵌套 HTML 文件要按入口目录注入 base，保证 CSS/JS 能加载。
```

使用阶段：Preview 修复。  
产出影响：Preview 与真实 workspace 文件一致。

### Prompt F：Phase 1 IM 核心补齐

```txt
实现 Phase 1：会话归档、消息引用、复制、软删除、重新生成、长期上下文 pin。
不要破坏现有流式消息、Agent 执行、Workspace Preview、Apply/Revert Diff。
旧接口默认行为保持不变。
```

使用阶段：IM 功能完善。  
产出影响：AgentHub 从 Demo 工具进化为更完整的聊天式产品。

### Prompt G：自建 Agent

```txt
实现前端自建 Agent 功能。
用户可以输入名称、描述、能力标签、系统提示词，并选择后端。
启用后的自建 Agent 可加入会话成员，出现在 @ 菜单中。
自建 Agent 第一版不保存独立 API Key，复用全局后端配置。
不要影响 Orchestrator 内置开发链路。
```

使用阶段：Phase 3 Agent 管理。  
产出影响：实现 CustomAgent 模型、API、Adapter 和前端管理弹窗。

### Prompt H：Codex / Claude Code 接入

```txt
请接入 Codex 和 Claude Code，作为独立内置 Agent。
它们要像 Orchestrator、Code Agent 一样出现在常用 Agent 列表中，
但不能进入 Orchestrator 默认开发 harness。
调用必须通过统一 ExternalCliAgentAdapter，在临时 workspace 副本中运行 CLI，
比较前后文件差异并生成 code/diff artifact。
```

使用阶段：多后端接入。  
产出影响：Codex 和 Claude Code 成为独立 Agent，也可作为自建 Agent 后端。

### Prompt I：代码审查

```txt
请以 code review 视角审查本次 diff。
重点找 bug、状态污染、路径越权、API 不兼容、测试缺失、用户可见体验退化。
输出 Findings first，按严重程度排序，给出文件和行号。
如果没有发现问题，也要说明剩余风险和建议验证命令。
```

使用阶段：每次重要改动后。  
产出影响：减少 AI 自动生成代码的盲点。

### Prompt J：答辩文档整理

```txt
请根据 AgentHub 当前代码和开发过程，整理产品设计文档、技术文档、AI 协作开发记录。
必须映射评审维度：
AI 协作能力、功能完整度、生成效果质量、代码理解度、创新与产品感。
不要只列功能，要解释为什么这样设计、如何实现、如何验证、还有哪些边界。
```

使用阶段：最终交付材料整理。  
产出影响：形成 `docs/product-spec.md`、`docs/tech-design.md`、`docs/prompt-log.md`。

## 5. 市面 / GitHub Skill 使用记录

本节记录“市面已有或 GitHub 下载的 Skill / 插件式能力”。这些 Skill 的作用不是替代开发，而是帮助 AI 更快理解代码、审查变更、验证 UI 或生成交付物。

### Skill 1：Understand Anything Codebase Graph

来源：GitHub 插件 `Lum1104/Understand-Anything`  
本地路径：

```txt
/Users/chenzhe/.understand-anything/repo/understand-anything-plugin/skills/understand/SKILL.md
```

用途：

- 扫描 AgentHub 代码库。
- 生成 `.understand-anything/knowledge-graph.json`。
- 提取文件、模块、函数、层级、依赖关系。
- 支撑后续架构问答和 diff 分析。

典型 Prompt：

```txt
使用 understand-anything:understand，以中文理解 AgentHub 整个项目。
请生成知识图谱，重点识别 FastAPI、React、Agent Adapter、Orchestrator、Workspace、Preview 的关系。
```

在 AgentHub 中的使用：

- 用于早期理解前后端结构。
- 用于整理 `docs/project-architecture.md`。
- 用于答辩准备，解释“用户消息如何流经系统”。

Skill 规则摘要：

```txt
1. 确认项目根目录。
2. 检查是否已有 knowledge-graph.json。
3. 扫描项目文件和 manifest。
4. 按批次分析文件。
5. 生成 nodes、edges、layers、tour。
6. 输出 knowledge-graph.json。
7. 可选启动 dashboard 可视化。
```

### Skill 2：Understand Chat

来源：Understand Anything GitHub 插件  
本地路径：

```txt
/Users/chenzhe/.understand-anything/repo/understand-anything-plugin/skills/understand-chat/SKILL.md
```

用途：

- 基于 knowledge graph 向代码库提问。
- 不需要一次性读完整项目。
- 通过搜索 node、edge、layer 回答架构问题。

典型 Prompt：

```txt
基于 AgentHub 的 knowledge graph，解释一条消息从前端输入到后端 MessageService、
AgentService、Agent Adapter、Workspace Preview 的完整链路。
```

在 AgentHub 中的使用：

- 辅助理解 `AgentService` 为什么是调度中心。
- 辅助确认 `WorkspaceService` 与 `api/workspaces.py` 的关系。
- 辅助整理技术文档中的架构图和调用链。

Skill 内容摘要：

```txt
1. 检查 .understand-anything/knowledge-graph.json。
2. 读取 project metadata。
3. 搜索与问题相关的 nodes。
4. 查找匹配节点的一跳 edges。
5. 读取 layer context。
6. 基于相关子图回答问题，并引用具体文件和关系。
```

### Skill 3：Understand Diff

来源：Understand Anything GitHub 插件  
用途：

- 分析当前 git diff 改了哪些组件。
- 根据知识图谱找受影响模块。
- 评估跨层风险。

典型 Prompt：

```txt
请使用 understand-diff 分析当前改动。
重点判断是否影响 SSE 流式消息、Orchestrator 调度、Workspace Preview、Custom Agent。
```

在 AgentHub 中的使用：

- 用于文档更新前确认没有误改业务代码。
- 用于大型功能后判断影响范围。
- 用于 Review Checklist 中的“影响模块”判断。

Skill 内容摘要：

```txt
1. 获取 changed files。
2. 读取 knowledge graph project metadata。
3. 为 changed files 找对应 nodes。
4. 根据 edges 找 upstream/downstream affected components。
5. 判断 affected layers。
6. 输出 Changed Components、Affected Components、Risk Assessment。
7. 写 diff-overlay.json，供 dashboard 展示。
```

### Skill 4：Understand Explain

来源：Understand Anything GitHub 插件  
用途：

- 深入解释某个文件、函数或模块。
- 结合知识图谱和源码说明输入、处理、输出、依赖关系。

典型 Prompt：

```txt
请使用 understand-explain 解释 agenthub/services/agent_service.py。
重点说明它如何完成 @Agent 路由、Orchestrator 决策、Harness 执行、流式输出和自建 Agent 调用。
```

在 AgentHub 中的使用：

- 准备答辩中“核心代码讲解”。
- 解释 `RealAgent` 的 repair/salvage 机制。
- 解释 `WorkspaceService.apply_diff()` 和 `revert_applied_diff()`。

Skill 内容摘要：

```txt
1. 在 knowledge graph 中找到目标 node。
2. 查找 incoming/outgoing edges。
3. 读取 connected nodes。
4. 识别所属 layer。
5. 读取实际源码。
6. 解释角色、内部结构、外部依赖、数据流和复杂点。
```

### Skill 5：Browser UI QA Skill

来源：Codex / Browser 插件能力  
用途：

- 打开本地前端页面。
- 点击按钮、输入消息、截图验证 UI。
- 检查流式输出、Preview、弹窗、成员选择等用户体验。

典型 Prompt：

```txt
请用 Browser 打开本地 AgentHub 前端，创建新会话，发送 @Orchestrator Todo 任务。
验证用户消息是否立即出现、Agent 是否流式输出、Apply Diff 后 Preview 是否能打开。
```

在 AgentHub 中的使用价值：

- 适合验证“自动滚动到底部”。
- 适合验证“打开预览按钮是否可点击”。
- 适合验证“自建 Agent 测试输出是否 Markdown 渲染”。

Skill 工作流：

```txt
1. 启动后端和前端。
2. 打开 localhost/Vite 页面。
3. 执行用户关键路径。
4. 截图或读取 DOM 状态。
5. 记录失败现象。
6. 回到代码中定位原因。
```

### Skill 6：OpenAI Docs / API Docs Skill

来源：Codex 内置 OpenAI 文档能力，或同类官方文档查询 Skill  
用途：

- 查询 OpenAI-compatible 调用方式。
- 校验 response_format、streaming、chat completions 的字段。
- 避免凭记忆写过时 API。

典型 Prompt：

```txt
请查询官方 OpenAI API 文档，确认 chat completions 的 streaming delta 结构和 response_format=json_object 用法。
然后对照 AgentHub RealAgent 的实现，指出需要注意的兼容性。
```

在 AgentHub 中的使用价值：

- 支撑 `RealAgent.stream()` 和 `_iter_stream_deltas()` 设计。
- 支撑结构化输出 repair 方案。
- 避免前端直接接触 API Key。

### Skill 7：Markdown / Docs Delivery Skill

来源：通用文档生成工作流 Skill，可由 Codex 文档类能力或团队自建模板承载  
用途：

- 把散乱开发记录整理成产品文档、技术文档、Prompt Log。
- 将功能实现映射到评审维度。

典型 Prompt：

```txt
请把 AgentHub 当前项目整理成 3 个交付文档：
产品设计文档、技术文档、AI 协作开发记录。
文档要覆盖评审表中的五个维度，并结合真实代码和开发过程。
```

在 AgentHub 中的使用价值：

- 生成 `docs/product-spec.md`。
- 生成 `docs/tech-design.md`。
- 生成 `docs/prompt-log.md`。

## 6. AgentHub 自建 Skill 设计

本节是项目中沉淀出的“自建 Skill”。它们不一定都已经安装成独立插件，但内容可以直接转化为 `skills/<skill-name>/SKILL.md`，体现团队把项目经验从 Prompt 上升为可复用能力。

### 自建 Skill 1：agenthub-architecture-navigator

触发场景：

- 需要解释 AgentHub 架构。
- 需要新人快速理解项目。
- 需要答辩讲解代码结构。

Skill 内容：

```markdown
---
name: agenthub-architecture-navigator
description: Use when explaining AgentHub architecture, module responsibilities, or end-to-end data flow.
---

# AgentHub Architecture Navigator

## Goal

Explain AgentHub from product flow to code modules without drifting into unrelated refactors.

## Workflow

1. Start from the demo path:
   User request -> Orchestrator -> Agents -> Artifacts -> Apply Diff -> Preview -> History.
2. Map each product step to code:
   - React state: frontend/src/App.tsx
   - API client: frontend/src/api/client.ts
   - Message route: agenthub/api/messages.py
   - Message service: agenthub/services/message_service.py
   - Agent service: agenthub/services/agent_service.py
   - Agent adapters: agenthub/agents/*
   - Workspace service: agenthub/services/workspace_service.py
3. Explain data models:
   Conversation, Message, Artifact, AgentRunInput, AgentRunResult, CustomAgent.
4. Explain boundaries:
   route is thin, service owns business logic, repository owns persistence, adapter owns backend calls.
5. End with one risk and one verification command.

## Output Format

- Product flow
- Module map
- Data flow
- Key design choices
- Known risks
```

在 AgentHub 中的价值：

- 让答辩时能解释代码理解度。
- 避免 AI 回答架构问题时泛泛而谈。

### 自建 Skill 2：agenthub-orchestrator-harness-guard

触发场景：

- 修改 Orchestrator。
- 修改 AgentService。
- 处理 schema 失败或任务拆解问题。

Skill 内容：

```markdown
---
name: agenthub-orchestrator-harness-guard
description: Use when changing AgentHub Orchestrator decisions, harness steps, schema repair, or multi-agent execution.
---

# AgentHub Orchestrator Harness Guard

## Non-negotiables

- Explicit @Agent routes to that Agent first.
- No @ message enters Orchestrator.
- Casual chat returns chat mode.
- Development work returns plan mode.
- Built-in harness only schedules code-agent, review-agent, preview-agent.
- Custom Agents do not enter automatic harness unless explicitly requested.
- Do not expose schema/internal errors to users.

## Workflow

1. Inspect route_agent and custom agent routing.
2. Inspect OrchestratorDecision schema.
3. Check RealAgent repair and relaxed recovery.
4. Confirm harness tasks include Code, Review, Preview for code work.
5. Verify each step emits harness_step and agent_delta.
6. Verify final result does not add a noisy harness summary.

## Acceptance

- @CodeAgent only runs Code Agent.
- @Orchestrator runs plan -> code -> review -> preview.
- “你好” returns natural chat.
- Schema failure becomes user-friendly message or safe plan.
```

在 AgentHub 中的价值：

- 防止 Orchestrator 回到早期规则式、写死式、裸错误式实现。
- 保证多 Agent 主链路稳定。

### 自建 Skill 3：agenthub-sse-streaming-debugger

触发场景：

- 前端不是流式输出。
- 切换会话时状态污染。
- draft 气泡不消失。
- 自动滚动异常。

Skill 内容：

```markdown
---
name: agenthub-sse-streaming-debugger
description: Use when debugging AgentHub SSE streaming, draft messages, generation state, or conversation isolation.
---

# AgentHub SSE Streaming Debugger

## Expected SSE Order

user_message -> harness_step -> agent_started -> agent_delta -> artifact -> agent_done -> done

## State Isolation Rules

- messagesByConversationId stores all messages.
- agentRunningByConversationId stores running state.
- generationNoticeByConversationId stores visible status.
- replyTargetsByConversationId stores reply target.
- Stream callbacks must capture the conversationId at send time.

## Debug Steps

1. Inspect frontend/src/api/client.ts requestSse.
2. Inspect App.tsx runConversationStream.
3. Confirm agent_delta appends to the correct draft.
4. Confirm agent_done replaces draft with persisted message.
5. Confirm done clears only the current conversation running state.
6. Confirm ChatPanel scrolls to messageEndRef on content length change.

## Common Bugs

- Global agentRunning causes cross-conversation pollution.
- agent_id displayed instead of agent name.
- draft remains after agent_done.
- delta arrives after draft is closed.
```

在 AgentHub 中的价值：

- 直接对应用户多次反馈的流式体验和会话污染问题。
- 可作为未来前端调试 SOP。

### 自建 Skill 4：agenthub-workspace-preview-guardian

触发场景：

- Apply Diff 后 preview 错误。
- HTML 入口不一致。
- 文件路径越权风险。
- Revert Diff 冲突。

Skill 内容：

```markdown
---
name: agenthub-workspace-preview-guardian
description: Use when changing WorkspaceService, apply diff, revert diff, preview-page, or preview assets.
---

# AgentHub Workspace Preview Guardian

## Core Rule

Agent output is suggestion. Real workspace write happens only after Apply Diff.

## Workflow

1. Normalize workspace path.
2. Reject path traversal.
3. Parse unified diff target.
4. Read current content.
5. Apply diff.
6. Save AppliedDiffRecord with before/after snapshots.
7. Select HTML entry_path.
8. Return preview_url and entry_path.
9. For preview-page, inject base by entry directory.
10. For revert, verify current content equals after_content before restoring.

## Acceptance

- todo.html returns preview-page?path=todo.html.
- pages/demo.html loads local CSS/JS relative to pages/.
- Revert restores previous content.
- Path ../escape.js fails.
```

在 AgentHub 中的价值：

- 保护 Demo 中最关键的“代码 -> Apply -> Preview”闭环。
- 防止 workspace 文件安全问题。

### 自建 Skill 5：agenthub-custom-agent-builder

触发场景：

- 新增自建 Agent 功能。
- 修改自建 Agent UI。
- 修复 system prompt、后端选择、测试输出、@ 菜单。

Skill 内容：

```markdown
---
name: agenthub-custom-agent-builder
description: Use when building or debugging AgentHub custom Agent creation, management, testing, and routing.
---

# AgentHub Custom Agent Builder

## Requirements

- User can input name, description, capabilities, system_prompt.
- system_prompt is required.
- Custom Agent can choose backend_id.
- UI never stores provider API Key.
- Enabled custom agents appear in /api/agents.
- Conversation members can include custom agents.
- @ custom agent routes by display name, not only id.
- Historical messages survive deletion of a custom agent.

## Debug Steps

1. Check CustomAgent schema/model/repository.
2. Check SQLite migration for backend_id.
3. Check AgentService _route_custom_agent.
4. Check CustomAgentAdapter backend selection.
5. Check CustomAgentManagerModal form and test output.
6. Check ChatPanel sender display name mapping.

## Common Bugs

- custom-agent_xxx leaks in content.
- Disabled agent still appears in @ menu.
- Markdown test output rendered as raw string.
- Deleting an agent breaks historical messages.
```

在 AgentHub 中的价值：

- 自建 Agent 是创新与产品感的重要加分点。
- Skill 固化了这一能力的边界，避免破坏内置主链路。

### 自建 Skill 6：agenthub-real-agent-schema-repair

触发场景：

- 出现“结构化输出不可用”。
- LLM 返回 JSON 字符串、Markdown fence、HTML 文档。
- Code/Review/Preview artifact 缺失。

Skill 内容：

```markdown
---
name: agenthub-real-agent-schema-repair
description: Use when debugging RealAgent JSON parsing, schema repair, artifact salvage, or user-facing error classification.
---

# AgentHub Real Agent Schema Repair

## Principle

Treat LLM output as unreliable text, not a typed API response.

## Recovery Order

1. Strip markdown JSON fence.
2. Try json.loads.
3. Extract first JSON object if text contains extra prose.
4. Normalize top-level list into AgentRunResult.
5. Unwrap nested JSON in content.
6. Normalize artifact id/type/title/data.
7. Request repair from same model.
8. Salvage Markdown code fences into code artifacts.
9. Salvage full HTML into code/diff artifacts.
10. If all fail, classify error as schema/config/network.

## User-facing Rule

- Schema failures do not mention .env.
- Config failures mention OPENAI_API_KEY / AGENT_BASE_URL / AGENT_MODEL.
- Transport failures mention network and timeout.
```

在 AgentHub 中的价值：

- 解决真实模型接入时最影响 Demo 稳定性的错误。
- 体现 AI 工程中对“不稳定模型输出”的系统性处理。

### 自建 Skill 7：agenthub-delivery-doc-writer

触发场景：

- 生成产品文档。
- 生成技术文档。
- 生成 AI 协作开发记录。
- 准备答辩材料。

Skill 内容：

```markdown
---
name: agenthub-delivery-doc-writer
description: Use when writing AgentHub delivery documents aligned with evaluation criteria.
---

# AgentHub Delivery Doc Writer

## Evaluation Mapping

Every document should map to:

1. AI collaboration capability.
2. Feature completeness.
3. Generation quality.
4. Code understanding.
5. Innovation and product sense.

## Required Docs

- product-spec.md: product positioning, users, flows, feature matrix.
- tech-design.md: architecture, API, data models, adapter, harness, workspace.
- prompt-log.md: prompts, rules, skills, review, iteration timeline.

## Writing Rules

- Explain why, not only what.
- Mention actual code modules.
- Mention known boundaries honestly.
- Tie features to demo path.
- Include verification commands.
```

在 AgentHub 中的价值：

- 让交付文档更贴合评审标准。
- 避免文档变成功能流水账。

## 7. Skill 使用矩阵

| 开发问题 | 使用 Skill | 产生价值 |
| --- | --- | --- |
| 不知道项目结构 | Understand Anything | 生成知识图谱，识别 FastAPI/React/Agent/Workspace 层 |
| 解释核心调用链 | Understand Chat | 用知识图谱回答“消息如何流转” |
| 审查改动影响 | Understand Diff | 找 changed/affected components |
| 准备答辩代码讲解 | Understand Explain | 深入解释 AgentService、RealAgent、WorkspaceService |
| 检查 UI 真实行为 | Browser UI QA Skill | 验证流式输出、Preview、弹窗 |
| 查询 API 正确用法 | OpenAI Docs Skill | 校验 streaming 和 response_format |
| 修 Orchestrator | agenthub-orchestrator-harness-guard | 保持 LLM 决策和 harness 稳定 |
| 修前端流式 | agenthub-sse-streaming-debugger | 保证会话隔离和 draft 替换 |
| 修 Preview | agenthub-workspace-preview-guardian | 保证 Apply/Revert/Preview 一致 |
| 做自建 Agent | agenthub-custom-agent-builder | 保证 system prompt、后端选择、@ 路由 |
| 修 schema 错误 | agenthub-real-agent-schema-repair | repair/salvage/错误分类 |
| 写交付文档 | agenthub-delivery-doc-writer | 对齐评审标准 |

## 8. 真实开发问题与 Prompt 复盘

### 8.1 Mock Agent 误连

问题：

```txt
重启后发现每次输入都得到同样回复，怀疑一直连着 mock agent。
```

Prompt：

```txt
请检查后端是否真正调用大模型。
检查 USE_MOCK_AGENTS、AgentRegistry、adapter_type、runtime info 和前端 VITE_API_BASE_URL。
前端如果发现核心 Agent 是 mock，需要显示明显警告。
```

结果：

- 增加 runtime 信息。
- 前端显示 mock 警告。
- 减少演示时误用模拟数据。

### 8.2 结构化输出不可用

问题：

```txt
系统经常显示模型连续返回了不符合结构要求的内容。
```

Prompt：

```txt
请检查 RealAgent 解析和 repair 逻辑。
不要把 schema 错误提示成 .env 配置错误。
尝试从 Markdown/HTML 中恢复 artifact。
```

结果：

- 增强 RealAgent parse/repair/salvage。
- 用户可见错误更准确。

### 8.3 Orchestrator 任务拆解像写死

问题：

```txt
@Orchestrator 时只输出模板化“安全兜底计划”，不像调用真实大模型。
```

Prompt：

```txt
检查 Orchestrator 决策化逻辑。
正常优先调用 LLM，只有 schema 失败才 fallback。
fallback 文案不能暴露内部错误，但也不要让主链路中断。
```

结果：

- OrchestratorAdapter 调 LLM。
- 增加 relaxed recovery。
- 开发任务继续进入 harness。

### 8.4 Preview 打开错误页面

问题：

```txt
生成 todo.html 后，打开预览仍跳 index.html 或旧页面。
```

Prompt：

```txt
apply_diff 应根据本次 diff 的 HTML 目标文件设置 preview entry。
preview-page 支持 ?path=todo.html。
前端打开预览使用后端返回的 preview_url。
```

结果：

- ApplyDiffResponse 增加 preview_url、entry_path。
- preview-page 支持 path。
- Workspace preview 与代码 artifact 更一致。

### 8.5 会话状态污染

问题：

```txt
一个会话正在回复，其他会话也显示正在回复。
```

Prompt：

```txt
把聊天运行状态从全局改为按 conversationId 隔离。
流式事件回调必须携带发送时的 conversationId。
```

结果：

- 前端消息缓存和生成状态按 conversationId 隔离。
- 切换会话不再污染。

### 8.6 自建 Agent 内部 id 泄漏

问题：

```txt
自建 Agent 回复和生成中状态出现 custom-agent_xxx。
```

Prompt：

```txt
请检查字段来源，并用最小改动修复。
展示名称使用 Agent.name，测试 Agent 输出用 Markdown 渲染。
```

结果：

- 用户看到的是自建 Agent 名称。
- 内部 id 只作为系统标识，不进入用户可见文案。

## 9. AI 协作经验总结

### 9.1 Prompt 层经验

1. 写清楚“不要改什么”比“要做什么”同样重要。
2. 截图问题要先描述用户现象，再让 AI 查代码。
3. 对大功能先要计划，再实现。
4. 对反复出现的问题，要要求 AI 解释根因。
5. 对 LLM 输出要默认不稳定，Prompt 中必须提 repair 和 fallback 边界。

### 9.2 Skill 层经验

1. 市面 Skill 适合解决通用问题：理解代码库、分析 diff、验证 UI、查文档。
2. 自建 Skill 适合固化项目特有经验：Orchestrator、SSE、Workspace、Custom Agent。
3. Skill 应该简洁、流程化，不能写成大段泛泛说明。
4. 每个 Skill 都要有触发场景、工作流、验收标准和常见坑。
5. Skill 输出不能替代源码验证，最终仍要看代码和测试。

### 9.3 工程层经验

1. IM 产品所有运行态必须按会话隔离。
2. Agent 产物必须结构化，不要只放自然语言。
3. 用户确认 Apply Diff 后才能写真实 workspace。
4. Preview URL 必须绑定具体 entry_path。
5. CLI Agent 必须在临时 workspace 副本运行。
6. 自建 Agent 的展示名称和内部 id 必须分离。
7. Mock 模式必须在 UI 中明显提示。

## 10. 可复用 Review 模板

````md
## AI 输出 Review

### 任务

- 功能：
- 影响模块：
- 是否改 API：
- 是否改数据模型：

### 检查点

- [ ] 是否遵守 AGENTS.md
- [ ] 是否保持 Demo 主线
- [ ] 是否只修改允许范围
- [ ] 是否有路径安全
- [ ] 是否没有泄露密钥
- [ ] 是否补测试
- [ ] 是否更新文档

### 发现问题

1. [P0/P1/P2] 文件：行号：问题描述。

### 验证命令

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check agenthub tests scripts
.venv/bin/python -m mypy agenthub
cd frontend && npm run build
```

### 结论

- 可合并 / 需修复 / 暂缓
````

## 11. 后续可真正落地的 Skill 目录建议

如果后续要把上面的自建 Skill 真正落成文件，可以创建：

```txt
skills/
  agenthub-architecture-navigator/
    SKILL.md
  agenthub-orchestrator-harness-guard/
    SKILL.md
  agenthub-sse-streaming-debugger/
    SKILL.md
  agenthub-workspace-preview-guardian/
    SKILL.md
  agenthub-custom-agent-builder/
    SKILL.md
  agenthub-real-agent-schema-repair/
    SKILL.md
  agenthub-delivery-doc-writer/
    SKILL.md
```

每个 `SKILL.md` 使用统一结构：

```markdown
---
name: skill-name
description: When to use this skill.
---

# Skill Name

## Goal

## Trigger

## Workflow

## Acceptance

## Common Mistakes
```

这样可以把本项目的 AI 协作经验从 Prompt Log 进一步沉淀成可调用能力。
