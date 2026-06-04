from functools import lru_cache

from agenthub.agents.registry import AgentRegistry, create_default_registry
from agenthub.config import get_settings
from agenthub.repositories.conversation_repo import ConversationRepository
from agenthub.repositories.message_repo import MessageRepository
from agenthub.repositories.sqlite import (
    SqliteConversationRepository,
    SqliteMessageRepository,
    SqliteWorkspaceRepository,
)
from agenthub.repositories.workspace_repo import WorkspaceRepository
from agenthub.services.agent_service import AgentService
from agenthub.services.conversation_service import ConversationService
from agenthub.services.message_service import MessageService
from agenthub.services.workspace_service import WorkspaceService


@lru_cache
def get_conversation_repository() -> ConversationRepository:
    settings = get_settings()
    if settings.persistence_backend == "sqlite":
        return SqliteConversationRepository(settings.database_url)
    return ConversationRepository()


@lru_cache
def get_message_repository() -> MessageRepository:
    settings = get_settings()
    if settings.persistence_backend == "sqlite":
        return SqliteMessageRepository(settings.database_url)
    return MessageRepository()


@lru_cache
def get_workspace_repository() -> WorkspaceRepository:
    settings = get_settings()
    if settings.persistence_backend == "sqlite":
        return SqliteWorkspaceRepository(settings.database_url)
    return WorkspaceRepository()


@lru_cache
def get_agent_registry() -> AgentRegistry:
    return create_default_registry(settings=get_settings())


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


def get_workspace_service() -> WorkspaceService:
    settings = get_settings()
    return WorkspaceService(
        repository=get_workspace_repository(),
        workspace_root=settings.workspace_root,
    )


def reset_dependency_caches() -> None:
    get_conversation_repository.cache_clear()
    get_message_repository.cache_clear()
    get_workspace_repository.cache_clear()
    get_agent_registry.cache_clear()
