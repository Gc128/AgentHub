from agenthub.schemas.message import Message


class MessageRepository:
    def __init__(self) -> None:
        self._messages: dict[str, list[Message]] = {}

    async def list_by_conversation(self, conversation_id: str) -> list[Message]:
        return list(self._messages.get(conversation_id, []))

    async def save(self, message: Message) -> Message:
        messages = self._messages.setdefault(message.conversation_id, [])
        messages.append(message)
        return message

    async def delete_by_conversation(self, conversation_id: str) -> None:
        self._messages.pop(conversation_id, None)
