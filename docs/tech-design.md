# Technical Design

## Backend

FastAPI exposes conversation, message, agent, and workspace APIs. Route handlers should delegate business logic to services.

## API Contract

The React client now treats FastAPI as the default MVP backend. The historical
Flask JSON service keeps a compatible contract for regression/reference use, but
new demo work should run against `VITE_API_BASE_URL=http://127.0.0.1:8000`.

| Frontend call | Flask demo | FastAPI status | Notes |
|---|---|---|---|
| `GET /api/conversations` | Supported | Supported | Returns `Conversation[]` with `is_pinned` and `workspace_id`. |
| `POST /api/conversations` | Supported | Supported | Creates a conversation and workspace id. |
| `PATCH /api/conversations/{id}` | Supported | Supported | Updates `title`, `mode`, `agent_ids`, and `is_pinned`. |
| `DELETE /api/conversations/{id}` | Supported | Supported | Returns `{ id, deleted }`; FastAPI also clears in-memory messages. |
| `GET /api/conversations/{id}/messages` | Supported | Supported | Returns `Message[]`. |
| `POST /api/conversations/{id}/messages` | Supported | Supported | Saves one message and returns one `Message`; it does not auto-run Agents. |
| `POST /api/conversations/{id}/messages/run` | Not used by Flask React demo | Supported | Primary current React send path; FastAPI saves the user message and all Agent messages. |
| `GET /api/agents` | Supported | Supported | Lists stable ids: `orchestrator`, `code-agent`, `review-agent`, `preview-agent`. |
| `POST /api/agents/run` | Supported | Supported | Debug/single-Agent helper. `context.agent_id=orchestrator` returns a plan artifact only. |
| `GET /api/workspaces/{id}/preview` | Supported | Supported | Uses `preview_url`, not `url`. |
| `GET /api/workspaces/{id}/files` | Supported | Supported | Returns file path and `updated_at`, not file content. |
| `GET /api/workspaces/{id}/files/content?path=...` | Supported | Supported | Returns one workspace file with content. |
| `POST /api/workspaces/{id}/files` | Supported | Supported | Demo helper to create or overwrite a workspace file. |
| `GET /api/workspaces/{id}/applied-diffs` | Supported | Supported | New records include optional `path`. |
| `POST /api/workspaces/{id}/apply-diff` | Supported | Supported | Applies a single-file unified diff and refreshes preview status. |

## Agents

All Agent execution goes through the `AgentAdapter` protocol. The production
path registers Code/Review/Preview wrappers around an OpenAI-compatible LLM
adapter. Each wrapper asks for a structured `AgentRunResult` JSON object and
validates required artifact types before returning.

`USE_MOCK_AGENTS=false` is the production/default `.env.example` setting. Tests
explicitly enable mock mode so CI remains offline and deterministic. Real LLM
settings are declared through environment variables, and no key should be
committed.

## Workspace

Workspace operations use `pathlib.Path` and must stay inside the configured workspace root. Git commands are wrapped and use argument lists with bounded working directories.

FastAPI workspace content is backed by real files under `WORKSPACE_ROOT`.
SQLite/in-memory repositories store preview metadata and applied-diff history;
file reads, writes, preview-page rendering, and Apply Diff all use the same
bounded filesystem workspace.

`AppliedDiffRecord.path` is optional for compatibility with older demo history.
New Apply Diff responses and history rows include `path` to show which workspace
file was changed.

FastAPI defaults to SQLite for production-like local runs. Tests set
`PERSISTENCE_BACKEND=memory` to keep isolated state.
