# CODEX_REVIEW_CHECKLIST.md

本清单用于每次 Codex 生成代码后的人工检查，也用于 Pull Request 前自查。

## 1. 基础检查

- [ ] Codex 是否遵守了 `AGENTS.md`？
- [ ] 是否遵守了 `PYTHON_PROJECT_GUIDE.md`？
- [ ] 是否只完成了本次任务范围内的内容？
- [ ] 是否修改了未授权文件？
- [ ] 是否删除或破坏了其他成员的代码？
- [ ] 是否引入了不必要的新依赖？
- [ ] 是否出现不可运行的伪代码？
- [ ] 是否存在明显 Python 语法错误？
- [ ] 核心函数是否有类型注解？
- [ ] API 入参和出参是否使用 Pydantic 模型？

## 2. 运行检查

- [ ] 依赖可以正常安装
- [ ] FastAPI 可以正常启动
- [ ] Python UI 可以正常启动，如果项目使用 NiceGUI / Reflex
- [ ] 页面没有明显运行时报错
- [ ] 控制台没有关键错误
- [ ] API 可以正常返回
- [ ] Mock 数据可以正常工作

建议命令：

```bash
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m mypy agenthub
python -m uvicorn agenthub.api.main:app --reload
```

如果项目使用 `uv`：

```bash
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy agenthub
uv run uvicorn agenthub.api.main:app --reload
```

如果某些脚本还不存在，需要在 PR 描述中说明。

## 3. 功能检查

- [ ] 是否满足任务验收标准？
- [ ] 是否覆盖空状态？
- [ ] 是否覆盖加载状态？
- [ ] 是否覆盖错误状态？
- [ ] 是否影响 Demo 主线？
- [ ] 是否能和其他模块联动？

## 4. AgentHub 专项检查

### 聊天模块

- [ ] 用户消息展示正确
- [ ] Agent 消息展示正确
- [ ] 代码块展示正确
- [ ] Artifact 卡片展示正确
- [ ] `@Agent` 识别正确
- [ ] 会话切换后消息不丢失

### Orchestrator 模块

- [ ] 能正确拆解任务
- [ ] 能选择合适 Agent
- [ ] 能汇总子 Agent 结果
- [ ] 出错时有降级逻辑
- [ ] 输出结构清晰
- [ ] 没有把复杂调度逻辑写死在 API route 中

### Agent Adapter 模块

- [ ] 所有 Agent 通过统一接口调用
- [ ] 真实 Agent 和 Mock Agent 可切换
- [ ] API Key 未暴露到前端或 UI
- [ ] 错误信息可读
- [ ] 返回结果包含必要字段
- [ ] 外部调用设置 timeout
- [ ] async 调用没有被错误阻塞

### Workspace / Diff / Preview 模块

- [ ] 文件读写限制在 workspace 内
- [ ] 用户传入路径经过安全解析
- [ ] Diff 可正确生成
- [ ] Apply Diff 后文件内容正确
- [ ] 预览地址可访问
- [ ] Git commit 不包含敏感文件
- [ ] `subprocess` 未使用 `shell=True`

## 5. 安全检查

- [ ] 没有提交 `.env`
- [ ] 没有硬编码 API Key
- [ ] 没有输出敏感日志
- [ ] 文件路径没有越权访问风险
- [ ] shell 命令没有危险操作
- [ ] 前端或 UI 没有直接调用敏感 AI API
- [ ] 没有把用户输入直接拼接到命令行或文件路径中

## 6. 文档检查

- [ ] 是否需要更新 README？
- [ ] 是否需要更新 API 文档？
- [ ] 是否需要更新 `PROMPT_LOG.md`？
- [ ] 是否需要更新 `DEV_STATUS.md`？
- [ ] 是否需要更新 `DECISION_LOG.md`？
- [ ] 是否需要在 Demo 脚本中体现该功能？

## 7. PR 前最终检查

- [ ] 当前分支来自最新 `dev`
- [ ] Commit 信息符合规范
- [ ] PR 标题清晰
- [ ] PR 描述包含测试方法
- [ ] 至少一名组员 Review
- [ ] 合并后不影响 Demo 主线
