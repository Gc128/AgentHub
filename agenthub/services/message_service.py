from datetime import UTC, datetime

from agenthub.repositories.conversation_repo import ConversationRepository
from agenthub.repositories.message_repo import MessageRepository
from agenthub.schemas.agent import AgentRunInput
from agenthub.schemas.message import Message, MessageCreate, MessageSendResponse
from agenthub.services.agent_service import AgentService
from agenthub.utils.ids import new_id


class MessageService:
    def __init__(
        self,
        conversation_repository: ConversationRepository,
        message_repository: MessageRepository,
        agent_service: AgentService,
    ) -> None:
        self._conversation_repository = conversation_repository
        self._message_repository = message_repository
        self._agent_service = agent_service

    async def list_messages(self, conversation_id: str) -> list[Message]:
        await self._conversation_repository.get(conversation_id)
        return await self._message_repository.list_by_conversation(conversation_id)

    async def create_message(
        self,
        conversation_id: str,
        request: MessageCreate,
    ) -> Message:
        conversation = await self._conversation_repository.get(conversation_id)
        now = datetime.now(UTC)
        message = Message(
            id=new_id("msg"),
            conversation_id=conversation_id,
            role="user" if request.sender_id == "user" else "agent",
            sender_id=request.sender_id,
            content=request.content,
            artifacts=request.artifacts,
            created_at=now,
        )
        await self._message_repository.save(message)
        updated = conversation.model_copy(update={"updated_at": now})
        await self._conversation_repository.save(updated)
        return message

    async def send_message(
        self,
        conversation_id: str,
        request: MessageCreate,
    ) -> MessageSendResponse:
        conversation = await self._conversation_repository.get(conversation_id)
        user_message = await self.create_message(
            conversation_id,
            request.model_copy(update={"sender_id": "user", "artifacts": []}),
        )

        agent_messages: list[Message] = []
        if request.run_agent:
            history = await self._message_repository.list_by_conversation(conversation_id)
            results = await self._agent_service.run_for_message(
                AgentRunInput(
                    conversation_id=conversation_id,
                    workspace_id=conversation.workspace_id,
                    user_message=request.content,
                    history=history,
                )
            )
            for result in results:
                agent_message = Message(
                    id=new_id("msg"),
                    conversation_id=conversation_id,
                    role="agent",
                    sender_id=result.agent_id,
                    content=result.content,
                    artifacts=result.artifacts,
                    created_at=datetime.now(UTC),
                )
                await self._message_repository.save(agent_message)
                agent_messages.append(agent_message)

        updated = conversation.model_copy(update={"updated_at": datetime.now(UTC)})
        await self._conversation_repository.save(updated)
        return MessageSendResponse(user_message=user_message, agent_messages=agent_messages)

    async def delete_messages_for_conversation(self, conversation_id: str) -> None:
        await self._message_repository.delete_by_conversation(conversation_id)
