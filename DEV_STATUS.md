# DEV_STATUS.md

本文件用于追踪 AgentHub 当前开发状态。建议每天结束前更新一次。

## 当前目标

完成 Python-first AgentHub MVP：

```txt
用户提出开发需求
→ Orchestrator 拆解任务
→ 多个 Agent 依次产出
→ 系统展示代码和 Diff
→ 用户应用变更
→ 页面预览更新
```

## 当前阶段

- [x] 阶段 1：项目初始化
- [x] 阶段 2：聊天主流程
- [x] 阶段 3：Orchestrator 与多 Agent 协作
- [x] 阶段 4：Workspace、Diff 与 Preview
- [ ] 阶段 5：Demo 包装与答辩材料

## 本周任务

| 任务 | 负责人 | 分支 | 状态 | 备注 |
|---|---|---|---|---|
| 初始化 Python 项目结构 |  | test | 已完成 | `agenthub/` + tests 已建立 |
| 初始化 FastAPI app |  | test | 已完成 | React 默认连接 FastAPI 8000 |
| 实现 Mock AgentAdapter |  | test | 已完成 | 仅测试/离线夹具使用 |
| 接入真实 OpenAI-compatible Agent |  | test | 已完成 | 需 `.env` 配置 `OPENAI_API_KEY` |
| 实现 Orchestrator 规则调度 |  | test | 已完成 | `/messages/run` 后端串联多 Agent |
| 实现 workspace 文件读写 |  | test | 已完成 | `WORKSPACE_ROOT` 真实文件系统 |
| 实现聊天 UI 原型 |  | test | 已完成 | React 三栏工作台 |

## Demo 主线状态

| 环节 | 状态 | 说明 |
|---|---|---|
| 创建会话 | 已完成 | FastAPI `POST /api/conversations` |
| 发送消息 | 已完成 | React 调用 `POST /api/conversations/{id}/messages/run` |
| @Agent 识别 | 已完成 | 后端 `route_agent` 统一识别 |
| Orchestrator 拆解 | 已完成 | 产出 plan file artifact |
| 子 Agent 回复 | 已完成 | Code / Review / Preview 顺序持久化为聊天消息 |
| 代码 Artifact | 已完成 | Code Agent 必须产出 code artifact |
| Diff Artifact | 已完成 | Code Agent 必须产出 diff artifact |
| Apply Diff | 已完成 | 写入真实 workspace 文件 |
| Preview | 已完成 | `preview_url` 指向 FastAPI preview-page |

## 风险记录

| 风险 | 等级 | 应对 |
|---|---|---|
| 纯 Python UI 表现不足 | 中 | 先用 NiceGUI / Reflex 打通闭环，必要时后期替换前端 |
| 真实 Agent 接入不稳定 | 中 | 生产默认真实 LLM；测试显式启用 Mock |
| 三人代码冲突 | 中 | 严格模块分工，全部走 PR |
| 时间不足 | 高 | 优先保证 Demo 主线，不做 P2 功能 |

## 今日更新

### 2026-06-04

- 完成：React + FastAPI + OpenAI-compatible Agent + 真实 workspace 文件闭环。
- 问题：当前仓库仍处于未完成 merge 状态，提交前需先处理 `.git/MERGE_HEAD`。
- 明日计划：补 Demo 脚本截图/录屏、配置真实模型 key 后做端到端人工演示。
