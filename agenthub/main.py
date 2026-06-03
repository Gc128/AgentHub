from fastapi import FastAPI
from fastapi.requests import Request
from fastapi.responses import JSONResponse

from agenthub.api import agents, conversations, messages, workspaces
from agenthub.core.errors import AgentHubError, ErrorResponse


def create_app() -> FastAPI:
    app = FastAPI(title="AgentHub", version="0.1.0")

    @app.exception_handler(AgentHubError)
    async def agenthub_error_handler(_request: Request, exc: AgentHubError) -> JSONResponse:
        error = ErrorResponse(code=exc.code, message=exc.message)
        return JSONResponse(status_code=exc.status_code, content=error.model_dump())

    app.include_router(conversations.router, prefix="/api", tags=["conversations"])
    app.include_router(messages.router, prefix="/api", tags=["messages"])
    app.include_router(agents.router, prefix="/api", tags=["agents"])
    app.include_router(workspaces.router, prefix="/api", tags=["workspaces"])

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "agenthub"}

    return app


app = create_app()
