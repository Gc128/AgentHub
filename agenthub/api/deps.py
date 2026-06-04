from functools import lru_cache

from agenthub.agents.registry import AgentRegistry, create_default_registry
from agenthub.repositories.conversation_repo import ConversationRepository
from agenthub.repositories.message_repo import MessageRepository
from agenthub.services.agent_service import AgentService
from agenthub.services.conversation_service import ConversationService
from agenthub.services.message_service import MessageService


@lru_cache
def get_conversation_repository() -> ConversationRepository:
    return ConversationRepository()


@lru_cache
def get_message_repository() -> MessageRepository:
    return MessageRepository()


@lru_cache
def get_agent_registry() -> AgentRegistry:
    return create_default_registry()


def get_conversation_service() -> ConversationService:
    return ConversationService(repository=get_conversation_repository())


def get_agent_service() -> AgentService:
    return AgentService(registry=get_agent_registry())


def get_message_service() -> MessageService:
    return MessageService(
        conversation_repository=get_conversation_repository(),
        message_repository=get_message_repository(),
        agent_service=get_agent_service(),
    )


def reset_dependency_caches() -> None:
    get_conversation_repository.cache_clear()
    get_message_repository.cache_clear()
    get_agent_registry.cache_clear()
