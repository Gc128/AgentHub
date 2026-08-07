from agenthub.schemas.memory import MemorySummaryRecordSchema


class MemorySummaryRepository:
    def __init__(self) -> None:
        self._summaries: dict[str, MemorySummaryRecordSchema] = {}

    async def get(self, conversation_id: str) -> MemorySummaryRecordSchema | None:
        return self._summaries.get(conversation_id)

    async def save(self, summary: MemorySummaryRecordSchema) -> MemorySummaryRecordSchema:
        self._summaries[summary.conversation_id] = summary
        return summary
