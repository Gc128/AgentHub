from functools import lru_cache

from agenthub.agents.langchain_agent import LangChainAgent
from agenthub.agents.registry import AgentRegistry, create_default_registry
from agenthub.config import get_settings
from agenthub.repositories.change_set_repo import ChangeSetRepository
from agenthub.repositories.conversation_repo import ConversationRepository
from agenthub.repositories.custom_agent_repo import CustomAgentRepository
from agenthub.repositories.memory_repo import MemorySummaryRepository
from agenthub.repositories.message_repo import MessageRepository
from agenthub.repositories.sqlite import (
    SqliteChangeSetRepository,
    SqliteConversationRepository,
    SqliteCustomAgentRepository,
    SqliteMemorySummaryRepository,
    SqliteMessageRepository,
    SqliteWorkspaceRepository,
)
from agenthub.repositories.workspace_repo import WorkspaceRepository
from agenthub.services.agent_service import AgentService
from agenthub.services.change_set_service import ChangeSetService
from agenthub.services.conversation_service import ConversationService
from agenthub.services.memory_service import MEMORY_SUMMARIZER_SYSTEM_PROMPT, MemoryContextService
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
def get_custom_agent_repository() -> CustomAgentRepository:
    settings = get_settings()
    if settings.persistence_backend == "sqlite":
        return SqliteCustomAgentRepository(settings.database_url)
    return CustomAgentRepository()


@lru_cache
def get_workspace_repository() -> WorkspaceRepository:
    settings = get_settings()
    if settings.persistence_backend == "sqlite":
        return SqliteWorkspaceRepository(settings.database_url)
    return WorkspaceRepository()


@lru_cache
def get_change_set_repository() -> ChangeSetRepository:
    settings = get_settings()
    if settings.persistence_backend == "sqlite":
        return SqliteChangeSetRepository(settings.database_url)
    return ChangeSetRepository()


@lru_cache
def get_memory_summary_repository() -> MemorySummaryRepository:
    settings = get_settings()
    if settings.persistence_backend == "sqlite":
        return SqliteMemorySummaryRepository(settings.database_url)
    return MemorySummaryRepository()


@lru_cache
def get_agent_registry() -> AgentRegistry:
    return create_default_registry(settings=get_settings())


def get_conversation_service() -> ConversationService:
    return ConversationService(repository=get_conversation_repository())


def get_agent_service() -> AgentService:
    return AgentService(
        registry=get_agent_registry(),
        custom_agent_repository=get_custom_agent_repository(),
        settings=get_settings(),
        change_set_service=get_change_set_service(),
    )


def get_message_service() -> MessageService:
    return MessageService(
        conversation_repository=get_conversation_repository(),
        message_repository=get_message_repository(),
        agent_service=get_agent_service(),
        memory_context_service=get_memory_context_service(),
    )


def get_workspace_service() -> WorkspaceService:
    settings = get_settings()
    return WorkspaceService(
        repository=get_workspace_repository(),
        workspace_root=settings.workspace_root,
    )


def get_change_set_service() -> ChangeSetService:
    settings = get_settings()
    return ChangeSetService(
        repository=get_change_set_repository(),
        workspace_repository=get_workspace_repository(),
        workspace_service=get_workspace_service(),
        workspace_root=settings.workspace_root,
        staging_root=settings.staging_root,
        preview_artifact_root=settings.preview_artifact_root,
        staging_ttl_hours=settings.preview_staging_ttl_hours,
        preview_artifact_ttl_hours=settings.preview_artifact_ttl_hours,
    )


def get_memory_context_service() -> MemoryContextService:
    settings = get_settings()
    summarizer = None
    if not settings.use_mock_agents and settings.openai_api_key:
        summarizer = LangChainAgent(
            agent_id="memory-summarizer",
            provider=settings.agent_provider,
            model=settings.agent_model,
            api_key=settings.openai_api_key,
            base_url=settings.agent_base_url,
            timeout_seconds=settings.agent_request_timeout_seconds,
            response_format=settings.agent_response_format,
            thinking=settings.agent_thinking,
            max_tokens=settings.agent_max_tokens,
            system_prompt=MEMORY_SUMMARIZER_SYSTEM_PROMPT,
        )
    return MemoryContextService(
        get_memory_summary_repository(),
        summarizer,
        workspace_service=get_workspace_service(),
        change_set_service=get_change_set_service(),
        context_token_budget=settings.agent_context_token_budget,
        pinned_token_budget=settings.pinned_context_token_budget,
        short_term_context_messages=settings.short_term_context_messages,
        summary_trigger_tokens=settings.memory_summary_trigger_tokens,
        summary_trigger_messages=settings.memory_summary_trigger_messages,
    )


def reset_dependency_caches() -> None:
    get_conversation_repository.cache_clear()
    get_message_repository.cache_clear()
    get_custom_agent_repository.cache_clear()
    get_workspace_repository.cache_clear()
    get_change_set_repository.cache_clear()
    get_memory_summary_repository.cache_clear()
    get_agent_registry.cache_clear()
