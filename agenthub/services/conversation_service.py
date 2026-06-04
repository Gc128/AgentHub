from datetime import UTC, datetime

from agenthub.repositories.conversation_repo import ConversationRepository
from agenthub.schemas.conversation import Conversation, ConversationCreate, ConversationUpdate
from agenthub.utils.ids import new_id


class ConversationService:
    def __init__(self, repository: ConversationRepository) -> None:
        self._repository = repository

    async def list_conversations(self) -> list[Conversation]:
        return await self._repository.list()

    async def create_conversation(self, request: ConversationCreate) -> Conversation:
        conversation_id = new_id("conv")
        workspace_id = request.workspace_id or f"ws_{conversation_id}"
        now = datetime.now(UTC)
        conversation = Conversation(
            id=conversation_id,
            title=request.title,
            mode=request.mode,
            agent_ids=request.agent_ids,
            workspace_id=workspace_id,
            created_at=now,
            updated_at=now,
        )
        return await self._repository.save(conversation)

    async def get_conversation(self, conversation_id: str) -> Conversation:
        return await self._repository.get(conversation_id)

    async def update_conversation(
        self,
        conversation_id: str,
        request: ConversationUpdate,
    ) -> Conversation:
        conversation = await self._repository.get(conversation_id)
        updated = conversation.model_copy(
            update={
                "title": request.title if request.title is not None else conversation.title,
                "agent_ids": request.agent_ids
                if request.agent_ids is not None
                else conversation.agent_ids,
                "updated_at": datetime.now(UTC),
            }
        )
        return await self._repository.save(updated)
