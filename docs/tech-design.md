# Technical Design

## Backend

FastAPI exposes conversation, message, agent, and workspace APIs. Route handlers should delegate business logic to services.

## Agents

All Agent execution goes through the `AgentAdapter` protocol. Mock Agents are first-class fallback components for offline development and stable demos.

## Workspace

Workspace operations use `pathlib.Path` and must stay inside the configured workspace root. Git commands are wrapped and use argument lists with bounded working directories.
