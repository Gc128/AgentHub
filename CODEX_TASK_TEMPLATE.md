# CODEX_TASK_TEMPLATE.md

每次让 Codex 开始一个具体任务前，建议复制以下模板，并补全内容后发送给 Codex。

---

## Codex 任务模板

你是 AgentHub 项目的 Python AI Coding 助手。请先阅读并遵守仓库根目录的 `AGENTS.md` 和 `PYTHON_PROJECT_GUIDE.md`。

### 1. 项目背景

AgentHub 是一个 IM 聊天式多 Agent 协作平台。当前目标是完成一个稳定可演示的 MVP：

```txt
用户提出开发需求
→ Orchestrator 拆解任务
→ 多个 Agent 依次产出
→ 系统展示代码和 Diff
→ 用户应用变更
→ 页面预览更新
```

### 2. 当前任务

请实现：

```txt
【在这里填写具体任务，例如：实现 FastAPI 消息发送接口】
```

### 3. 任务边界

本次只做：

```txt
【列出本次必须完成的功能】
```

本次不要做：

```txt
【列出本次禁止扩展的内容】
```

### 4. 允许修改文件

```txt
【列出允许修改的文件或目录】
```

### 5. 禁止修改文件

```txt
【列出禁止修改的文件或目录】
```

### 6. Python 技术约束

1. 使用 Python 3.11+；
2. FastAPI route 只负责请求响应，不写复杂业务逻辑；
3. API 请求和响应必须使用 Pydantic 模型；
4. 核心函数必须有类型注解；
5. 文件路径使用 `pathlib.Path`；
6. 外部 API 调用使用 async；
7. 不要硬编码密钥；
8. 不要提交 `.env`；
9. 不要使用 `shell=True`；
10. 如果需要新依赖，先说明原因。

### 7. 接口 / 类型约束

必须遵守以下类型或接口：

```python
【粘贴相关 Pydantic 模型、Protocol 或函数签名】
```

### 8. UI / 交互要求

```txt
【描述页面效果、交互方式、加载状态、错误状态；如果本任务不涉及 UI，写“不涉及”】
```

### 9. 验收标准

完成后必须满足：

```txt
1. xxx
2. xxx
3. xxx
```

### 10. 建议验证命令

```bash
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m mypy agenthub
```

如果项目使用 `uv`：

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy agenthub
```

### 11. 输出要求

完成后请按以下格式回复：

```md
## 完成情况

## 修改文件

## 核心逻辑

## 如何验证

## 风险与后续
```

### 12. 注意事项

1. 不要擅自大范围重构；
2. 不要引入大型依赖；
3. 不要硬编码密钥；
4. 不要修改无关文件；
5. 如果发现当前代码结构无法完成任务，请先说明问题和最小改动方案。
