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
