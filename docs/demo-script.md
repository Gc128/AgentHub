# AgentHub Review-Only Demo

## 准备

```bash
python -m pip install -e ".[dev]"
alembic upgrade head
python -m uvicorn agenthub.main:app --host 127.0.0.1 --port 8000
```

另开终端运行 `cd frontend && npm install && npm run dev`。无需安装 Chromium。

## 场景一：成功链路

1. 新建包含 Orchestrator、Code 和 Review 的会话。
2. 发送：

   ```text
   @Orchestrator 创建一个静态 Todo 页面，支持新增、完成、删除、筛选和 localStorage，不引用外部资源。
   ```

3. 展示 Orchestrator 的 `Code → Review` 分工。
4. 展示候选文件清单与后端 Diff，确认正式 Workspace 尚未变化。
5. 展示 Review 报告和 `ready`。
6. 在大弹窗打开人工隔离预览，操作页面确认效果。
7. 点击“合入 Workspace”，展示正式文件和 Preview 更新。
8. 整组 Revert，确认恢复到合入前。

## 场景二：有证据的 Review blocker

让首个候选明确漏掉一项需求，观察：

```text
Review blocker（验收项 + 文件 + 代码证据）
→ needs_fix
→ Code Agent 修复一次
→ 子 Change Set
→ 静态检查 + Review
→ ready 或 failed
```

缺少上述证据的 high/warning 只展示，不会阻止合入。

## 场景三：确定性静态失败

要求页面引用 `https://example.com/app.js` 或一个不存在的本地 CSS。展示后端以具体文件和引用为证据阻止，而不是根据风格或 DOM 猜测报错。

## 场景四：无伪造成功的基础设施失败

使模型连续返回非法 Schema，或配置不可用模型：

- SSE 为 `agent_failed`，消息 `status=failed`；
- 不出现假 Code/Review/Preview 产物；
- 不触发代码修复；
- 正式 Workspace 不变。

## 场景五：历史候选重新审查

1. 选择一条历史 `failed` Change Set。
2. 点击“重新代码审查”。
3. 确认系统创建新子 Change Set，旧记录不变。
4. 新候选通过后再手动 Promote。

## 面试讲解重点

- LLM 是候选生成者，不是正式 Workspace 直接修改者。
- 只有确定性静态问题和有证据 Review blocker 可阻塞。
- 人工 Preview 与状态门禁解耦，避免自动 UI 检查误报。
- Promote 前做候选哈希和 before hash 复核，解决“审查内容”与“合入内容”一致性。
