# DECISION_LOG.md

本文件记录 AgentHub 项目的关键技术决策，便于答辩时解释架构选型。

## 决策模板

```md
## ADR-xxx：决策标题

日期：2026-xx-xx  
决策人：成员 A / B / C  
状态：已接受 / 已废弃 / 观察中

### 背景

为什么需要做这个决策？

### 备选方案

1. 方案 A
2. 方案 B
3. 方案 C

### 最终选择

选择 xxx。

### 选择理由

1. xxx
2. xxx
3. xxx

### 代价与风险

1. xxx
2. xxx

### 后续影响

需要修改哪些模块或文档？
```

---

## ADR-001：采用 Python-first 技术栈

日期：2026-xx-xx  
决策人：全体成员  
状态：已接受

### 背景

团队希望整个 AgentHub 项目尽量使用 Python 开发，以降低三人协作成本，并更方便实现 Agent、Orchestrator、workspace、diff、preview 等后端能力。

### 备选方案

1. Next.js + Node.js 全栈；
2. React 前端 + Python 后端；
3. NiceGUI / Reflex + FastAPI 全 Python；
4. Streamlit / Gradio 快速原型。

### 最终选择

优先采用 Python-first 架构。MVP 阶段可选择 NiceGUI / Reflex + FastAPI；如果后期 UI 表现不足，可保留 Python 后端并替换为 React 前端。

### 选择理由

1. Python 更适合快速实现 Agent 调度、文件处理、Diff、Git 封装；
2. 团队技术栈统一，降低协作成本；
3. Codex 生成 Python 后端逻辑较容易 Review；
4. FastAPI 适合提供清晰的 API 和 SSE 流式输出。

### 代价与风险

1. 纯 Python UI 的复杂 IM 体验可能不如 React；
2. Monaco Editor、复杂 Diff Viewer 可能需要额外集成；
3. 如果后期换前端，需要保持 API 层稳定。

### 后续影响

1. 更新 `AGENTS.md`；
2. 更新 Codex 任务模板；
3. 更新 Review Checklist；
4. 按 Python 目录结构初始化项目。
