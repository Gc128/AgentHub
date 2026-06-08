from typing import Annotated
from urllib.parse import urlparse

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from agenthub.api.deps import get_agent_service
from agenthub.config import get_settings
from agenthub.schemas.agent import Agent, AgentRunInput, AgentRunResult, AgentRuntimeInfo
from agenthub.services.agent_service import AgentService

router = APIRouter()


@router.get("/agents", response_model=list[Agent])
async def list_agents(
    service: Annotated[AgentService, Depends(get_agent_service)],
) -> list[Agent]:
    return service.list_agents()


@router.get("/agents/runtime", response_model=AgentRuntimeInfo)
async def agent_runtime_info() -> AgentRuntimeInfo:
    settings = get_settings()
    parsed = urlparse(settings.agent_base_url)
    return AgentRuntimeInfo(
        agent_mode="mock" if settings.use_mock_agents else "real",
        provider=settings.agent_provider,
        model=settings.agent_model,
        base_url_host=parsed.netloc or settings.agent_base_url,
        api_key_configured=bool(settings.openai_api_key),
    )


@router.post("/agents/run", response_model=AgentRunResult)
async def run_agent(
    input_data: AgentRunInput,
    service: Annotated[AgentService, Depends(get_agent_service)],
) -> AgentRunResult:
    return await service.run(input_data)


@router.post("/agents/stream")
async def stream_agent(
    input_data: AgentRunInput,
    service: Annotated[AgentService, Depends(get_agent_service)],
) -> StreamingResponse:
    return StreamingResponse(service.stream(input_data), media_type="text/event-stream")
