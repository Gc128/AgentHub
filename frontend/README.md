# AgentHub Frontend

React + TypeScript + Vite frontend for the AgentHub IM-style multi-agent workspace.

## Local Startup

Start the FastAPI backend first:

```bash
python -m uvicorn agenthub.main:app --reload
```

Then start the frontend:

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000 npm run dev
```

If `VITE_API_BASE_URL` is not set, the frontend defaults to `http://127.0.0.1:8000`.

## Build

```bash
npm run build
```

The send-message flow calls `POST /api/conversations/{conversation_id}/messages/run`.
FastAPI persists the user message and returns the complete Agent message sequence.
