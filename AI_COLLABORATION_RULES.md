# AI_COLLABORATION_RULES.md

本文件规定 AgentHub 团队使用 Codex / Claude Code / TRAE 等 AI Coding 工具时必须遵守的规则。

## 1. 基本原则

1. AI 是开发助手，不是最终负责人；
2. 每段 AI 生成代码都必须由对应成员人工 Review；
3. 不允许直接把 AI 生成的大段代码合并到 `dev` 或 `main`；
4. 不允许让 AI 无边界地“重构整个项目”；
5. 不允许让 AI 处理真实密钥、隐私数据或未脱敏日志。

## 2. 每次使用 AI 前必须准备

1. 明确当前任务；
2. 明确允许修改的文件；
3. 明确禁止修改的文件；
4. 明确验收标准；
5. 明确运行和测试命令；
6. 明确是否允许新增依赖。

推荐直接复制 `CODEX_TASK_TEMPLATE.md`。

## 3. Python 项目专项规则

1. 要求 AI 输出类型注解；
2. 要求 AI 使用 Pydantic 处理 API 输入输出；
3. 要求 AI 为核心逻辑补充 pytest；
4. 要求 AI 不在 FastAPI route 中堆业务逻辑；
5. 要求 AI 不使用 `shell=True`；
6. 要求 AI 对 workspace 路径做越权检查；
7. 要求 AI 不硬编码密钥、绝对路径、个人电脑路径；
8. 要求 AI 对外部 API 调用设置 timeout。

## 4. AI 输出后必须检查

1. 是否可运行；
2. 是否通过 pytest；
3. 是否通过 ruff；
4. 是否通过 mypy 或至少没有明显类型问题；
5. 是否修改了无关文件；
6. 是否引入了不必要依赖；
7. 是否影响其他成员模块；
8. 是否需要同步更新文档。

## 5. Prompt 记录规则

以下情况必须记录到 `PROMPT_LOG.md`：

1. 生成核心模块；
2. 设计 Agent Adapter；
3. 设计 Orchestrator；
4. 设计 workspace / diff / preview；
5. 修复关键 bug；
6. 让 AI 做架构调整；
7. 让 AI 做性能或安全相关修改。

## 6. 决策记录规则

以下情况必须记录到 `DECISION_LOG.md`：

1. 更换框架；
2. 新增重要依赖；
3. 修改目录结构；
4. 修改 Agent Adapter 接口；
5. 修改数据库模型；
6. 修改 Demo 主线；
7. 从全 Python UI 切换到 React 前端，或反向切换。

## 7. 禁止给 AI 的任务

1. “帮我把整个项目全部重构一下”；
2. “随便改到能跑为止”；
3. “自动提交并 push”；
4. “把我的 API Key 写进代码里”；
5. “忽略测试，先合并”；
6. “删除冲突文件重新生成”。

## 8. 推荐给 AI 的任务表达

推荐：

```txt
请只在 agenthub/agents/ 和 tests/test_agents/ 中实现 MockAgentAdapter，遵守 AgentAdapter Protocol，补充 pytest，并说明如何验证。
```

不推荐：

```txt
帮我做一下 Agent 功能。
```
