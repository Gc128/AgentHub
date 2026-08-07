# AgentHub Product Spec

## 产品定位

AgentHub 是一个 IM 式多 Agent 开发协作平台，展示可审计、可拒绝、可回退的静态 Web 开发链路。

## 核心流程

1. 用户提出静态页面需求。
2. Orchestrator 产生任务与验收标准。
3. Code Agent 生成完整候选文件，后端生成 Change Set 和 Diff。
4. 候选只进入 Staging，后端执行确定性静态安全检查。
5. Review Agent 审查功能和验收覆盖；只有完整证据的 blocker 才阻止。
6. Review `pass/pass_with_warnings` 进入 `ready`，用户人工查看隔离页面。
7. 用户 Promote 后，后端复核哈希、检测冲突并原子合入。
8. 历史可按 Change Set 整组 Revert 或创建“重新应用”候选。

## 失败原则

- timeout/429/5xx 最多重试一次；Schema 最多格式修复一次。
- Review 未覆盖验收项属于 `review_contract` 失败，不伪装成代码问题，不触发代码修复。
- 不信任模型输出的 Diff、Preview URL、JavaScript 或 shell 指令。
- 不使用浏览器检查结果阻止合入，也不会因浏览器结果自动修代码。
- Promote 前正式 Workspace 不变，Promote 内容必须与已审查候选哈希一致。

## 当前边界

- 只支持静态 HTML/CSS/JavaScript，不运行 npm install、打包或任意命令。
- 默认手动 Promote，自动代码修复最多一次。
- 人工隔离预览不是自动验收门禁。
- 记忆仅在当前会话内，不做跨会话向量检索。
- 未实现 Codex CLI、Claude Code CLI 或公开部署平台。

## Demo 验收

1. 成功：候选 → 静态检查/Review 通过 → 人工预览 → Promote → Revert。
2. 真实 blocker：自动修复一次 → 新子 Change Set → ready/failed。
3. 基础设施失败：明确终止，无假产物，正式 Workspace 不变。
4. 历史 Preview 失败：从不可变快照创建新的 Review-only 子 Change Set。
