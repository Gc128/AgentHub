from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest

from agenthub.agents.real_agent import RealAgent
from agenthub.core.errors import BadRequestError
from agenthub.repositories.memory_repo import MemorySummaryRepository
from agenthub.schemas.agent import AgentRunInput
from agenthub.schemas.memory import ConversationMemorySummary, MemorySummaryRecordSchema
from agenthub.schemas.message import Message
from agenthub.services.memory_service import MemoryContextService


class RecordingSummarizer:
    def __init__(self) -> None:
        self.inputs: list[AgentRunInput] = []

    async def run_structured(
        self,
        input_data: AgentRunInput,
        schema: type[ConversationMemorySummary],
        *,
        schema_name: str,
    ) -> ConversationMemorySummary:
        del schema, schema_name
        self.inputs.append(input_data)
        return ConversationMemorySummary(facts=["Earlier messages were summarized."])


def message(message_id: str, content: str, *, pinned: bool = False) -> Message:
    return Message(
        id=message_id,
        conversation_id="conv-1",
        role="user",
        sender_id="user",
        content=content,
        is_context_pinned=pinned,
        created_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_memory_keeps_pins_summary_and_recent_messages() -> None:
    repository = MemorySummaryRepository()
    await repository.save(
        MemorySummaryRecordSchema(
            conversation_id="conv-1",
            up_to_message_id="m1",
            summary=ConversationMemorySummary(
                requirements=["Use a trusted browser preview."],
                promoted_changes=["Promoted index.html."],
            ),
        )
    )
    pinned = message("pin-1", "Never use model supplied preview URLs.", pinned=True)
    old = message("m1", "old")
    recent = message("m2", "Add a conflict check before promote.")
    service = MemoryContextService(repository, None)

    prepared = await service.prepare(
        conversation_id="conv-1",
        workspace_id="ws-1",
        user_message="Continue",
        messages=[old, recent],
        pinned_messages=[pinned],
    )

    assert prepared.history == [old, recent]
    assert prepared.context["pinned_messages"]
    assert prepared.context["memory_summary"] == {
        "facts": [],
        "requirements": ["Use a trusted browser preview."],
        "decisions": [],
        "open_questions": [],
        "promoted_changes": ["Promoted index.html."],
    }


@pytest.mark.asyncio
async def test_memory_limits_short_term_context_to_latest_20_messages() -> None:
    service = MemoryContextService(MemorySummaryRepository(), None)
    messages = [message(f"m{index}", f"message-{index}") for index in range(25)]

    prepared = await service.prepare(
        conversation_id="conv-1",
        workspace_id="ws-1",
        user_message="continue",
        messages=messages,
        pinned_messages=[],
    )

    assert [item.id for item in prepared.history] == [f"m{index}" for index in range(5, 25)]
    assert prepared.context["short_term_context_omitted_messages"] == 5


@pytest.mark.asyncio
async def test_memory_keeps_latest_20_while_summarizing_every_20_new_messages() -> None:
    repository = MemorySummaryRepository()
    summarizer = RecordingSummarizer()
    service = MemoryContextService(repository, cast(RealAgent, summarizer))
    messages = [message(f"m{index}", f"message-{index}") for index in range(40)]

    first_checkpoint = await service.prepare(
        conversation_id="conv-1",
        workspace_id="ws-1",
        user_message="continue",
        messages=messages[:20],
        pinned_messages=[],
    )

    assert [item.id for item in first_checkpoint.history] == [f"m{index}" for index in range(20)]
    first_summary = await repository.get("conv-1")
    assert first_summary is not None
    assert first_summary.up_to_message_id == "m19"
    assert len(summarizer.inputs) == 1

    between_checkpoints = await service.prepare(
        conversation_id="conv-1",
        workspace_id="ws-1",
        user_message="continue",
        messages=messages[:21],
        pinned_messages=[],
    )

    assert [item.id for item in between_checkpoints.history] == [
        f"m{index}" for index in range(1, 21)
    ]
    assert len(summarizer.inputs) == 1

    second_checkpoint = await service.prepare(
        conversation_id="conv-1",
        workspace_id="ws-1",
        user_message="continue",
        messages=messages,
        pinned_messages=[],
    )

    assert [item.id for item in second_checkpoint.history] == [
        f"m{index}" for index in range(20, 40)
    ]
    second_summary = await repository.get("conv-1")
    assert second_summary is not None
    assert second_summary.up_to_message_id == "m39"
    assert len(summarizer.inputs) == 2
    assert summarizer.inputs[1].context["previous_summary"] == {
        "facts": ["Earlier messages were summarized."],
        "requirements": [],
        "decisions": [],
        "open_questions": [],
        "promoted_changes": [],
    }


@pytest.mark.asyncio
async def test_memory_excludes_current_request_from_the_20_message_window() -> None:
    service = MemoryContextService(MemorySummaryRepository(), None)
    messages = [message(f"m{index}", f"message-{index}") for index in range(20)]
    current = message("m-current", "current request")

    prepared = await service.prepare(
        conversation_id="conv-1",
        workspace_id="ws-1",
        user_message=current.content,
        messages=[*messages, current],
        pinned_messages=[],
    )

    assert prepared.history == messages


@pytest.mark.asyncio
async def test_memory_overflow_fails_instead_of_silently_dropping_history() -> None:
    service = MemoryContextService(
        MemorySummaryRepository(),
        None,
        context_token_budget=2000,
        summary_trigger_tokens=1000,
    )
    messages = [message(f"m{index}", "x" * 1000) for index in range(12)]

    with pytest.raises(BadRequestError) as caught:
        await service.prepare(
            conversation_id="conv-1",
            workspace_id="ws-1",
            user_message="continue",
            messages=messages,
            pinned_messages=[],
        )

    assert caught.value.code == "memory_context_overflow"
