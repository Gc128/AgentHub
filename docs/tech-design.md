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
| `POST /api/conversations/{id}/messages/run` | Not used by Flask React demo | Supported | Non-streaming compatibility path; FastAPI saves the user message and all Agent messages. |
| `POST /api/conversations/{id}/messages/stream` | Not supported | Supported | Primary React send path. Returns SSE events: `user_message`, `agent_started`, `agent_delta`, `agent_done`, `artifact`, `harness_step`, `error`, `done`. |
| `GET /api/agents` | Supported | Supported | Lists stable ids: `orchestrator`, `code-agent`, `review-agent`, `preview-agent`. |
| `POST /api/agents/run` | Supported | Supported | Debug/single-Agent helper. `context.agent_id=orchestrator` returns a plan message without a fake file artifact. |
| `GET /api/workspaces/{id}/preview` | Supported | Supported | Uses `preview_url`, not `url`. |
| `GET /api/workspaces/{id}/files` | Supported | Supported | Returns file path and `updated_at`, not file content. |
| `GET /api/workspaces/{id}/files/content?path=...` | Supported | Supported | Returns one workspace file with content. |
| `POST /api/workspaces/{id}/files` | Supported | Supported | Demo helper to create or overwrite a workspace file. |
| `GET /api/workspaces/{id}/applied-diffs` | Supported | Supported | New records include optional `path`. |
| `POST /api/workspaces/{id}/apply-diff` | Supported | Supported | Applies a single-file unified diff and refreshes preview status. |

## Agents

All Agent execution goes through the `AgentAdapter` protocol. It is AgentHub's
unified protocol layer for LLM and tool backends: business services depend on
`AgentRunInput` and `AgentRunResult`, not on OpenAI, Claude, Mock, Codex, or a
future coding agent directly. Adapters keep provider details, auth, streaming,
timeouts, and response parsing outside the orchestration code.

`AgentAdapter.run()` remains the stable non-streaming method. Adapters may also
implement `stream()` as a `StreamingAgentAdapter`; `RealAgent` uses
OpenAI-compatible `stream: true` and `MockAgent` emits deterministic chunks for
offline tests.

The production path registers Orchestrator/Code/Review/Preview wrappers around
an OpenAI-compatible LLM adapter. Orchestrator returns an `OrchestratorDecision`
(`chat` or `plan`); child Agents return structured `AgentRunResult` objects and
validate required artifact types before returning.

When a user sends a message without `@Agent`, `MessageService` now uses
Orchestrator as the default LLM assistant entry. Greetings, ordinary chat, and
development planning all go through Orchestrator LLM. Rule-based `create_plan()`
remains only as a mock/legacy fallback.

The Orchestrator harness lifecycle is:

```txt
plan -> run step -> verify artifacts -> retry once on failure -> stop or continue
```

Each stage emits `harness_step` SSE events so the frontend can show live
progress while waiting for LLM responses. Structured JSON is buffered server-side;
only safe Markdown `content` is sent as `agent_delta` chunks. The plan message
uses role-specific instructions for Code, Review, and Preview Agents and does
not create a fake workspace file artifact.

If a model returns malformed JSON or a response that does not match the expected
schema, `RealAgent` silently asks the model to repair the output once. It also
normalizes common LLM shapes such as wrapped `result/data`, artifact maps,
Markdown code fences, raw HTML documents, JSON string-list findings, and
Markdown Orchestrator task plans. Code Agent remains strict: it must recover a
real model-produced code artifact and diff, otherwise the step fails. Review and
Preview can recover from schema errors by validating prior artifacts/workspace
context so their formatting problems do not block code preview.

Preview Agent is retained as a verification role. It checks workspace and
preview context, returns an honest preview artifact/status, and never claims to
have applied a diff or written files.

`USE_MOCK_AGENTS=false` and `AGENT_ALLOW_FALLBACKS=false` are the
production/default `.env.example` settings. Tests explicitly enable mock mode so
CI remains offline and deterministic. Real LLM settings are declared through
environment variables, and no key should be committed. The external smoke script
`scripts/verify_real_agent_tasks.py` runs ten real Orchestrator development
tasks through API, Apply Diff, and preview-page consistency checks.

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
