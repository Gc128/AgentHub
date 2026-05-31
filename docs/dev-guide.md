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
