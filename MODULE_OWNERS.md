# MODULE_OWNERS.md

本文件记录 AgentHub 三人成员的模块负责人。请在项目开始时把“成员 A / B / C”替换为真实姓名或昵称。

## 1. 模块分工

| 模块 | 负责人 | 目录 | 说明 |
|---|---|---|---|
| Python UI / 聊天界面 | 成员 A | `agenthub/ui/` | 会话列表、消息流、Artifact 卡片、预览入口 |
| FastAPI 后端 | 成员 B | `agenthub/api/`、`agenthub/services/` | 会话 API、消息 API、Agent 调用 API |
| Agent Adapter | 成员 B | `agenthub/agents/` | Mock Agent、真实 Agent 适配、Agent Registry |
| Orchestrator | 成员 B | `agenthub/orchestrator/` | 任务拆解、调度、汇总 |
| Workspace | 成员 C | `agenthub/workspace/` | 文件读写、Diff、Git、预览 |
| 数据模型 | 成员 B + 成员 C | `agenthub/models/`、`agenthub/schemas/` | 数据库模型和 Pydantic schema |
| 测试 | 三人共同 | `tests/` | 各自模块必须补充测试 |
| 文档与 Demo | 三人共同 | `docs/` | 产品文档、技术文档、Prompt 记录、Demo 脚本 |

## 2. 修改规则

1. 修改自己负责的模块前，不需要额外审批；
2. 修改他人负责模块前，必须先在群里说明；
3. 修改 `agenthub/schemas/`、`agenthub/agents/base.py`、`agenthub/orchestrator/` 接口前，必须通知全员；
4. 修改目录结构前，必须记录到 `DECISION_LOG.md`；
5. 修改 Demo 主线前，必须三人确认。

## 3. Review 规则

| PR 类型 | Review 要求 |
|---|---|
| UI 改动 | 成员 A 自查，至少一名队友 Review |
| API 改动 | 成员 B 自查，至少一名队友 Review |
| Agent / Orchestrator 改动 | 成员 B 自查，成员 A 或 C Review |
| Workspace / Diff / Git 改动 | 成员 C 自查，成员 B Review |
| Schema / Adapter 接口改动 | 全员知会 |
| 文档改动 | 可快速合并，但关键信息需同步 |

## 4. 冲突处理

如果两个成员同时需要修改同一模块：

1. 先在 GitHub Issue 或群聊中说明；
2. 拆分任务边界；
3. 先合并更底层的接口改动；
4. 后合并依赖接口的功能改动；
5. 必要时由模块负责人统一整理。
