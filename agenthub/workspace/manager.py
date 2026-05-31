from pathlib import Path


class WorkspacePathError(ValueError):
    pass


class WorkspaceManager:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def resolve(self, workspace_id: str, relative_path: str = ".") -> Path:
        workspace_root = (self.root / workspace_id).resolve()
        target = (workspace_root / relative_path).resolve()
        if workspace_root != target and workspace_root not in target.parents:
            raise WorkspacePathError("Path is outside the workspace.")
        return target

    def ensure_workspace(self, workspace_id: str) -> Path:
        path = self.resolve(workspace_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def write_text(self, workspace_id: str, relative_path: str, content: str) -> Path:
        target = self.resolve(workspace_id, relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def read_text(self, workspace_id: str, relative_path: str) -> str:
        return self.resolve(workspace_id, relative_path).read_text(encoding="utf-8")
