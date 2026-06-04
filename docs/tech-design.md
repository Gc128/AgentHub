# Technical Design

## Backend

FastAPI exposes conversation, message, agent, and workspace APIs. Route handlers should delegate business logic to services.

## Agents

All Agent execution goes through the `AgentAdapter` protocol. Mock Agents are first-class fallback components for offline development and stable demos.

## Workspace

Workspace operations use `pathlib.Path` and must stay inside the configured workspace root. Git commands are wrapped and use argument lists with bounded working directories.

Current React + Flask demo keeps workspace files in JSON tables while reusing
`agenthub.workspace.diff` for unified diff generation and application. A code
artifact creates a pending diff artifact for the same logical file, but it does
not update `workspace_files.json` until the user calls Apply Diff.

`AppliedDiffRecord.path` is optional for compatibility with older demo history.
New Apply Diff responses and history rows include `path` to show which workspace
file was changed.
