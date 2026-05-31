# PYTHON_PROJECT_GUIDE.md

本文件用于说明 AgentHub Python-first 版本的工程选型与开发约定。

## 1. 关键调整结论

如果 AgentHub 改为 Python 开发，需要重点调整以下内容：

1. 后端由 Node.js / NestJS / Express 改为 FastAPI；
2. TypeScript 类型定义改为 Pydantic 模型；
3. Agent Adapter 改为 Python `Protocol` + async 接口；
4. Workspace、Diff、Git 封装改为 Python 模块；
5. 测试工具改为 pytest；
6. Lint / Format 改为 ruff；
7. 类型检查改为 mypy 或 pyright；
8. 包管理可使用 uv / pip / Poetry，团队必须统一；
9. 如果坚持全 Python UI，优先考虑 NiceGUI 或 Reflex；
10. 如果更重视最终展示效果，可保留 React 前端，后端和 Agent 层全部 Python。

## 2. 推荐架构

### 方案 A：Python-first，保留高质量 Web 前端

```txt
React / Next.js 前端
        ↓ HTTP / SSE
FastAPI 后端
        ↓
Orchestrator / Agent Adapter / Workspace / Diff / Preview
        ↓
SQLite / Git / 本地 workspace
```

优点：UI 效果最好，适合比赛 Demo。  
缺点：不是 100% Python。

### 方案 B：全 Python Demo

```txt
NiceGUI / Reflex UI
        ↓ 直接调用或 HTTP
FastAPI 服务层
        ↓
Orchestrator / Agent Adapter / Workspace / Diff / Preview
        ↓
SQLite / Git / 本地 workspace
```

优点：几乎全 Python，团队技术栈统一。  
缺点：复杂 IM 交互、Monaco 编辑器、精细 Diff UI 需要额外处理。

### 建议

比赛早期可以采用 **方案 B** 快速打通闭环；如果后期 UI 表现不够，再把 UI 层替换成 React，Python 后端不需要大改。

## 3. 模块边界

### API 层

只负责：

- 接收请求；
- 参数校验；
- 调用 service；
- 返回响应；
- SSE 流式输出。

不负责：

- 复杂业务逻辑；
- 直接读写 workspace；
- 直接拼接 prompt；
- 直接调用某个 Agent API。

### Service 层

负责：

- 会话管理；
- 消息管理；
- Agent 调用编排；
- 数据库事务；
- 业务错误处理。

### Orchestrator 层

负责：

- 任务理解；
- 任务拆解；
- Agent 选择；
- 子 Agent 调用顺序；
- 最终汇总。

### Agent Adapter 层

负责：

- Mock Agent；
- Codex Agent；
- Claude Agent；
- OpenCode Agent；
- 统一输入输出结构；
- 错误兜底。

### Workspace 层

负责：

- 创建 workspace；
- 文件读写；
- 路径安全；
- Diff 生成和应用；
- Git commit；
- 预览服务。

## 4. FastAPI API 示例

```python
from fastapi import APIRouter, Depends
from agenthub.schemas.agent import AgentRunRequest, AgentRunResponse
from agenthub.services.agent_service import AgentService, get_agent_service

router = APIRouter(prefix="/api/agent", tags=["agent"])

@router.post("/run", response_model=AgentRunResponse)
async def run_agent(
    request: AgentRunRequest,
    service: AgentService = Depends(get_agent_service),
) -> AgentRunResponse:
    return await service.run_agent(request)
```

## 5. SSE 流式输出建议

MVP 阶段可以先不用复杂 WebSocket，优先用 FastAPI `StreamingResponse` 或 SSE。

```python
from collections.abc import AsyncIterator
from fastapi.responses import StreamingResponse

async def event_stream() -> AsyncIterator[str]:
    yield "data: Orchestrator 正在拆解任务...\n\n"
    yield "data: Code Agent 正在生成代码...\n\n"

return StreamingResponse(event_stream(), media_type="text/event-stream")
```

## 6. 数据模型建议

Pydantic schema 与数据库 model 分开，避免 API 返回结构被数据库实现绑定。

```txt
models/     # SQLModel / SQLAlchemy ORM
schemas/    # Pydantic API DTO
```

## 7. Workspace 路径安全原则

所有用户传入路径必须经过安全解析：

```python
from pathlib import Path

class WorkspacePathError(ValueError):
    pass

def resolve_workspace_path(root: Path, relative_path: str) -> Path:
    root = root.resolve()
    target = (root / relative_path).resolve()
    if root not in target.parents and target != root:
        raise WorkspacePathError("Path escapes workspace root")
    return target
```

禁止直接使用用户传入路径进行读写。

## 8. Git 命令封装原则

1. 使用 `subprocess.run([...], cwd=workspace_root, timeout=...)`；
2. 不使用 `shell=True`；
3. 不拼接用户输入为命令字符串；
4. 捕获 stdout / stderr；
5. 错误返回可读信息；
6. 不自动 push。

## 9. 推荐命令

如果使用标准 pip：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
uvicorn agenthub.api.main:app --reload
pytest
ruff check .
ruff format .
mypy agenthub
```

如果使用 uv：

```bash
uv sync
uv run uvicorn agenthub.api.main:app --reload
uv run pytest
uv run ruff check .
uv run ruff format .
uv run mypy agenthub
```

Windows PowerShell 激活虚拟环境：

```powershell
.venv\Scripts\Activate.ps1
```

## 10. 初期开发顺序

1. 建立 FastAPI app；
2. 建立 Pydantic schema；
3. 建立 Mock Agent Adapter；
4. 建立 Orchestrator 规则调度；
5. 建立会话和消息 API；
6. 建立 workspace 文件读写；
7. 建立 diff 生成；
8. 建立 preview；
9. 再优化 UI。
