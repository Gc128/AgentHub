from typing import Annotated
from urllib.parse import urlparse

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from agenthub.api.deps import get_agent_service
from agenthub.config import get_settings
from agenthub.schemas.agent import (
    Agent,
    AgentBackend,
    AgentRunInput,
    AgentRunResult,
    AgentRuntimeInfo,
)
from agenthub.schemas.custom_agent import (
    CustomAgent,
    CustomAgentCreate,
    CustomAgentDeleteResult,
    CustomAgentTestRequest,
    CustomAgentUpdate,
)
from agenthub.services.agent_service import AgentService

router = APIRouter()


@router.get("/agents", response_model=list[Agent])
async def list_agents(
    service: Annotated[AgentService, Depends(get_agent_service)],
) -> list[Agent]:
    return await service.list_agents()


@router.get("/agents/custom", response_model=list[CustomAgent])
async def list_custom_agents(
    service: Annotated[AgentService, Depends(get_agent_service)],
) -> list[CustomAgent]:
    return await service.list_custom_agents()


@router.get("/agents/backends", response_model=list[AgentBackend])
async def list_agent_backends(
    service: Annotated[AgentService, Depends(get_agent_service)],
) -> list[AgentBackend]:
    return await service.list_agent_backends()


@router.post("/agents/custom", response_model=CustomAgent, status_code=201)
async def create_custom_agent(
    request: CustomAgentCreate,
    service: Annotated[AgentService, Depends(get_agent_service)],
) -> CustomAgent:
    return await service.create_custom_agent(request)


@router.patch("/agents/custom/{agent_id}", response_model=CustomAgent)
async def update_custom_agent(
    agent_id: str,
    request: CustomAgentUpdate,
    service: Annotated[AgentService, Depends(get_agent_service)],
) -> CustomAgent:
    return await service.update_custom_agent(agent_id, request)


@router.delete("/agents/custom/{agent_id}", response_model=CustomAgentDeleteResult)
async def delete_custom_agent(
    agent_id: str,
    service: Annotated[AgentService, Depends(get_agent_service)],
) -> CustomAgentDeleteResult:
    await service.delete_custom_agent(agent_id)
    return CustomAgentDeleteResult(id=agent_id, deleted=True)


@router.post("/agents/custom/{agent_id}/test", response_model=AgentRunResult)
async def test_custom_agent(
    agent_id: str,
    request: CustomAgentTestRequest,
    service: Annotated[AgentService, Depends(get_agent_service)],
) -> AgentRunResult:
    return await service.test_custom_agent(agent_id, request.message)


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
