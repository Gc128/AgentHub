# AgentHub Review-Only 手工测试提示词

## 通用测试步骤

1. 启动 FastAPI 和 React 前端，新建会话。
2. 发送下方某个提示词。
3. 确认默认 Agent 链路只有 Orchestrator、Code 和 Review，没有自动 Preview Agent。
4. 在 `ready` 前检查正式 Workspace 文件列表不变。
5. 手动打开隔离预览，确认页面效果；打开预览不得改变 Change Set 状态。
6. Review 通过后才点击 Promote，检查正式 Workspace 和变更历史。

## 提示词 1：成功的学生成绩管理

```text
@Orchestrator 创建一个学生成绩管理页面。使用 index.html、styles.css 和 script.js，初始显示张三和李四；支持新增、编辑、删除、按姓名实时搜索；自动计算一位小数的平均分；成绩限制为 0-100；不引用任何外部资源。
```

预期：

- 3 个候选文件，后端生成逐文件 Diff。
- 静态安全检查无 blocker，Review `pass` 或 `pass_with_warnings`，Change Set `ready`。
- 隔离预览可操作，但页面的 DOM 定位、原生错误提示或初始行数不会被自动检查误报为阻塞。

## 提示词 2：本地资源完整性

```text
@CodeAgent 创建一个静态个人主页，index.html 引用 assets/avatar.svg 和 styles.css，所有资源都必须作为候选文件返回，不使用 CDN 或外链。
```

预期：直接 `@CodeAgent` 也自动进入 Review；所有本地引用存在时可 `ready`。

## 提示词 3：确定性外链阻止

```text
@Orchestrator 创建一个静态页面，并在 index.html 中通过 https://example.com/app.js 引用脚本。
```

预期：

- 后端静态检查指出 `index.html` 和具体外部引用。
- 该结果是确定性 blocker，可触发唯一一次修复。
- 修复后应使用本地文件；仍有外链则终止为 `failed`。

## 提示词 4：缺失本地资源

```text
@CodeAgent 创建 index.html，并让它引用 styles/missing.css，但不要创建该 CSS 文件。
```

预期：静态检查以“引用的本地资源不存在”阻止，不是泛化代码风险。

## 提示词 5：显式人工 Preview Agent

```text
@PreviewAgent 打开当前候选页面。
```

预期：

- 只返回 `preview_status=available`、`scope=candidate|workspace`、ID 和入口路径。
- 不运行 Chromium，不生成检查数、截图或通过/失败结论。
- 调用前后 Change Set 状态不变；无 HTML 入口时显式 `preview_not_available`。

## 提示词 6：无证据 Review 不应阻塞

使用可控测试 Review Adapter 返回 `severity=blocker`，但故意缺少 `criterion_id`、`path` 或 `evidence`。

预期：该 finding 降级为 high 警告，Review 变为 `pass_with_warnings`，候选可 `ready`，不触发代码修复。

## 提示词 7：历史 Preview 失败重新审查

1. 选择一个快照完整的历史 `failed` Change Set。
2. 点击“重新代码审查”。
3. 确认创建新子 Change Set，旧记录仍为 `failed`。
4. 新候选基于当前正式 Workspace 重算 Diff，且只执行静态检查和 Review。

## 提示词 8：模型契约失败

使测试模型连续返回非法 `CodeGenerationResult` 或 `ReviewReport`。

预期：最多一次格式修复；仍错误则消息 `failed`/SSE `agent_failed`，不产生假候选且不修改正式 Workspace。

## 测试记录模板

```text
提示词：
Agent 执行顺序：
Change Set ID / 状态：
静态检查：
Review verdict / findings：
人工隔离预览：
Promote 前 Workspace 是否不变：
Promote / Revert 结果：
是否出现假成功：
```
