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

- [ ] 阶段 1：项目初始化
- [ ] 阶段 2：聊天主流程
- [ ] 阶段 3：Orchestrator 与多 Agent 协作
- [ ] 阶段 4：Workspace、Diff 与 Preview
- [ ] 阶段 5：Demo 包装与答辩材料

## 本周任务

| 任务 | 负责人 | 分支 | 状态 | 备注 |
|---|---|---|---|---|
| 初始化 Python 项目结构 |  |  | 未开始 |  |
| 初始化 FastAPI app |  |  | 未开始 |  |
| 实现 Mock AgentAdapter |  |  | 未开始 |  |
| 实现 Orchestrator 规则调度 |  |  | 未开始 |  |
| 实现 workspace 文件读写 |  |  | 未开始 |  |
| 实现聊天 UI 原型 |  |  | 未开始 |  |

## Demo 主线状态

| 环节 | 状态 | 说明 |
|---|---|---|
| 创建会话 | 未开始 |  |
| 发送消息 | 未开始 |  |
| @Agent 识别 | 未开始 |  |
| Orchestrator 拆解 | 未开始 |  |
| 子 Agent 回复 | 未开始 |  |
| 代码 Artifact | 未开始 |  |
| Diff Artifact | 未开始 |  |
| Apply Diff | 未开始 |  |
| Preview | 未开始 |  |

## 风险记录

| 风险 | 等级 | 应对 |
|---|---|---|
| 纯 Python UI 表现不足 | 中 | 先用 NiceGUI / Reflex 打通闭环，必要时后期替换前端 |
| 真实 Agent 接入不稳定 | 高 | 保留 Mock Agent，Demo 时可切换 |
| 三人代码冲突 | 中 | 严格模块分工，全部走 PR |
| 时间不足 | 高 | 优先保证 Demo 主线，不做 P2 功能 |

## 今日更新

### 2026-xx-xx

- 完成：
- 问题：
- 明日计划：
