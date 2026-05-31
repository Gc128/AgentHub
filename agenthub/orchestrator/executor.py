from agenthub.agents.code_agent import CodeAgent
from agenthub.agents.mock_agent import MockAgent
from agenthub.agents.review_agent import ReviewAgent
from agenthub.schemas.agent import AgentRunInput, AgentRunResult


def get_mock_adapter(agent_id: str) -> MockAgent:
    if agent_id == "code-agent":
        return CodeAgent()
    if agent_id == "review-agent":
        return ReviewAgent()
    return MockAgent(agent_id=agent_id)


async def execute_agent(agent_id: str, input_data: AgentRunInput) -> AgentRunResult:
    return await get_mock_adapter(agent_id).run(input_data)
