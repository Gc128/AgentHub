from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from agenthub.api.deps import get_agent_service
from agenthub.schemas.agent import Agent, AgentRunInput, AgentRunResult
from agenthub.services.agent_service import AgentService

router = APIRouter()


@router.get("/agents", response_model=list[Agent])
async def list_agents(
    service: Annotated[AgentService, Depends(get_agent_service)],
) -> list[Agent]:
    return service.list_agents()


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
