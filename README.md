# AgentHub

AgentHub 是一个 React + FastAPI 的 IM 式多 Agent 开发协作平台。它把模型输出视为不可信候选，通过隔离 Change Set、确定性静态安全检查和有证据的代码审查控制合入；隔离预览只供用户人工查看，不参与 `ready` 判定。

## Review-Only 开发闭环

```text
用户需求
→ Orchestrator 生成任务和验收标准
→ Code Agent 返回完整候选文件
→ 后端生成 Change Set、unified diff 和隔离 Workspace
→ 后端执行确定性静态安全检查
→ Review Agent 审查代码和验收覆盖
→ Review pass/pass_with_warnings 后进入 ready
→ 用户人工查看隔离页面并 Promote
→ 后端复核哈希并原子写入正式 Workspace
```

核心保证：

- Promote 前正式 Workspace 字节级不变。
- `ready` 只由静态安全检查和 Review 决定，不运行 Playwright/Chromium。
- Review blocker 必须同时有验收项、文件路径和具体代码证据；缺少证据的结论降级为非阻塞警告。
- 确定性安全检查会拒绝路径越界、哈希变化、符号链接、空候选、NUL、缺失入口/本地资源与外部资源。
- Preview URL 只由前端 API client 按 `workspace_id/change_set_id` 构造，模型 URL 不会被信任。
- Schema、配置和网络失败会显式终止，不会产生假代码、假 Review 或假 Preview。
- 只有有证据的 Review blocker 可触发一次代码修复；第二次仍失败则明确终止。

第一版只支持静态 HTML/CSS/JavaScript，不执行模型给出的 shell、构建命令或任意 JavaScript。

## 已实现能力

- 会话、`@Agent` 路由、SSE 流式状态、引用、软删除和 Pin。
- `OrchestratorDecision`、`CodeGenerationResult`、`ReviewReport` 角色专属契约。
- Change Set 状态机、隔离 Staging、多文件 Diff、冲突检测、Promote 和整组 Revert。
- 直接 `@CodeAgent` 也固定进入 `Code → 静态检查 → Review`。
- 整组回退后的“重新应用”会创建新候选并重新 Review，不直接复活旧 Diff。
- 历史 Preview 失败候选可“重新代码审查”；新子 Change Set 基于当前 Workspace 重算 Diff，旧记录不变。
- 显式 `@PreviewAgent` 只返回人工预览入口，不改变 Change Set 状态。
- 会话级 Pin + 结构化摘要双层记忆。
- SQLite/SQLModel 持久化、Alembic 基线，以及 React 的候选/正式 Workspace 分区 UI。
- Mock Agent 只在 `USE_MOCK_AGENTS=true` 时启用，真实 Agent 失败不会自动切换。

<!-- 当前未实现 Codex CLI、Claude Code CLI、npm 动态构建或公开部署平台，简历不应声明这些能力。 -->

## 技术栈

| 模块 | 技术 |
| --- | --- |
| 后端 | Python 3.11+、FastAPI、Pydantic v2、asyncio |
| Agent | LangChain、OpenAI-compatible Chat Completions、角色专属 Schema |
| 数据 | SQLite、SQLModel、Alembic |
| 安全门禁 | 确定性静态检查、Review 证据契约、SHA-256 |
| Workspace | pathlib、unified diff、`os.replace`、失败回滚 |
| 前端 | React、TypeScript、Vite、Ant Design |
| 测试 | pytest、Vitest、Testing Library |
| 质量 | ruff、mypy strict、ESLint |

## 快速启动

### 1. 安装

```bash
python -m pip install -e ".[dev]"
cd frontend && npm install && cd ..
```

### 2. 配置

```bash
cp .env.example .env
```

在 `.env` 填写真实模型配置；不要提交该文件。若只需离线 UI Demo，可显式设置 `USE_MOCK_AGENTS=true`。

### 3. 初始化空数据库

```bash
alembic upgrade head
```

当前 Alembic 是面向空库的完整基线。开发阶段的无版本旧库请先移走，再执行迁移。

### 4. 运行

终端 1：

```bash
python -m uvicorn agenthub.main:app --reload --host 127.0.0.1 --port 8000
```

终端 2：

```bash
cd frontend
npm run dev
```

打开 `http://127.0.0.1:5173/`。新流程不需安装 Chromium。

## Change Set API

```text
GET  /api/workspaces/{workspace_id}/change-sets
GET  /api/workspaces/{workspace_id}/change-sets/{change_set_id}
POST /api/workspaces/{workspace_id}/change-sets/{change_set_id}/promote
POST /api/workspaces/{workspace_id}/change-sets/{change_set_id}/reject
POST /api/workspaces/{workspace_id}/change-sets/{change_set_id}/revert
POST /api/workspaces/{workspace_id}/change-sets/{change_set_id}/reapply
POST /api/workspaces/{workspace_id}/change-sets/{change_set_id}/re-review
GET  /api/workspaces/{workspace_id}/change-sets/{change_set_id}/preview-page
GET  /api/workspaces/{workspace_id}/change-sets/{change_set_id}/preview-assets/{path}
```

SSE 的 `validation_started/validation_completed` 现在专指 Review 阶段；`change_set_ready` 在 Review 通过后发出。`agent_done` 只表示真实成功。历史 PreviewReport/截图字段和读取路由仅用于旧数据，新流程不再写入。

旧 `/apply-diff` 已 deprecated 且默认关闭，主前端不调用。

## 验证

```bash
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m mypy agenthub

cd frontend
npm run lint
npm run test
npm run build
```

测试覆盖 Review-only 状态计算、静态安全检查、隔离写入、Promote/冲突/Revert/重新应用、旧失败候选重新审查、人工预览 URL 信任边界、记忆 overflow 和前端 Promote 权限。

## 目录

```text
agenthub/                 Python 后端
frontend/                 React 客户端
alembic/                  空库完整基线
tests/                    pytest 测试
.agenthub/staging/        临时候选 Workspace（git ignored）
.agenthub/preview-artifacts/  历史 Preview 产物（git ignored）
```

<!-- 详见 [技术设计](docs/tech-design.md)、[Demo 脚本](docs/demo-script.md)、[手工测试提示词](docs/manual-test-prompts.md) 和 [简历表述](docs/resume-notes.md)。 -->
