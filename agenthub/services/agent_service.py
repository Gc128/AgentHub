from agenthub.agents.mock_agent import MockAgent
from agenthub.schemas.agent import AgentRunInput, AgentRunResult


class AgentService:
    async def run(self, input_data: AgentRunInput) -> AgentRunResult:
        agent = MockAgent(agent_id=input_data.context.get("agent_id", "mock-agent"))
        return await agent.run(input_data)
