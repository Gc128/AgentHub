from agenthub.core.errors import NotFoundError
from agenthub.schemas.change_set import ChangeSet, ChangeSetFile, ValidationRun


class ChangeSetRepository:
    def __init__(self) -> None:
        self._change_sets: dict[str, ChangeSet] = {}

    async def save(self, change_set: ChangeSet) -> ChangeSet:
        self._change_sets[change_set.id] = change_set
        return change_set

    async def get(self, workspace_id: str, change_set_id: str) -> ChangeSet:
        change_set = self._change_sets.get(change_set_id)
        if change_set is None or change_set.workspace_id != workspace_id:
            raise NotFoundError("change_set_not_found", "Change set does not exist.")
        return change_set

    async def list_by_workspace(self, workspace_id: str) -> list[ChangeSet]:
        values = [
            change_set
            for change_set in self._change_sets.values()
            if change_set.workspace_id == workspace_id
        ]
        return sorted(values, key=lambda item: item.created_at, reverse=True)

    async def save_files(
        self, change_set_id: str, files: list[ChangeSetFile]
    ) -> list[ChangeSetFile]:
        change_set = self._change_sets.get(change_set_id)
        if change_set is None:
            raise NotFoundError("change_set_not_found", "Change set does not exist.")
        self._change_sets[change_set_id] = change_set.model_copy(update={"files": files})
        return files

    async def save_validation(self, validation: ValidationRun) -> ValidationRun:
        change_set = self._change_sets.get(validation.change_set_id)
        if change_set is None:
            raise NotFoundError("change_set_not_found", "Change set does not exist.")
        validations = [current for current in change_set.validations if current.id != validation.id]
        validations.append(validation)
        self._change_sets[change_set.id] = change_set.model_copy(
            update={"validations": validations}
        )
        return validation
