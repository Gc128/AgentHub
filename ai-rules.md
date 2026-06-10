# AgentHub AI 协作规则

最后更新：2026-06-10  
适用对象：Codex、Claude Code、OpenCode、TRAE、团队成员  
目标：让 AI Coding 服务 AgentHub Demo 主线，同时保证代码安全、架构清晰、可验证、可复盘。

## 1. 总原则

### 1.1 Demo 主线优先

所有 AI 生成的功能都必须优先服务这条主线：

```txt
用户提出开发需求
-> Orchestrator 拆解
-> 多 Agent 产出
-> 展示 code/diff/preview artifact
-> 用户 Apply Diff
-> Workspace Preview 更新
-> 聊天历史保留
```

如果某项功能不能增强这条主线，或者会破坏主线稳定性，应暂缓。

### 1.2 AI 是协作助手，不是最终负责人

- AI 可以写代码、读代码、生成计划、做审查、写文档。
- 人类必须负责最终选择、Review、验证和合并。
- 不允许把 AI 生成代码未经阅读直接合并。
- 不允许让 AI “随便改到能跑为止”。

### 1.3 小步快跑，禁止大范围无关重构

每次 AI 任务应有明确边界：

- 只改必要模块。
- 不改无关目录。
- 不引入无关依赖。
- 不为了“代码更优雅”重写稳定模块。
- 不删除他人代码来规避冲突。

### 1.4 产品体验与工程安全同等重要

AgentHub 是一个可演示产品，不只是 API 项目。AI 输出必须同时考虑：

- 用户是否看得懂当前状态。
- 流式输出是否舒适。
- 会话状态是否隔离。
- Preview 是否指向真实代码。
- 错误提示是否准确。
- 文件操作是否安全。

## 2. 每次使用 AI 前的输入清单

向 AI 提交任务前，必须尽量提供：

1. 背景：为什么要做。
2. 当前问题：用户看到什么现象，或测试报什么错。
3. 目标：期望最终行为。
4. 范围：允许改哪些文件。
5. 禁区：不能改哪些功能或接口。
6. 验收：如何判断完成。
7. 测试：需要跑哪些命令。
8. 风险：是否涉及 API、数据模型、workspace、密钥。

推荐模板：

```txt
请完成以下任务：

背景：
- 当前 AgentHub 的 xxx 功能存在 xxx 问题。

目标：
- 实现 xxx。
- 保持 xxx 不受影响。

允许修改：
- agenthub/...
- frontend/src/...
- tests/...

禁止修改：
- 不改变 SSE 事件名。
- 不重写 Orchestrator 主链路。
- 不改 .env，不提交密钥。

验收标准：
- 用户操作 xxx 时应看到 xxx。
- API 返回 xxx。
- 测试 xxx 通过。

验证命令：
- .venv/bin/python -m pytest -q
- cd frontend && npm run build
```

## 3. Prompt 编写规范

### 3.1 好 Prompt 的特征

- 目标具体。
- 约束明确。
- 可验证。
- 包含当前代码事实或截图现象。
- 明确不允许破坏的主链路。
- 要求 AI 查明原因，而不是只堆补丁。

### 3.2 坏 Prompt 示例

```txt
帮我优化项目。
```

问题：

- 没有目标。
- 没有范围。
- 没有验收标准。
- 容易导致大范围重构。

### 3.3 好 Prompt 示例

```txt
当前 @ 自建 Agent 回复时，消息正文前出现 custom-agent_xxx。
请检查这个字段来自后端 content 拼接还是前端 sender_id 展示。
要求用最小代码改动修复聊天消息、生成中状态、测试 Agent 输出三个位置。
不要改 Agent 路由、数据库模型和 Orchestrator 逻辑。
```

## 4. 计划与实现流程

### 4.1 复杂任务必须先出计划

涉及以下任一内容时，先让 AI 输出计划：

- 新 API。
- 新数据模型。
- Orchestrator 调度变化。
- Workspace 文件写入。
- 多 Agent 后端接入。
- 大型前端状态变化。
- 安全相关逻辑。

计划必须包含：

- Summary。
- Key Changes。
- Test Plan。
- Assumptions。

### 4.2 实现计划时不得擅自扩展

AI 实现时只能做计划中明确的事情。如果发现计划不足，应先说明缺口，再补充小范围方案。

### 4.3 修复 bug 先定位根因

修复步骤：

1. 复述用户现象。
2. 搜索相关代码。
3. 找出真正根因。
4. 给出最小修复。
5. 增加测试或手动验证方式。
6. 更新文档或 Prompt Log。

## 5. 代码修改规则

### 5.1 后端规则

- API 入参与出参必须使用 Pydantic schema。
- 业务逻辑必须放 service，不堆在 FastAPI route。
- Repository 层负责 SQLite/memory 差异。
- Agent 调用必须通过 Adapter。
- 外部 HTTP 调用必须有 timeout。
- 错误信息可读，但不能泄露密钥。
- workspace 路径必须安全解析。
- 不使用 `shell=True` 拼接用户输入。
- CLI 调用必须使用参数列表。
- `.env` 不提交。

### 5.2 前端规则

- 会话相关状态必须按 `conversationId` 隔离。
- SSE 事件处理必须能在用户切换会话后继续写入正确缓存。
- 发送消息后用户消息应立即出现。
- 长回复必须流式/分段展示。
- 输入框禁用只影响当前会话。
- Markdown 必须经过 sanitize。
- artifact 操作按钮必须有禁用态、loading 态和错误处理。
- 不在前端保存或请求供应商 API Key。

### 5.3 Agent 规则

- 所有 Agent 输出统一为 `AgentRunResult`。
- 代码产物必须优先生成 `code` artifact。
- 文件变更必须生成 `diff` artifact。
- Preview 产物必须生成 `preview` artifact。
- Review 产物至少包含 findings/risk 类信息。
- 自建 Agent 必须使用用户填写的 system prompt。
- 自建 Agent 内部 id 不应展示给最终用户。
- Codex/Claude Code CLI 必须在临时 workspace 副本中运行。

### 5.4 Orchestrator 规则

- 用户显式 `@Agent` 时优先调用该 Agent。
- 无 `@` 时默认进入 Orchestrator 智能入口。
- 普通聊天不进入开发 harness。
- 开发任务优先由 LLM 决策。
- LLM 决策失败时可安全兜底，但不要向用户暴露 schema 内部错误。
- 默认开发计划只调度内置 `code-agent`、`review-agent`、`preview-agent`。
- 自建 Agent 不自动进入 Orchestrator harness，除非后续显式设计。

## 6. Artifact 规则

Artifact 是 AgentHub 的核心产品抽象。

### 6.1 类型

```txt
code
diff
preview
file
deploy
```

### 6.2 输出要求

- 不要只把代码放在自然语言里。
- 不要生成不可点击的假文件 artifact。
- `diff` 必须包含可应用的 unified diff。
- `preview` 必须说明 status、workspace_id、preview_url 或 pending 原因。
- `file` 用于计划、审查、附件、文档类产物。
- 二进制复杂产物后续应通过 file artifact 打开/下载，不应塞进 code/diff。

### 6.3 Apply Diff 规则

- Agent 生成 diff 不代表自动写入 workspace。
- 必须由用户点击 Apply Diff。
- Apply 后记录 AppliedDiffRecord。
- Revert 必须基于 before/after 快照。
- 如果当前文件不等于 after，必须提示冲突，不可强行覆盖。

## 7. LLM 结构化输出规则

### 7.1 不信任第一次输出

即使请求 `response_format=json_object`，模型也可能返回：

- Markdown fence 包裹 JSON。
- content 字段里嵌套 JSON。
- 顶层 list。
- artifacts 字段为 dict。
- 缺少 agent_id。
- code 只在 Markdown 中。
- HTML 文档直接裸输出。

### 7.2 必须做 repair 和 salvage

推荐顺序：

1. 正常 JSON parse。
2. Pydantic validate。
3. repair 调用。
4. unwrap/normalize 常见形状。
5. 从 Markdown code fence 恢复 code artifact。
6. 从 HTML 文档恢复 code/diff artifact。
7. 最终返回可读错误。

### 7.3 错误分类

- 配置错误：提示检查 `.env`、API Key、base URL、model。
- 网络错误：提示检查网络、供应商状态、timeout。
- Schema 错误：提示模型连续返回不符合结构，不要误导用户检查 `.env`。

## 8. Workspace 安全规则

- 所有 path 必须规范化。
- 禁止 `../` 越权。
- 禁止写入 workspace 根目录外。
- 删除文件必须确认路径是文件而不是目录。
- Preview assets 只能读取当前 workspace。
- CLI Agent 修改临时副本，不直接修改真实 workspace。
- Apply Diff 是真实 workspace 写入的唯一主路径。
- 不允许 AI 用绝对路径写用户电脑上的任意文件。

## 9. 测试规则

### 9.1 后端

优先补 pytest：

- API 返回值。
- service 业务逻辑。
- repository 持久化。
- Agent adapter 输出。
- workspace path safety。
- diff apply/revert。
- preview URL。
- schema repair。

### 9.2 前端

至少执行：

```bash
cd frontend && npm run build
```

重要交互需要手动验收：

- 流式输出。
- 自动滚动到底部。
- 切换会话不污染状态。
- Apply Diff 按钮状态。
- Preview 打开 URL。
- 自建 Agent 测试输出 Markdown 渲染。

### 9.3 常规命令

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check agenthub tests scripts
.venv/bin/python -m ruff format --check agenthub tests scripts
.venv/bin/python -m mypy agenthub
cd frontend && npm run build
```

如果无法运行，必须说明原因。

## 10. Skill 使用规则

### 10.1 什么时候使用 Skill

以下场景应优先使用 Skill：

- 需要理解整个代码库：使用 `understand`。
- 需要基于知识图谱问架构：使用 `understand-chat`。
- 需要分析 diff 影响范围：使用 `understand-diff`。
- 需要深入解释某个文件：使用 `understand-explain`。
- 需要可视化架构：使用 `understand-dashboard`。

### 10.2 使用 Skill 的记录要求

使用 Skill 后，Prompt Log 中应记录：

- Skill 名称。
- Skill 来源路径。
- 使用目的。
- 输入 Prompt。
- 输出如何影响实现或文档。
- 是否生成文件，例如 `.understand-anything/knowledge-graph.json`。

### 10.3 Skill 安全边界

- 不要把密钥、私密日志、用户隐私丢给 Skill。
- 生成知识图谱前应确认 ignore 配置，避免扫描无关大文件。
- 不要把 Skill 输出当成绝对真相，仍要回到源码核对。
- 不要让 Skill 自动修改业务代码，除非任务明确要求。

## 11. Git 与分支规则

- 不在未确认情况下 push。
- 不直接修改 main 分支配置。
- 不使用 `git reset --hard` 或强制 checkout 覆盖他人修改。
- 提交信息使用：

```txt
feat: 新功能
fix: 修复问题
docs: 文档修改
style: 样式调整
refactor: 重构
test: 测试
chore: 工程配置
```

AI 改代码后，提交前必须看：

```bash
git diff --stat
git diff --name-only
```

## 12. Prompt Log 记录规则

以下情况必须写入 `PROMPT_LOG.md`：

- 生成核心模块。
- 修改 Agent Adapter。
- 修改 Orchestrator。
- 修改 workspace/diff/preview。
- 修复关键用户截图问题。
- 接入新后端。
- 引入或使用 Skill。
- 大范围文档整理。
- 影响 Demo 主线的决策。

记录格式：

```md
## 日期：功能名

### 背景

### Prompt

### AI 输出

### 人工 Review

### 修复

### 验证

### 复盘
```

## 13. 禁止事项

禁止向 AI 提以下任务：

- “帮我整体重构一下。”
- “忽略测试，先合并。”
- “把 API Key 写进代码。”
- “删除冲突文件重新生成。”
- “随便改到能跑。”
- “不管现有逻辑，重新做一个。”
- “把 workspace 路径校验去掉。”
- “前端直接请求 OpenAI API。”

## 14. 交付前检查清单

### 14.1 功能

- 会话创建、切换、归档正常。
- 消息发送、流式输出、重新生成正常。
- `@Agent`、无 `@`、自建 Agent 路由正常。
- Code/Review/Preview 主链路正常。
- Apply Diff、Preview、Revert 正常。

### 14.2 体验

- 长回复不是一次性刷出。
- 切换会话不会状态污染。
- 错误提示可读。
- 内部 id 不暴露给用户。
- Markdown 正常渲染。

### 14.3 安全

- `.env` 未提交。
- API Key 未泄露。
- workspace 路径无越权。
- CLI 无 shell 拼接。
- Preview assets 限制在 workspace 内。

### 14.4 文档

- `product-spec.md` 更新。
- `tech-design.md` 更新。
- `PROMPT_LOG.md` 或 `docs/prompt-log.md` 更新。
- `ai-rules.md` 更新。
- Demo 脚本与实际功能一致。

## 15. 最佳实践总结

1. 先写规则，再让 AI 写代码。
2. 先问清现象，再定位根因。
3. 先保 Demo 主线，再加扩展能力。
4. 先结构化产物，再展示自然语言。
5. 先用户确认 Apply，再写真实 workspace。
6. 先按会话隔离状态，再处理流式体验。
7. 先 repair/salvage，再向用户报告失败。
8. 先测试验证，再整理文档。
