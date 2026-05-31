from fastapi import FastAPI

from agenthub.api import agents, conversations, messages, workspaces


def create_app() -> FastAPI:
    app = FastAPI(title="AgentHub", version="0.1.0")
    app.include_router(conversations.router, prefix="/api", tags=["conversations"])
    app.include_router(messages.router, prefix="/api", tags=["messages"])
    app.include_router(agents.router, prefix="/api", tags=["agents"])
    app.include_router(workspaces.router, prefix="/api", tags=["workspaces"])

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "agenthub"}

    return app


app = create_app()
