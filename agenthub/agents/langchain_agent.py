from agenthub.agents.real_agent import (
    ChatModelFactory,
    LangChainChatModel,
    RealAgent,
    RealAgentConfigurationError,
    RealAgentSchemaError,
    RealAgentTransportError,
    RealAgentUnavailableError,
)


class LangChainAgent(RealAgent):
    """LangChain-backed real Agent adapter."""


__all__ = [
    "ChatModelFactory",
    "LangChainAgent",
    "LangChainChatModel",
    "RealAgentConfigurationError",
    "RealAgentSchemaError",
    "RealAgentTransportError",
    "RealAgentUnavailableError",
]
