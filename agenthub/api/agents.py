from fastapi import APIRouter

from agenthub.agents.mock_agent import MockAgent
from agenthub.schemas.agent import AgentRunInput, AgentRunResult

router = APIRouter()


@router.post("/agents/run", response_model=AgentRunResult)
async def run_agent(input_data: AgentRunInput) -> AgentRunResult:
    agent = MockAgent(agent_id=input_data.context.get("agent_id", "mock-agent"))
    return await agent.run(input_data)
