from agenthub.schemas.message import Message


class MessageService:
    async def list_messages(self, conversation_id: str) -> list[Message]:
        return []
