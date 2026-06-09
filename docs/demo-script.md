# AgentHub Demo Script

## 准备

1. 启动 FastAPI 后端，确认前端 `VITE_API_BASE_URL` 指向 `http://127.0.0.1:8000`。
2. 启动 React 前端。
3. 打开页面后确认没有 Mock Agent 警告；如果是 mock 模式，说明当前是离线演示。

## 演示一：开发任务主链路

1. 新建会话：`Todo App Development`。
2. 选择内置 Agent：Orchestrator、Code Agent、Review Agent、Preview Agent。
3. 发送：

   ```txt
   @Orchestrator 帮我做一个简洁的 Todo List 网页，支持新增、完成、删除和筛选。
   ```

4. 展示用户消息立即出现，Agent 回复按 SSE 一段段流式输出。
5. 展示 Orchestrator 的任务拆解：Code、Review、Preview 各自职责明确。
6. 展示 Code Agent 的 Markdown 说明、code artifact 和 diff artifact。
7. 点击 Apply Diff，说明代码被写入真实 workspace。
8. 在右侧 Workspace 中打开 preview，确认页面来自当前 `entry_path`。
9. 展示 Review Agent 检查结果和 Preview Agent 预览状态。
10. 点击已应用 Diff 的 Revert，说明可以回退到应用前代码。

## 演示二：IM 核心能力

1. 在同一个会话中回复某条 Agent 消息，展示输入框上方的引用预览。
2. 复制一条消息，展示复制提示。
3. Pin 一条需求消息，说明它会作为长期上下文进入后续 Agent 输入。
4. 软删除一条消息，展示时间线位置保留，但正文和 artifacts 被隐藏。
5. 对某条用户消息点击重新生成，展示不会重复创建用户消息，只追加新的 Agent 回复。
6. 归档会话，再切换到 archived/all 筛选展示恢复能力。

## 演示三：自建 Agent

1. 点击左侧 Agent 区的“管理”。
2. 新建自建 Agent：

   - 名称：`需求澄清 Agent`
   - 描述：`帮助用户把模糊需求拆成可执行问题`
   - 能力标签：`clarify, product`
   - 系统提示词：

     ```txt
     你是 AgentHub 的需求澄清 Agent。你不直接写代码，而是把用户的模糊需求整理成 3 个关键问题，并给出建议的下一步。
     ```

3. 点击测试 Agent，输入：`我想做一个学生成绩管理页面`。
4. 保存并启用 Agent。
5. 在会话成员管理中加入 `需求澄清 Agent`。
6. 在输入框输入或从 @ 菜单选择：

   ```txt
   @需求澄清Agent 我想做一个学生成绩管理页面
   ```

7. 展示自建 Agent 按系统提示词回复。
8. 禁用该 Agent，展示它不再出现在新会话成员候选和 @ 菜单中。

## 演示四：继续迭代

1. 回到开发会话，发送一个小改动：

   ```txt
   @CodeAgent 把 Todo 页面改成深浅主题切换，并保留现有交互。
   ```

2. 展示 Code Agent 新 diff。
3. Apply Diff 后刷新 preview。
4. 说明同一个 workspace 支持多轮对话迭代和回退。

## 讲解重点

- 前端只负责 IM 体验、SSE 消费和 artifact 操作；后端负责真实执行闭环。
- Orchestrator harness 让多 Agent 协作可观察、可校验、可重试。
- Apply Diff 与 Preview 操作的是同一份真实 workspace 文件。
- 自建 Agent 第一版配置系统提示词，复用全局 LLM 后端，不保存用户密钥。
