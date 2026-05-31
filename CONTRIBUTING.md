# CONTRIBUTING.md

本文件规定 AgentHub 项目的 GitHub 协作流程。

## 1. 分支模型

```txt
main                  # 稳定可演示版本
dev                   # 日常集成分支
feature/xxx           # 功能分支
fix/xxx               # 修复分支
docs/xxx              # 文档分支
```

## 2. 开发流程

```bash
git checkout dev
git pull origin dev
git checkout -b feature/xxx
```

完成后：

```bash
git add .
git commit -m "feat: add xxx"
git push origin feature/xxx
```

然后在 GitHub 创建 Pull Request，目标分支为 `dev`。

## 3. 合并规则

1. 不允许直接 push 到 `main`；
2. 不建议直接 push 到 `dev`；
3. 每个 PR 只解决一个明确问题；
4. 至少一名队友 Review；
5. 合并前必须能本地运行；
6. 合并后及时删除远程 feature 分支；
7. 每个稳定节点由 `dev` 合并到 `main`。

## 4. Commit 规范

```txt
feat: 新功能
fix: 修复 bug
docs: 文档修改
style: 样式调整
refactor: 重构
test: 测试
chore: 工程配置
```

示例：

```bash
git commit -m "feat: add mock agent adapter"
git commit -m "fix: handle empty agent response"
git commit -m "docs: update python codex rules"
```

## 5. PR 描述要求

每个 PR 必须说明：

1. 本次完成了什么；
2. 修改了哪些模块；
3. 如何测试；
4. 是否影响其他成员；
5. 是否使用 AI 生成；
6. 是否更新了文档。

## 6. Python PR 前检查

建议执行：

```bash
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m mypy agenthub
```

如果使用 `uv`：

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy agenthub
```

## 7. 合并前检查

- [ ] 已基于最新 `dev`
- [ ] 无明显冲突
- [ ] 本地可运行
- [ ] 无敏感信息
- [ ] 无无关文件修改
- [ ] 已更新必要文档
- [ ] 已记录重要 Prompt

## 8. 版本节点

每次形成可演示版本时，建议打 tag：

```bash
git tag demo-v0.1
git push origin demo-v0.1
```

版本节点建议：

```txt
demo-v0.1：FastAPI + Python UI 骨架
demo-v0.2：Mock Agent 回复
demo-v0.3：Orchestrator 多 Agent 协作
demo-v0.4：Diff 与 Preview
demo-v1.0：比赛最终 Demo
```
