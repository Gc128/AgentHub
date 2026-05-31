# AgentHub Python Codex 协作文档说明

本目录是一套面向 **Python-first AgentHub 项目** 的仓库根目录协作文档。

建议把这些文件直接放到项目根目录，让所有成员和 Codex / Claude Code / TRAE 在开发前统一遵守。

## 文件说明

| 文件 | 用途 |
|---|---|
| `AGENTS.md` | 仓库级 AI Coding 总规则，Codex 每次任务前优先阅读 |
| `PYTHON_PROJECT_GUIDE.md` | Python 技术栈、目录结构、运行命令与模块边界 |
| `CODEX_TASK_TEMPLATE.md` | 每次给 Codex 派任务时复制使用的模板 |
| `CODEX_REVIEW_CHECKLIST.md` | Codex 生成代码后的人工 Review 清单 |
| `AI_COLLABORATION_RULES.md` | 团队使用 AI Coding 的协作纪律 |
| `PROMPT_LOG.md` | 重要 Prompt 与 AI 产出记录 |
| `DECISION_LOG.md` | 技术决策记录 |
| `MODULE_OWNERS.md` | 三人成员模块边界与负责人 |
| `DEV_STATUS.md` | 当前开发状态追踪 |
| `CONTRIBUTING.md` | GitHub 分支、提交、PR 协作流程 |
| `.github/pull_request_template.md` | GitHub PR 模板 |
| `.codex/README.md` | Codex 使用补充说明 |
| `PYPROJECT_TEMPLATE.toml` | 可参考的 Python 项目配置模板 |
| `.env.example` | 环境变量示例，不填写真实密钥 |

## 使用方式

1. 将本压缩包内容解压到项目根目录；
2. 根据三人真实姓名/昵称修改 `MODULE_OWNERS.md`；
3. 根据最终选型修改 `PYTHON_PROJECT_GUIDE.md` 中的 UI 方案；
4. 每次给 Codex 派任务前复制 `CODEX_TASK_TEMPLATE.md`；
5. 每次 Codex 完成代码后按 `CODEX_REVIEW_CHECKLIST.md` 检查；
6. 重要 Prompt 记录到 `PROMPT_LOG.md`；
7. 架构或技术栈变化记录到 `DECISION_LOG.md`。
