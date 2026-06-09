from typing import Literal

from agenthub.core.errors import NotFoundError
from agenthub.schemas.conversation import Conversation

ConversationStatusFilter = Literal["active", "archived", "all"]


class ConversationRepository:
    def __init__(self) -> None:
        self._conversations: dict[str, Conversation] = {}

    async def list(self, status: ConversationStatusFilter = "active") -> list[Conversation]:
        conversations = list(self._conversations.values())
        if status != "all":
            conversations = [
                conversation for conversation in conversations if conversation.status == status
            ]
        return sorted(conversations, key=lambda item: item.updated_at, reverse=True)

    async def get(self, conversation_id: str) -> Conversation:
        conversation = self._conversations.get(conversation_id)
        if conversation is None:
            raise NotFoundError("conversation_not_found", "Conversation does not exist.")
        return conversation

    async def save(self, conversation: Conversation) -> Conversation:
        self._conversations[conversation.id] = conversation
        return conversation

    async def delete(self, conversation_id: str) -> None:
        await self.get(conversation_id)
        del self._conversations[conversation_id]

    async def exists(self, conversation_id: str) -> bool:
        return conversation_id in self._conversations
