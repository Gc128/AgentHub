# AgentHub 简历表述

## 项目描述（可直接使用）

**AgentHub｜可审计多 Agent 开发协作平台**  
基于 React、FastAPI、Pydantic、LangChain 和 SQLite 构建 IM 式多 Agent 开发平台，将 LLM 代码生成改造为“候选 Change Set → 静态安全检查 → Review 门禁 → 人工预览与合入”的可审计闭环。

- 设计 Orchestrator/Code/Review 角色专属结构化契约与统一失败语义；网络错误限次重试、Schema 限次修复，禁止模型失败后伪造成功产物。
- 实现多文件 Change Set 状态机和隔离 Staging Workspace，由后端生成 unified diff 与 SHA-256 快照；Promote 前做乐观并发检测，并通过 `os.replace`、失败回滚和整组 Revert 保证合入安全。
- 构建高置信静态安全检查，阻止路径越界、符号链接、候选哈希变化、缺失本地资源和外部资源；启发式风格判断不作为阻塞条件。
- 设计 Review 证据契约：blocker 必须关联验收项、文件路径和具体代码证据，否则降级为非阻塞警告；只有真实 blocker 触发一次自动修复。
- 实现信任边界清晰的人工隔离预览：前端只根据 workspace/change-set ID 构造后端 URL，不信任模型返回的 URL，且预览结果不会改变合入状态。
- 实现会话级 Pin + 结构化摘要双层记忆，并使用 pytest、Vitest/Testing Library 覆盖隔离写入、静态检查、冲突、回退、重新审查和 Promote 权限。

## 面试展开

### 为什么取消自动浏览器门禁？

声明式 UI 检查容易因 DOM 定位、前置操作造成的数据变化或原生表单提示差异而误报。项目选择只让“能确定为真”的静态安全问题和有代码证据的 Review blocker 阻止合入；隔离页面供用户人工验收。

### 如何保证“审查的就是合入的”？

Change Set 保存每个文件的 before/after 内容和哈希，静态检查和 Review 绑定同一候选快照。Promote 前再比较正式 Workspace before hash 和候选 hash，冲突则 409，不覆盖。

### 历史失败候选如何处理？

旧记录保持不变。“重新代码审查”从不可变 `after_content` 创建新子 Change Set，基于当前正式 Workspace 重算 Diff 和 before hash，再执行新的 Review-only 流程。

## 不应写入简历的能力

当前仓库没有实现 Playwright 自动验收、Codex CLI、Claude Code CLI、动态 npm 构建、容器部署平台、跨会话向量记忆或任意框架项目预览。
