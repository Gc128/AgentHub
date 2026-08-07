# AgentHub 架构

```text
React UI
  ├─ 会话/SSE
  ├─ Change Set 状态与 Review 报告
  ├─ 人工隔离 Preview（可交互 iframe）
  └─ Promote / Revert / Reapply / Re-review
          │
FastAPI ── AgentService ── Orchestrator → Code → Review
   │            │
   │            └─ MemoryContextBuilder
   │
   └─ ChangeSetService
        ├─ Workspace 路径与 hash 边界
        ├─ Staging 快照 + 后端 unified diff
        ├─ StaticCandidateInspector
        ├─ Review 证据门禁
        └─ 原子 Promote + Applied Diff
                 │
         SQLite / filesystem
```

## 信任边界

- 模型可产生候选文件和 Review 意见，不可产生可信 Diff、Preview URL 或合入状态。
- 后端负责路径、快照、Diff、静态安全检查、冲突检测和原子写入。
- Review 仅在 blocker 具有验收项、路径和证据时可阻塞。
- 人工 Preview 只是读取候选快照的 UI，不调整状态。

## 关键不变式

1. Promote 前正式 Workspace 不变。
2. Promote 内容哈希等于已 Review 候选哈希。
3. 正式 Workspace before hash 变化时返回冲突，不覆盖。
4. 旧 Change Set 不修改；修复、重新应用和重新审查都创建子 Change Set。
5. Agent 基础设施/契约失败不会变成业务成功。
