# AgentHub AI 协作开发记录

最后更新：2026-06-10  
记录范围：2026-05-22 至 2026-06-10  
用途：展示 AgentHub 从 0 到 1 的 AI 协作过程、Prompt 策略、规则沉淀、问题修复和验证方式。

## 1. 协作目标

AgentHub 的开发不是简单让 AI 写若干文件，而是把 AI Coding 纳入一个可控流程：

```txt
需求文档
-> AI 协作规则
-> 分阶段开发计划
-> Codex/AI 实现
-> 人类反馈问题
-> 定向修复
-> 测试验证
-> Prompt Log 记录
-> 文档交付
```

在评审维度中，“AI 协作能力”权重最高，因此项目专门沉淀了 Spec、Rules、Prompt Log、Review Checklist 和架构决策记录，让 AI 协作本身成为可展示产物。

## 2. AI 协作资产

| 资产 | 文件 | 作用 |
| --- | --- | --- |
| 仓库级规则 | `AGENTS.md` | 规定项目目标、技术栈、目录、Adapter、Artifact、Orchestrator、安全和验证要求 |
| AI 协作规则 | `docs/ai-rules.md` | 精简版协作原则：Demo 主线优先、结构化产物、安全审查 |
| 任务模板 | `CODEX_TASK_TEMPLATE.md` | 把需求转成可交给 Codex 的开发任务 |
| 审查清单 | `CODEX_REVIEW_CHECKLIST.md` | 每次 AI 改代码后的基础、运行、功能、安全、文档检查 |
| 决策记录 | `DECISION_LOG.md` | 记录 Python-first 等关键技术决策 |
| Prompt 记录 | `docs/prompt-log.md` | 记录阶段 Prompt、问题、实现结果和复盘 |
| 架构说明 | `docs/project-architecture.md` | 帮助 AI 和人快速理解代码结构 |
| 测试集 | `tests/` | 将 AI 产物行为固化成可回归验证 |

这些资产共同解决三个问题：

- AI 生成代码容易跑偏：用 `AGENTS.md` 限定主线和边界。
- AI 输出质量不稳定：用 Review Checklist 和 tests 做二次校验。
- 答辩时难解释过程：用 Prompt Log 和 Decision Log 还原迭代路径。

## 3. 从 0 到 1 时间线

### 2026-05-22 至 2026-05-31：需求与规范期

主要产出：

- 明确课题：IM 聊天式多 Agent 协作平台。
- 明确评审权重：AI 协作能力、功能完整度、生成效果质量、代码理解度、产品感。
- 确定核心演示链路：用户需求 -> Orchestrator -> 多 Agent -> 代码/Diff -> Apply -> Preview -> 历史保留。
- 形成 Python-first 思路：后端、Agent、Orchestrator、Workspace、Diff 以 Python 为主，前端可用 React 保证 IM 体验。
- 初步沉淀 `AGENTS.md`、任务模板、审查清单和决策记录。

关键 Prompt 思路：

```txt
请基于课题要求，规划一个 Python-first 的 IM 多 Agent 协作平台，
要求优先保证 Demo 主线，不要被企业级权限、多端协同、部署平台等大功能带偏。
```

阶段价值：

- 在写代码前先定义协作规则，避免 AI 后续随意重构或引入偏离主线的大功能。
- 把“至少接入两个 Agent 平台”和“统一适配器层”提前写进架构目标。

### 2026-06-01：项目初始化

提交记录显示 `chore: initialize AgentHub project` 和前端框架初始化。

主要工作：

- 初始化 Python package、pyproject、基础文档。
- 创建 React/Vite 前端框架。
- 确立 FastAPI + Pydantic + SQLite/memory repository 的后端方向。

协作重点：

- 先搭骨架，不急于堆功能。
- 保持目录与 `AGENTS.md` 的推荐结构基本一致。

### 2026-06-02：前端会话与 Mock 演示链路

提交记录包括：

- 搭建前端基础框架。
- 完成会话与消息主流程。
- 接入 `@Agent` 调度与 mock Agent 回复。
- 完善 Artifact 卡片。
- 接入 Apply Diff 与预览刷新闭环。
- 引入 Ant Design 并优化前端演示体验。

关键 Prompt 思路：

```txt
先做一个能演示的 IM 主界面：左侧会话、中心聊天、右侧 artifact/workspace，
用 mock 数据跑通 @Agent、代码卡片、Diff 卡片和 Preview 卡片。
```

问题与修复：

- 早期前端更多依赖 mock 数据，后续用户反馈“重启后一直用 mock agent”，推动新增 runtime guard。
- 子组件撑开父组件、群聊 Agent 封闭等 UI/交互问题在同日修复。

阶段价值：

- UI 首先形成可感知产品形态，方便后续联调后端。
- Mock 链路帮助快速验证会话、消息、artifact 设计。

### 2026-06-03：后端 MVP、Workspace 与 Diff

提交记录包括：

- 支持 Diff 应用到 workspace 文件。
- 后端接口分离。
- Member B 后端 MVP。
- Markdown-first Agent 回复与 Workspace 右栏改造。

关键 Prompt 思路：

```txt
把 mock 前端接到真实 FastAPI 后端：会话、消息、Agent、workspace、diff、preview 都要有 API，
业务逻辑放在 service/repository，不要写进 route。
```

主要结果：

- 建立 FastAPI routes：conversations、messages、agents、workspaces。
- 建立 schemas/models/repositories/services 分层。
- 增加 WorkspaceService，支持真实文件写入。
- 增加 diff apply 逻辑，前端 Apply Diff 后能看到 workspace 文件变化。

阶段价值：

- AgentHub 从“UI Demo”进入“真实文件闭环”。
- Apply Diff 成为区分普通聊天机器人和开发协作平台的核心能力。

### 2026-06-04 至 2026-06-05：多人联调与 Orchestrator/Workspace

提交记录显示多次联调和 `orchestrator/workspace` 开发。

主要工作：

- 对齐前后端 API。
- 强化 Orchestrator 调度、workspace 文件列表、preview 状态。
- 修复接口类型和联调问题。

协作策略：

- 以可运行 Demo 为优先级最高目标。
- 对接口不一致优先补 schema 和类型，而不是让前端临时猜字段。

阶段价值：

- 三人协作中的接口摩擦逐步收敛。
- 项目从单模块实现走向端到端联调。

### 2026-06-07：Workspace 功能完善与架构文档

提交记录包括 workspace 功能完善、项目结构文档上传。

主要结果：

- 右侧 workspace 面板逐步成型。
- 文件列表、预览、变更历史和应用状态更完整。
- 形成 `docs/project-architecture.md`，帮助团队和 AI 快速理解项目。

关键 Prompt 思路：

```txt
请纵览项目结构，解释前端、后端、Agent、Orchestrator、Workspace 的职责，
让新加入的开发者能从一条消息流理解整个系统。
```

阶段价值：

- 文档开始从“计划”转向“解释真实代码”。
- 为后续复杂修复提供上下文基础。

### 2026-06-08 至 2026-06-09：Orchestrator、Preview 与真实 LLM 稳定性

用户连续反馈：

- 前端一次性吐出结果，不是流式。
- 无 `@Agent` 时没有响应。
- Orchestrator 任务拆解复制用户原话。
- Preview Agent 职责不清。
- 一直用 Mock Agent。
- 模型结构化输出不可用。
- Orchestrator 像规则式兜底，不像真实 LLM。
- Preview 打开 URL 错误。

关键 Prompt 片段：

```txt
Orchestrator 的任务拆解不是规则式，应该调用大模型。
前端展示输出一定要流式输出。
Schema 失败不要把错误伪装成 .env 配置问题。
Preview URL 应该跳转到具体代码对应的网址。
```

主要修复：

- 新增 `/messages/stream` SSE 主链路。
- 前端用 draft message 展示 `agent_delta`。
- 无 `@` 默认进入 Orchestrator 智能入口。
- Orchestrator 优先调用 LLM 生成 `OrchestratorDecision`。
- RealAgent 增加 repair、结构归一化和非结构化 salvage。
- 错误分类：配置/网络/schema 分开提示。
- Apply Diff 返回 `preview_url` 和 `entry_path`。
- `preview-page?path=` 支持指定入口和嵌套资源。
- 前端增加 Mock 后端明显提示。

阶段复盘：

- LLM 结构化输出不能被当成稳定 API，必须有 repair、归一化、salvage 和产品层错误边界。
- 流式体验不仅是后端 SSE，还要前端按会话隔离状态并做视觉分块。
- Preview 必须绑定真实 workspace entry，否则演示时会出现“代码生成了但预览不是这份代码”的断裂。

### 2026-06-09：Phase 1 IM 核心补齐

用户要求：

```txt
实现 Phase 1：会话归档、消息引用、消息复制、软删除、重新生成、长期上下文 pin。
尽量不影响现有流式消息、Agent 执行、workspace preview、Apply/Revert Diff。
```

主要结果：

- Conversation 增加 `status=active|archived`。
- Message 增加 `reply_to_id`、`regenerated_from_id`、`is_context_pinned`、`deleted_at`。
- 新增软删除 API、pin/unpin API、regenerate stream API。
- 前端每条消息增加回复、复制、重新生成、pin、删除操作。
- Agent history 过滤删除消息，pinned messages 注入 context。
- Regenerate 不重复创建用户消息，只追加新的 Agent 回复。

阶段价值：

- AgentHub 不再只是“生成代码 Demo”，开始具备真实 IM 产品基础。
- 长期上下文 pin 为多轮 Agent 协作提供产品化入口。

### 2026-06-09：会话状态污染与 Todo 固定模板问题

用户反馈：

- 会话 A 正在回复时，切到会话 B 也显示 Agent 正在回复中。
- 不同 Todo 需求生成同一个固定页面。

关键 Prompt 思路：

```txt
把聊天运行状态从全局状态改为按 conversationId 隔离；
移除 Todo 固定模板替换逻辑，改为模型输出优先 + 交互性校验 + repair。
```

主要修复：

- 前端引入 `messagesByConversationId`。
- `agentRunning`、`generationNotice`、draft、reply target 按会话隔离。
- 流式事件携带发送时 conversationId 快照。
- Code Agent 不再静默用固定 Todo 模板覆盖模型输出。
- Todo 交互不足时优先 repair，不把不同需求压成同一页面。

阶段复盘：

- IM 产品最怕状态污染，所有运行态都必须按会话隔离。
- 兜底模板会提升短期成功率，但会严重损害生成差异和用户信任。

### 2026-06-10：Phase 3 自建 Agent

用户要求：

```txt
前端自建 Agent 时可以输入 Agent 的系统提示词；
启用后的自建 Agent 可加入会话，出现在 @ 菜单中，并按 system prompt 回复。
```

主要结果：

- 新增 `CustomAgent` schema/model/repository。
- SQLite 新增 `customagentrecord` 表和兼容迁移。
- 新增自建 Agent API：list/create/update/delete/test。
- 新增 `CustomAgentAdapter`，复用全局 OpenAI-compatible 或 CLI 后端。
- 前端新增 `CustomAgentManagerModal`。
- 会话成员管理和 `@` 菜单支持自建 Agent。

后续修复：

- 自建 Agent 回复中不再暴露 `custom-agent_xxx` id。
- 生成中状态不显示内部 id。
- 测试 Agent 输出改为 Markdown 渲染。

阶段价值：

- AgentHub 从“固定内置 Agent”扩展到“用户可配置角色 Agent”。
- system prompt 成为产品能力，而不是只写在代码里的开发配置。

### 2026-06-10：Codex / Claude Code 多后端接入

用户要求：

```txt
只接入 Codex 和 Claude Code。
希望能真实调用 Codex CLI 跑通一个小任务。
Codex 和 Claude Code 要像 Orchestrator、Code Agent 一样出现在常用 Agent 里，
但不影响 Orchestrator 逻辑。
```

主要结果：

- 新增后端枚举：`openai-compatible`、`codex-cli`、`claude-code-cli`。
- 新增 `ExternalCliAgentAdapter`。
- 内置 Agent 列表增加 `codex-agent` 和 `claude-code-agent`。
- Codex/Claude Code 是独立 Agent，不进入 Orchestrator 默认开发 harness。
- 自建 Agent 可选择 Codex 或 Claude Code 后端。
- 前端将 `Codex CLI` 展示简化为 `Codex`。
- 新建会话和成员管理增加全选/取消全选。

真实调用逻辑：

```txt
用户 @Codex 或 @自建CodexAgent
-> AgentService 路由到对应 adapter
-> ExternalCliAgentAdapter 创建临时 workspace 副本
-> 调用 codex exec / claude --print
-> 对比运行前后文本文件快照
-> 生成 code/diff artifact
-> 返回 AgentRunResult
-> 前端流式展示并允许用户 Apply Diff
```

阶段复盘：

- CLI Agent 必须在临时副本运行，避免绕过 Apply Diff 直接改真实 workspace。
- Codex/Claude Code 作为独立 Agent 更安全，不应混入 Orchestrator 的内置开发计划。

## 4. 关键问题复盘

### 4.1 Mock Agent 误连

现象：用户重启后发现输入任何内容都是固定回复。  
原因：前端可能连接了测试端口或后端处于 mock 模式。  
修复：新增 runtime info，前端显示 Mock Agent 警告；`GET /api/agents` 暴露 adapter_type。

### 4.2 结构化输出不可用

现象：模型返回 JSON/Markdown 混合内容，Pydantic 校验失败，用户看到内部 schema 错误。  
原因：LLM 输出不是强类型 API，即使设置 response_format 也可能出现字段缺失、嵌套 JSON、Markdown fence 等。  
修复：RealAgent 增加 repair、unwrap、normalize、salvage；错误提示按 schema/config/network 分类。

### 4.3 Orchestrator 像写死规则

现象：用户希望任务拆解由大模型完成，但系统经常展示安全兜底文案。  
原因：Orchestrator 决策失败时直接回到规则计划，且文案显得模板化。  
修复：优先 LLM `OrchestratorDecision`，失败后先 relaxed text recovery，再安全兜底；兜底不暴露内部错误。

### 4.4 Todo 固定模板

现象：不同需求都生成相似 Todo 页面。  
原因：早期为了保证交互成功，用固定模板替换静态 Todo。  
修复：模型输出优先，缺交互时 repair，避免把不同需求压成同一产物。

### 4.5 Preview URL 不一致

现象：代码生成后打开预览跳到旧页面或错误页面。  
原因：preview 默认固定 `index.html`，Apply Diff 没有返回本次入口。  
修复：Apply Diff 返回 `preview_url` 和 `entry_path`；preview-page 支持 `?path=`。

### 4.6 会话状态污染

现象：在一个会话发任务，切到其他会话也显示正在回复。  
原因：运行态是全局状态。  
修复：messages、running、notice、draft、reply target 全部按 conversationId 管理。

### 4.7 自建 Agent 内部 id 泄漏

现象：回复或生成中状态显示 `custom-agent_xxx`。  
原因：部分文案直接使用 sender_id/agent_id。  
修复：前端通过 Agent 列表映射显示名称；测试输出只展示 content 并用 Markdown 渲染。

### 4.8 CLI Agent 复杂文件不可打开

现象：Codex 生成 `generated.pdf`，聊天里有链接但点不开。  
原因：ExternalCliAgentAdapter 当前只快照 UTF-8 文本文件，PDF 等二进制被跳过；前端 file artifact 也没有打开/下载语义。  
当前状态：已定位，列入后续 Phase；需要新增 artifact 文件存储和 file card 打开/下载能力。

## 5. Prompt 方法论

### 5.1 先计划，再实现

对复杂任务先要求 AI 输出 Summary、Key Changes、Test Plan、Assumptions，再执行。这能减少实现时跑偏。

### 5.2 强制保留主链路

每次功能扩展都强调“不影响现有 Orchestrator、Code、Review、Preview、Workspace、Apply/Revert 主链路”。

### 5.3 最小改动修复

对 UI 文案、id 泄漏、按钮能力等问题，要求“最小代码改动代价”，避免 AI 大范围重构。

### 5.4 反复打磨真实体验

用户多次用真实截图反馈：不是流式、按钮不能点、预览打不开、schema 错误暴露、会话污染。每次都以实际产品现象倒逼代码修复。

### 5.5 禁止伪成功

对 Todo 固定模板、fallback、mock 数据等问题，明确要求“不要用模拟数据或最小兜底冒充真实生成”。这直接提升生成效果质量和系统可信度。

## 6. 验证方式

常规验证命令：

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check agenthub tests scripts
.venv/bin/python -m ruff format --check agenthub tests scripts
.venv/bin/python -m mypy agenthub
cd frontend && npm run build
```

真实任务 smoke：

```bash
.venv/bin/python scripts/verify_real_agent_tasks.py
```

重点手工验证：

- 发送长任务时用户消息立即出现，Agent 一段段输出。
- 会话 A 生成中切到会话 B，B 不显示 A 的生成状态。
- Apply Diff 后 Preview 打开本次入口。
- Revert 后 workspace 文件恢复。
- 自建 Agent 测试和聊天回复都按 Markdown 渲染。
- Codex 独立 Agent 能通过本地 CLI 运行小任务。

## 7. 当前交付状态

| 交付项 | 状态 |
| --- | --- |
| 产品设计文档 | 已整理为 `docs/product-spec.md` |
| 技术文档 | 已整理为 `docs/tech-design.md` |
| AI 协作开发记录 | 已整理为 `docs/prompt-log.md` |
| 可运行 Demo | React + FastAPI 本地运行 |
| AI 协作规则 | `AGENTS.md`、`docs/ai-rules.md`、Review Checklist |
| 多 Agent 调度 | Orchestrator + Code + Review + Preview |
| 多后端接入 | OpenAI-compatible + Codex CLI + Claude Code CLI |
| 自建 Agent | 支持 system prompt 和后端选择 |
| 已知待补 | CLI 二进制复杂产物可打开展示 |


