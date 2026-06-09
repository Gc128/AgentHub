import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from agenthub.core.errors import BadRequestError
from agenthub.repositories.conversation_repo import ConversationRepository
from agenthub.repositories.message_repo import MessageRepository
from agenthub.schemas.agent import AgentRunInput, AgentRunResult
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
        if request.reply_to_id is not None:
            await self._message_repository.get(conversation_id, request.reply_to_id)
        now = datetime.now(UTC)
        message = Message(
            id=new_id("msg"),
            conversation_id=conversation_id,
            role="user" if request.sender_id == "user" else "agent",
            sender_id=request.sender_id,
            content=request.content,
            artifacts=request.artifacts,
            reply_to_id=request.reply_to_id,
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
                    history=_active_history(history),
                    context=await self._build_context(
                        conversation_id,
                        reply_to_id=request.reply_to_id,
                    ),
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

    async def stream_message(
        self,
        conversation_id: str,
        request: MessageCreate,
    ) -> AsyncIterator[str]:
        conversation = await self._conversation_repository.get(conversation_id)
        user_message = await self.create_message(
            conversation_id,
            request.model_copy(update={"sender_id": "user", "artifacts": []}),
        )
        yield _format_sse("user_message", {"message": user_message.model_dump(mode="json")})

        if not request.run_agent:
            yield _format_sse("done", {"agent_messages": []})
            return

        history = await self._message_repository.list_by_conversation(conversation_id)
        agent_messages: list[Message] = []
        stream_input = AgentRunInput(
            conversation_id=conversation_id,
            workspace_id=conversation.workspace_id,
            user_message=request.content,
            history=_active_history(history),
            context=await self._build_context(
                conversation_id,
                reply_to_id=request.reply_to_id,
            ),
        )
        async for event, data in self._agent_service.stream_for_message(stream_input):
            if event == "agent_done":
                result_payload = data.get("result")
                if isinstance(result_payload, dict):
                    agent_result = self._agent_result_from_payload(result_payload)
                    agent_message = Message(
                        id=new_id("msg"),
                        conversation_id=conversation_id,
                        role="agent",
                        sender_id=agent_result.agent_id,
                        content=agent_result.content,
                        artifacts=agent_result.artifacts,
                        created_at=datetime.now(UTC),
                    )
                    await self._message_repository.save(agent_message)
                    agent_messages.append(agent_message)
                    yield _format_sse(
                        "agent_done",
                        {
                            "message": agent_message.model_dump(mode="json"),
                            "result": agent_result.model_dump(mode="json"),
                        },
                    )
                    continue
            yield _format_sse(event, data)

        updated = conversation.model_copy(update={"updated_at": datetime.now(UTC)})
        await self._conversation_repository.save(updated)
        yield _format_sse(
            "done",
            {"agent_messages": [message.model_dump(mode="json") for message in agent_messages]},
        )

    async def soft_delete_message(self, conversation_id: str, message_id: str) -> Message:
        conversation = await self._conversation_repository.get(conversation_id)
        message = await self._message_repository.get(conversation_id, message_id)
        deleted_message = message.model_copy(
            update={
                "content": "消息已删除",
                "artifacts": [],
                "is_context_pinned": False,
                "deleted_at": datetime.now(UTC),
            }
        )
        await self._message_repository.save(deleted_message)
        await self._conversation_repository.save(
            conversation.model_copy(update={"updated_at": datetime.now(UTC)})
        )
        return deleted_message

    async def set_message_context_pin(
        self,
        conversation_id: str,
        message_id: str,
        pinned: bool,
    ) -> Message:
        conversation = await self._conversation_repository.get(conversation_id)
        message = await self._message_repository.get(conversation_id, message_id)
        if message.deleted_at is not None:
            raise BadRequestError(
                "message_deleted",
                "Deleted messages cannot be pinned into long-term context.",
            )
        pinned_message = message.model_copy(update={"is_context_pinned": pinned})
        await self._message_repository.save(pinned_message)
        await self._conversation_repository.save(
            conversation.model_copy(update={"updated_at": datetime.now(UTC)})
        )
        return pinned_message

    async def stream_regenerated_message(
        self,
        conversation_id: str,
        message_id: str,
    ) -> AsyncIterator[str]:
        conversation = await self._conversation_repository.get(conversation_id)
        target_message = await self._message_repository.get(conversation_id, message_id)
        if target_message.role != "user":
            raise BadRequestError(
                "regenerate_requires_user_message",
                "Only user messages can be regenerated.",
            )
        if target_message.deleted_at is not None:
            raise BadRequestError(
                "message_deleted",
                "Deleted messages cannot be regenerated.",
            )

        history = await self._message_repository.list_by_conversation(conversation_id)
        history_before_target = _messages_before(history, message_id)
        agent_messages: list[Message] = []
        stream_input = AgentRunInput(
            conversation_id=conversation_id,
            workspace_id=conversation.workspace_id,
            user_message=target_message.content,
            history=_active_history(history_before_target),
            context=await self._build_context(conversation_id),
        )
        yield _format_sse(
            "harness_step",
            {
                "status": "started",
                "message": "正在基于这条用户消息重新生成回复",
            },
        )
        async for event, data in self._agent_service.stream_for_message(stream_input):
            if event == "agent_done":
                result_payload = data.get("result")
                if isinstance(result_payload, dict):
                    agent_result = self._agent_result_from_payload(result_payload)
                    agent_message = Message(
                        id=new_id("msg"),
                        conversation_id=conversation_id,
                        role="agent",
                        sender_id=agent_result.agent_id,
                        content=agent_result.content,
                        artifacts=agent_result.artifacts,
                        regenerated_from_id=target_message.id,
                        created_at=datetime.now(UTC),
                    )
                    await self._message_repository.save(agent_message)
                    agent_messages.append(agent_message)
                    yield _format_sse(
                        "agent_done",
                        {
                            "message": agent_message.model_dump(mode="json"),
                            "result": agent_result.model_dump(mode="json"),
                        },
                    )
                    continue
            yield _format_sse(event, data)

        updated = conversation.model_copy(update={"updated_at": datetime.now(UTC)})
        await self._conversation_repository.save(updated)
        yield _format_sse(
            "done",
            {"agent_messages": [message.model_dump(mode="json") for message in agent_messages]},
        )

    async def delete_messages_for_conversation(self, conversation_id: str) -> None:
        await self._message_repository.delete_by_conversation(conversation_id)

    def _agent_result_from_payload(self, payload: dict[str, object]) -> AgentRunResult:
        return AgentRunResult.model_validate(payload)

    async def _build_context(
        self,
        conversation_id: str,
        reply_to_id: str | None = None,
    ) -> dict[str, object]:
        pinned_messages = await self._message_repository.list_pinned_by_conversation(
            conversation_id
        )
        context: dict[str, object] = {
            "pinned_messages": [message.model_dump(mode="json") for message in pinned_messages]
        }
        if reply_to_id is not None:
            context["reply_to_id"] = reply_to_id
        return context


def _active_history(messages: list[Message]) -> list[Message]:
    return [message for message in messages if message.deleted_at is None]


def _messages_before(messages: list[Message], message_id: str) -> list[Message]:
    for index, message in enumerate(messages):
        if message.id == message_id:
            return messages[:index]
    return messages


def _format_sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
