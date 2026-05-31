from agenthub.schemas.agent import AgentRunInput, AgentRunResult


class RealAgentUnavailableError(RuntimeError):
    pass


class RealAgent:
    id = "real-agent"
    name = "Real Agent"
    capabilities = ["external-agent"]

    async def run(self, input_data: AgentRunInput) -> AgentRunResult:
        raise RealAgentUnavailableError("Real agent integration is not configured yet.")
