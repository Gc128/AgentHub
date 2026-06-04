import json
import re
import shlex
from typing import Any

import httpx
from pydantic import ValidationError

from agenthub.schemas.agent import AgentRunInput, AgentRunResult
from agenthub.schemas.artifact import Artifact


class RealAgentUnavailableError(RuntimeError):
    pass


class RealAgent:
    name = "Real Agent"
    capabilities = ["external-agent", "llm"]

    def __init__(
        self,
        *,
        agent_id: str = "real-agent",
        provider: str = "openai-compatible",
        model: str = "gpt-4o-mini",
        api_key: str | None = None,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 30.0,
        response_format: str = "json_object",
        thinking: str = "auto",
        max_tokens: int | None = None,
        system_prompt: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.id = agent_id
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.response_format = response_format
        self.thinking = thinking
        self.max_tokens = max_tokens
        self.system_prompt = system_prompt or (
            "You are an AgentHub coding assistant. Return concise Markdown "
            "unless the caller asks for structured JSON."
        )
        self._http_client = http_client

    async def run(self, input_data: AgentRunInput) -> AgentRunResult:
        if not self.api_key:
            raise RealAgentUnavailableError("Real agent integration is not configured yet.")
        if self.provider not in {"openai", "openai-compatible"}:
            raise RealAgentUnavailableError(f"Provider {self.provider!r} is not supported yet.")

        payload = self._build_payload(input_data)
        headers = {"Authorization": f"Bearer {self.api_key}"}

        try:
            if self._http_client is not None:
                response = await self._http_client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
            else:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                    )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RealAgentUnavailableError(self._status_error_message(exc)) from exc
        except httpx.TimeoutException as exc:
            raise RealAgentUnavailableError(
                f"LLM request timed out after {self.timeout_seconds:g} seconds "
                f"({type(exc).__name__}). Increase AGENT_REQUEST_TIMEOUT_SECONDS, "
                "disable provider-side thinking, or check provider latency."
            ) from exc
        except httpx.HTTPError as exc:
            raise RealAgentUnavailableError(
                f"LLM request failed before completion ({type(exc).__name__})."
            ) from exc

        content = self._extract_content(response.json())
        return self._parse_result(content)

    def _build_payload(self, input_data: AgentRunInput) -> dict[str, Any]:
        history_messages = [
            {
                "role": _message_role_for_llm(message.role),
                "content": f"{message.sender_id}: {message.content}",
            }
            for message in input_data.history[-8:]
        ]
        user_payload = {
            "conversation_id": input_data.conversation_id,
            "workspace_id": input_data.workspace_id,
            "user_message": input_data.user_message,
            "context": input_data.context,
        }
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                *history_messages,
                {
                    "role": "user",
                    "content": json.dumps(user_payload, ensure_ascii=False),
                },
            ],
            "temperature": 0.2,
        }
        if self.response_format == "json_object":
            payload["response_format"] = {"type": "json_object"}
        if self.thinking in {"enabled", "disabled"}:
            payload["thinking"] = {"type": self.thinking}
        if self.max_tokens is not None:
            payload["max_tokens"] = self.max_tokens
        return payload

    def _status_error_message(self, exc: httpx.HTTPStatusError) -> str:
        status_code = exc.response.status_code
        if status_code in {401, 403}:
            return (
                f"LLM request authentication failed with status {status_code}. "
                "Verify OPENAI_API_KEY belongs to the provider configured by AGENT_BASE_URL."
            )

        detail = _safe_response_excerpt(exc.response)
        suffix = f" Provider response: {detail}" if detail else ""
        return f"LLM request failed with status {status_code}.{suffix}"

    def _extract_content(self, payload: dict[str, Any]) -> str:
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise RealAgentUnavailableError("LLM response did not contain choices.")
        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            raise RealAgentUnavailableError("LLM response choice was malformed.")
        message = first_choice.get("message")
        if not isinstance(message, dict):
            raise RealAgentUnavailableError("LLM response message was malformed.")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise RealAgentUnavailableError("LLM response content was empty.")
        return content

    def _parse_result(self, content: str) -> AgentRunResult:
        payload_text = _strip_json_fence(content)
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError:
            return AgentRunResult(
                agent_id=self.id,
                content=content,
                artifacts=_extract_markdown_code_artifacts(content, self.id),
                next_actions=[],
            )

        if not isinstance(payload, dict):
            raise RealAgentUnavailableError("Structured LLM response must be a JSON object.")
        payload.setdefault("agent_id", self.id)
        payload.setdefault("artifacts", [])
        payload.setdefault("next_actions", [])
        payload["artifacts"] = [
            self._normalize_artifact(artifact, index)
            for index, artifact in enumerate(payload["artifacts"])
        ]
        content_value = payload.get("content")
        if isinstance(content_value, str):
            payload["artifacts"] = _merge_artifacts(
                payload["artifacts"],
                _extract_markdown_code_artifacts(content_value, self.id),
            )
        try:
            return AgentRunResult.model_validate(payload)
        except ValidationError as exc:
            raise RealAgentUnavailableError(
                "Structured LLM response did not match AgentRunResult schema."
            ) from exc

    def _normalize_artifact(self, artifact: object, index: int) -> object:
        if not isinstance(artifact, dict):
            return artifact

        artifact_type = artifact.get("type")
        if not isinstance(artifact_type, str) or not artifact_type:
            artifact_type = _infer_artifact_type(artifact)

        artifact_id = artifact.get("id")
        if not isinstance(artifact_id, str) or not artifact_id:
            artifact_id = f"artifact-{self.id}-{index + 1}"

        title = artifact.get("title")
        if not isinstance(title, str) or not title:
            title = _default_artifact_title(artifact, artifact_type)

        data = artifact.get("data")
        if not isinstance(data, dict):
            data = {
                key: value for key, value in artifact.items() if key not in {"id", "type", "title"}
            }

        return {
            "id": artifact_id,
            "type": artifact_type,
            "title": title,
            "data": data,
        }


def _strip_json_fence(content: str) -> str:
    value = content.strip()
    if value.startswith("```"):
        lines = value.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return value


def _message_role_for_llm(role: str) -> str:
    if role == "agent":
        return "assistant"
    if role == "system":
        return "system"
    return "user"


def _safe_response_excerpt(response: httpx.Response) -> str:
    try:
        text = response.text.strip()
    except Exception:
        return ""
    if not text:
        return ""
    sanitized = re.sub(r"Bearer\s+[A-Za-z0-9._-]+", "Bearer ***", text)
    sanitized = re.sub(r"sk-[A-Za-z0-9._-]+", "sk-***", sanitized)
    return sanitized[:300]


def _infer_artifact_type(artifact: dict[str, Any]) -> str:
    payload = _artifact_payload(artifact)
    if "diff" in payload:
        return "diff"
    if "preview_url" in payload:
        return "preview"
    if {"filename", "content"}.issubset(payload):
        return "code"
    return "file"


def _default_artifact_title(artifact: dict[str, Any], artifact_type: str) -> str:
    payload = _artifact_payload(artifact)
    filename = payload.get("filename")
    if isinstance(filename, str) and filename:
        return filename
    return artifact_type.capitalize()


def _artifact_payload(artifact: dict[str, Any]) -> dict[str, Any]:
    data = artifact.get("data")
    return data if isinstance(data, dict) else artifact


_CODE_FENCE_RE = re.compile(
    r"```(?P<meta>[^\n`]*)\n(?P<content>.*?)(?:\n```|```)",
    re.DOTALL,
)


def _extract_markdown_code_artifacts(content: str, agent_id: str) -> list[Artifact]:
    artifacts: list[Artifact] = []
    for index, match in enumerate(_CODE_FENCE_RE.finditer(content), start=1):
        metadata = _parse_code_fence_metadata(match.group("meta"), index)
        code_content = match.group("content")
        if not code_content:
            continue
        artifacts.append(
            Artifact(
                id=f"artifact-{agent_id}-markdown-{index}",
                type="code",
                title=metadata["filename"],
                data={
                    "filename": metadata["filename"],
                    "language": metadata["language"],
                    "content": code_content,
                },
            )
        )
    return artifacts


def _parse_code_fence_metadata(meta: str, index: int) -> dict[str, str]:
    tokens = shlex.split(meta.strip()) if meta.strip() else []
    language = _normalize_language(tokens[0]) if tokens else "text"
    filename = ""

    for token in tokens[1:]:
        key, separator, value = token.partition("=")
        if separator and key in {"filename", "file", "path"} and value:
            filename = value
            break
        if not separator and _looks_like_filename(token):
            filename = token
            break

    if not filename and tokens and _looks_like_filename(tokens[0]):
        filename = tokens[0]
        language = _language_from_filename(filename)

    if not filename:
        filename = _default_filename_for_language(language, index)

    return {"language": language, "filename": filename}


def _normalize_language(value: str) -> str:
    if not value:
        return "text"
    if _looks_like_filename(value):
        return _language_from_filename(value)
    return value.lower()


def _looks_like_filename(value: str) -> bool:
    return "/" in value or "." in value


def _language_from_filename(filename: str) -> str:
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return {
        "js": "javascript",
        "jsx": "jsx",
        "ts": "typescript",
        "tsx": "tsx",
        "html": "html",
        "css": "css",
        "py": "python",
        "md": "markdown",
    }.get(suffix, suffix or "text")


def _default_filename_for_language(language: str, index: int) -> str:
    return {
        "html": "index.html",
        "tsx": "src/App.tsx",
        "jsx": "src/App.jsx",
        "typescript": "src/App.ts",
        "javascript": "src/App.js",
        "css": "src/styles.css",
        "python": "main.py",
        "markdown": "README.md",
        "md": "README.md",
    }.get(language, f"artifact-{index}.txt")


def _merge_artifacts(existing: list[object], extracted: list[Artifact]) -> list[object]:
    seen = {_artifact_key(artifact) for artifact in existing}
    merged = list(existing)
    for artifact in extracted:
        key = _artifact_key(artifact)
        if key not in seen:
            merged.append(artifact)
            seen.add(key)
    return merged


def _artifact_key(artifact: object) -> tuple[str, str, str]:
    if isinstance(artifact, Artifact):
        filename = str(artifact.data.get("filename", ""))
        content = str(artifact.data.get("content", artifact.data.get("diff", "")))
        return (artifact.type, filename, content)
    if not isinstance(artifact, dict):
        return ("unknown", "", repr(artifact))
    artifact_type = str(artifact.get("type", ""))
    payload = _artifact_payload(artifact)
    filename = str(payload.get("filename", ""))
    content = str(payload.get("content", payload.get("diff", "")))
    return (artifact_type, filename, content)
