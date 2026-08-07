# AgentHub Technical Design

## 1. 系统边界

AgentHub 当前支持静态 HTML/CSS/JavaScript。React 负责会话、候选状态和人工隔离预览；FastAPI 负责 Agent 调度、Change Set、静态安全检查、Review 门禁与 Promote；SQLite 保存会话、候选、Review、记忆和 Applied Diff。

系统不运行模型给出的 shell、构建命令或任意 JavaScript，不自动启动浏览器进行验收。

## 2. Agent 契约与错误语义

- `OrchestratorDecision`：模式、任务依赖和稳定 ID 验收标准。
- `CodeGenerationResult`：摘要和完整候选文件，不接受模型 Diff 或浏览器检查。
- `ReviewReport`：verdict、风险、findings 和验收覆盖。
- Preview artifact：只包含 `available`、`scope`、workspace/change-set ID 和入口路径。

外部模型 timeout/429/5xx 最多重试一次，JSON/Pydantic 错误最多请求一次格式修复。最终失败以 `AgentRunError` 和 `Message.status=failed` 返回，Mock 仅在 `USE_MOCK_AGENTS=true` 时启用。

## 3. Change Set 状态机

```text
generated → staging → validating → ready → promoting → promoted
                              ↘ needs_fix → validating
                              ↘ failed / rejected / conflicted
```

Code Agent 返回文件后，后端：

1. 规范化相对路径，保存正式 Workspace before 内容与 hash。
2. 复制正式 Workspace 到 `.agenthub/staging/{change_set_id}`。
3. 应用 upsert/delete，保存 after 内容与 hash，由后端生成 unified diff。
4. 对同一候选快照执行静态安全检查和 Review。
5. Review `pass/pass_with_warnings` 置 `ready`；有证据 blocker 置 `needs_fix/failed`。

Promote 只接受 `ready`：重新比较 before hash 和候选 hash，写入使用同目录临时文件与 `os.replace`，多文件中途失败会按 before snapshot 回滚。

## 4. 确定性静态检查

`StaticCandidateInspector` 只阻止能从候选快照确定的问题：

- 路径必须在 Workspace 内，Staging 不允许符号链接。
- 候选不能为空、不能包含 NUL，静态 Web 必须有 HTML 入口。
- HTML/CSS 引用的本地资源必须存在。
- 拒绝 `http://`、`https://`、协议相对 URL 和其他外部 scheme。
- Review 前和 Promote 前都复核候选 hash。

括号数量、DOM 选择器风格、可能的运行时行为等启发式判断不作为静态 blocker。

## 5. Review 门禁

Review blocker 必须同时包含：

- 当前验收标准的 `criterion_id`；
- 候选文件 `path`；
- 可核对的具体 `evidence`。

不完整的 blocker 降级为 high 警告，不阻止。Review 未覆盖任一验收项时返回 `review_contract_failed`，该失败不进入代码修复循环。只有有效 blocker 可触发一次 Code Agent 修复和完整重审。

## 6. 人工隔离预览

Preview 是人工查看能力，不是状态门禁。前端 iframe 和新窗口 URL 只由 API client 使用 workspace/change-set ID 构造。显式 `@PreviewAgent` 只返回候选或正式 Workspace 的入口，无入口时返回 `preview_not_available`，不写入 Review/PreviewReport 也不改变 Change Set 状态。

历史 `PreviewReport` 和截图字段/路由仅为旧数据读取保留，新流程不再写入。终态候选的 Staging 已清理时，人工预览从不可变 `after_content` 读取。

## 7. 历史候选和重新应用

- `re-review`：仅允许 `failed` 且快照完整的候选，创建新子 Change Set，基于当前 Workspace 重算 before hash/Diff，只做静态检查与 Review。
- `reapply`：整组 Revert 后创建新候选，也执行 Review-only 流程，不直接写回旧 Diff。

两者都不修改原 Change Set 审计记录。

## 8. 会话记忆、API 与 SSE

`MemoryContextBuilder` 按系统提示词、当前请求、Pin、有效摘要、最近 20 条短期消息、Workspace 与活跃 Change Set 组装上下文。短期窗口由 `SHORT_TERM_CONTEXT_MESSAGES` 配置；每累计 `MEMORY_SUMMARY_TRIGGER_MESSAGES=20` 条新消息时增量更新长期摘要，但仍重叠保留最近 20 条原文。当前用户请求和 Pin 使用独立位置与预算；短期原文超出 token 预算时显式返回 `memory_context_overflow`。

```text
POST /api/workspaces/{workspace_id}/change-sets/{change_set_id}/promote
POST /api/workspaces/{workspace_id}/change-sets/{change_set_id}/revert
POST /api/workspaces/{workspace_id}/change-sets/{change_set_id}/reapply
POST /api/workspaces/{workspace_id}/change-sets/{change_set_id}/re-review
GET  /api/workspaces/{workspace_id}/change-sets/{change_set_id}/preview-page
```

`validation_started/validation_completed` 仅表示 Review，`change_set_ready` 在 Review 通过后发出。

## 9. 验证

```bash
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m mypy agenthub
cd frontend && npm run lint && npm run test && npm run build
```

CI 不安装 Chromium，覆盖 Review-only 状态、静态安全、隔离候选、Promote/冲突/回滚/Revert、重新审查、记忆和前端权限。
