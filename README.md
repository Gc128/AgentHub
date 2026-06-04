# AgentHub

AgentHub is a Python-first IM-style multi-agent collaboration platform. The MVP focuses on a stable demo flow: a user sends a development request, the Orchestrator breaks it down, multiple Agents produce structured artifacts, the system shows code and diffs, the user applies changes, and the preview updates while the conversation history remains intact.

## Current Scope

- FastAPI backend and health check
- Pydantic schemas for conversations, messages, agents, artifacts, and agent runs
- OpenAI-compatible real Agent Adapter with mock mode reserved for tests
- Rule-based Orchestrator plan, routing, and backend multi-Agent execution
- Workspace-safe file manager, diff helper, Git wrapper, real filesystem writes, and preview metadata
- Project docs and tests scaffold

## Local Setup

```bash
python -m pip install -e ".[dev]"
cp .env.example .env
# Fill OPENAI_API_KEY in .env for real Agent runs.
python -m uvicorn agenthub.main:app --reload
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

## Validation

```bash
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m mypy agenthub
```

## Demo Direction

The first stable path should support:

1. Create a conversation.
2. Send `@Orchestrator` a development request.
3. Let the FastAPI backend route to Code Agent, Review Agent, and Preview Agent.
4. Return code, diff, and preview artifacts.
5. Apply changes to a bounded workspace.
6. Keep the full collaboration history in the chat stream.
