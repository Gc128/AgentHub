from agenthub.core.errors import NotFoundError
from agenthub.schemas.message import Message


class MessageRepository:
    def __init__(self) -> None:
        self._messages: dict[str, list[Message]] = {}

    async def list_by_conversation(self, conversation_id: str) -> list[Message]:
        return list(self._messages.get(conversation_id, []))

    async def list_pinned_by_conversation(self, conversation_id: str) -> list[Message]:
        return [
            message
            for message in self._messages.get(conversation_id, [])
            if message.is_context_pinned and message.deleted_at is None
        ]

    async def get(self, conversation_id: str, message_id: str) -> Message:
        for message in self._messages.get(conversation_id, []):
            if message.id == message_id:
                return message
        raise NotFoundError("message_not_found", "Message does not exist.")

    async def save(self, message: Message) -> Message:
        messages = self._messages.setdefault(message.conversation_id, [])
        for index, existing_message in enumerate(messages):
            if existing_message.id == message.id:
                messages[index] = message
                return message
        messages.append(message)
        return message

    async def delete_by_conversation(self, conversation_id: str) -> None:
        self._messages.pop(conversation_id, None)
