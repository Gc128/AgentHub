from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from agenthub.agents.real_agent import RealAgent, RealAgentUnavailableError
from agenthub.core.errors import BadRequestError
from agenthub.repositories.memory_repo import MemorySummaryRepository
from agenthub.schemas.agent import AgentRunInput
from agenthub.schemas.memory import (
    ConversationMemorySummary,
    MemorySummaryRecordSchema,
)
from agenthub.schemas.message import Message
from agenthub.services.change_set_service import ChangeSetService
from agenthub.services.workspace_service import WorkspaceService


@dataclass(frozen=True)
class PreparedMemoryContext:
    history: list[Message]
    context: dict[str, object]


class MemoryContextService:
    def __init__(
        self,
        repository: MemorySummaryRepository,
        summarizer: RealAgent | None,
        workspace_service: WorkspaceService | None = None,
        change_set_service: ChangeSetService | None = None,
        *,
        context_token_budget: int = 120000,
        pinned_token_budget: int = 3000,
        short_term_context_messages: int = 20,
        summary_trigger_tokens: int = 6000,
        summary_trigger_messages: int = 20,
    ) -> None:
        self._repository = repository
        self._summarizer = summarizer
        self._workspace_service = workspace_service
        self._change_set_service = change_set_service
        self._context_token_budget = context_token_budget
        self._pinned_token_budget = pinned_token_budget
        self._short_term_context_messages = short_term_context_messages
        self._summary_trigger_tokens = summary_trigger_tokens
        self._summary_trigger_messages = summary_trigger_messages

    async def prepare(
        self,
        *,
        conversation_id: str,
        workspace_id: str,
        user_message: str,
        messages: list[Message],
        pinned_messages: list[Message],
    ) -> PreparedMemoryContext:
        active = [message for message in messages if message.deleted_at is None]
        if active and active[-1].role == "user":
            if active[-1].content.strip() == user_message.strip():
                active = active[:-1]
        summary_record = await self._repository.get(conversation_id)
        unsummarized = _messages_after_summary(active, summary_record)
        warning = ""
        token_triggered = _estimate_messages_tokens(unsummarized) >= self._summary_trigger_tokens
        should_summarize = len(unsummarized) >= self._summary_trigger_messages or token_triggered
        if should_summarize and self._summarizer is not None and unsummarized:
            try:
                summary_record = await self._summarize(
                    conversation_id=conversation_id,
                    workspace_id=workspace_id,
                    messages=unsummarized,
                    previous_summary=summary_record,
                )
            except RealAgentUnavailableError as exc:
                warning = f"Memory summary update failed: {exc}"
        elif should_summarize and self._summarizer is None:
            warning = (
                "Memory summarizer is not configured; messages outside the short-term "
                "window are not represented by a long-term summary."
            )

        selected_pinned = _fit_messages(pinned_messages, self._pinned_token_budget)
        if len(selected_pinned) != len(pinned_messages):
            raise BadRequestError(
                "memory_context_overflow",
                "Pinned messages exceed PINNED_CONTEXT_TOKEN_BUDGET. Unpin or shorten context.",
            )

        pinned_ids = {message.id for message in selected_pinned}
        recent_candidates = [message for message in active if message.id not in pinned_ids]
        omitted_recent_count = max(
            len(recent_candidates) - self._short_term_context_messages,
            0,
        )
        recent_candidates = recent_candidates[-self._short_term_context_messages :]
        reserved = _estimate_messages_tokens(selected_pinned) + _estimate_text_tokens(user_message)
        if summary_record is not None:
            reserved += _estimate_text_tokens(summary_record.summary.model_dump_json())
        available = max(self._context_token_budget - reserved, 0)
        selected_recent = _fit_messages_from_newest(recent_candidates, available)
        if len(selected_recent) != len(recent_candidates):
            raise BadRequestError(
                "memory_context_overflow",
                "The latest short-term messages exceed AGENT_CONTEXT_TOKEN_BUDGET. "
                "Increase the budget, shorten messages, or reduce "
                "SHORT_TERM_CONTEXT_MESSAGES.",
            )

        context: dict[str, object] = {
            "pinned_messages": [message.model_dump(mode="json") for message in selected_pinned],
            "memory_summary": summary_record.summary.model_dump(mode="json")
            if summary_record is not None
            else None,
        }
        if self._workspace_service is not None:
            files = await self._workspace_service.list_files(workspace_id)
            context["workspace_summary"] = {
                "workspace_id": workspace_id,
                "files": [file.path for file in files],
            }
        if self._change_set_service is not None:
            change_sets = await self._change_set_service.list(workspace_id)
            context["active_change_sets"] = [
                {
                    "id": item.id,
                    "status": item.status,
                    "repair_count": item.repair_count,
                    "entry_path": item.entry_path,
                }
                for item in change_sets
                if item.status not in {"promoted", "rejected"}
            ]
        if warning:
            context["memory_warning"] = warning
        if omitted_recent_count:
            context["short_term_context_omitted_messages"] = omitted_recent_count
        return PreparedMemoryContext(history=selected_recent, context=context)

    async def _summarize(
        self,
        *,
        conversation_id: str,
        workspace_id: str,
        messages: list[Message],
        previous_summary: MemorySummaryRecordSchema | None,
    ) -> MemorySummaryRecordSchema:
        if self._summarizer is None or not messages:
            raise RealAgentUnavailableError("Memory summarizer is not configured.")
        payload = [
            {
                "role": message.role,
                "sender_id": message.sender_id,
                "content": message.content,
                "status": message.status,
            }
            for message in messages
        ]
        summary = await self._summarizer.run_structured(
            AgentRunInput(
                conversation_id=conversation_id,
                workspace_id=workspace_id,
                user_message=json.dumps(payload, ensure_ascii=False),
                history=[],
                context={
                    "summary_scope": "conversation",
                    "previous_summary": (
                        previous_summary.summary.model_dump(mode="json")
                        if previous_summary is not None
                        else None
                    ),
                },
            ),
            ConversationMemorySummary,
            schema_name="ConversationMemorySummary",
        )
        record = MemorySummaryRecordSchema(
            conversation_id=conversation_id,
            up_to_message_id=messages[-1].id,
            summary=summary,
            status="ready",
            updated_at=datetime.now(UTC),
        )
        return await self._repository.save(record)


def _messages_after_summary(
    messages: list[Message], summary: MemorySummaryRecordSchema | None
) -> list[Message]:
    if summary is None:
        return messages
    for index, message in enumerate(messages):
        if message.id == summary.up_to_message_id:
            return messages[index + 1 :]
    return messages


def _estimate_text_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


def _estimate_messages_tokens(messages: list[Message]) -> int:
    return sum(_estimate_text_tokens(message.content) + 12 for message in messages)


def _fit_messages(messages: list[Message], budget: int) -> list[Message]:
    selected: list[Message] = []
    used = 0
    for message in messages:
        cost = _estimate_text_tokens(message.content) + 12
        if used + cost > budget:
            break
        selected.append(message)
        used += cost
    return selected


def _fit_messages_from_newest(messages: list[Message], budget: int) -> list[Message]:
    selected: list[Message] = []
    used = 0
    for message in reversed(messages):
        cost = _estimate_text_tokens(message.content) + 12
        if used + cost > budget:
            break
        selected.append(message)
        used += cost
    return list(reversed(selected))


MEMORY_SUMMARIZER_SYSTEM_PROMPT = """
You summarize one AgentHub conversation for future agent turns.
Return exactly one ConversationMemorySummary JSON object with these arrays:
facts, requirements, decisions, open_questions, promoted_changes.
Merge context.previous_summary with the newly supplied messages. Preserve still-valid
facts, requirements, decisions, open questions, and promoted changes from that summary.
Only include promoted workspace changes as promoted_changes. Do not treat failed,
rejected, staged, or merely generated candidates as accepted facts.
Do not invent user identity, requirements, decisions, or implementation status.
""".strip()
