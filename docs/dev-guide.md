# AgentHub Development Guide

This guide is derived from `AgentHub Python-First 协作开发文档.docx`.

## Technical Direction

AgentHub keeps the backend, Agent Adapter, Orchestrator, Workspace, Diff, and preview services Python-first. The default demo direction is React frontend plus FastAPI backend, while a Python UI remains acceptable for a faster all-Python demo.

## MVP Priority

The first milestone should make the project start, test, and demonstrate the core path:

User request -> Orchestrator plan -> Agent output -> code/diff/preview artifacts -> apply change -> preview update -> persistent chat history.

## Validation Commands

```bash
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m mypy agenthub
python -m uvicorn agenthub.main:app --reload
```

## Local Demo Startup

The stable presentation path now uses the React client plus the FastAPI backend:

```bash
python -m uvicorn agenthub.main:app --reload
cd frontend
VITE_API_BASE_URL=http://127.0.0.1:8000 npm run dev
```

Production-like local runs should copy `.env.example` to `.env`, set
`OPENAI_API_KEY`, and keep `USE_MOCK_AGENTS=false`. The old Flask JSON service in
`frontend/flask/` is retained as a historical test fixture/reference, not as the
default demo backend.
