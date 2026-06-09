import asyncio
import json
import re
import shlex
from collections.abc import AsyncIterator
from typing import Any, TypeVar, cast

import httpx
from pydantic import BaseModel, ValidationError

from agenthub.schemas.agent import AgentRunInput, AgentRunResult
from agenthub.schemas.artifact import Artifact


class RealAgentUnavailableError(RuntimeError):
    pass


class RealAgentConfigurationError(RealAgentUnavailableError):
    pass


class RealAgentTransportError(RealAgentUnavailableError):
    pass


class RealAgentSchemaError(RealAgentUnavailableError):
    pass


StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


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
        content = await self._request_content(input_data)
        return await self._parse_agent_result_with_repair(input_data, content)

    async def run_structured(
        self,
        input_data: AgentRunInput,
        model: type[StructuredModel],
        *,
        schema_name: str,
    ) -> StructuredModel:
        content = await self._request_content(input_data)
        try:
            return _parse_structured_model(content, model)
        except RealAgentSchemaError as exc:
            repaired_content = await self._request_repair(
                input_data,
                original_content=content,
                validation_error=str(exc),
                schema_name=schema_name,
            )
            try:
                return _parse_structured_model(repaired_content, model)
            except RealAgentSchemaError as repaired_exc:
                raise RealAgentSchemaError(
                    f"模型连续返回了不符合 {schema_name} 结构的内容。"
                ) from repaired_exc

    async def request_text(self, input_data: AgentRunInput, *, force_text: bool = False) -> str:
        return await self._request_content(input_data, force_text=force_text)

    async def _request_content(
        self,
        input_data: AgentRunInput,
        *,
        force_text: bool = False,
    ) -> str:
        if not self.api_key:
            raise RealAgentConfigurationError("Real agent integration is not configured yet.")
        if self.provider not in {"openai", "openai-compatible"}:
            raise RealAgentConfigurationError(f"Provider {self.provider!r} is not supported yet.")

        payload = self._build_payload(input_data)
        if force_text:
            payload.pop("response_format", None)
        headers = {"Authorization": f"Bearer {self.api_key}"}
        response = await self._post_chat_completion(payload, headers)
        content = self._extract_content(response.json())
        return content

    async def _post_chat_completion(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> httpx.Response:
        attempts = 3
        for attempt in range(attempts):
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
                return response
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in {401, 403}:
                    raise RealAgentConfigurationError(self._status_error_message(exc)) from exc
                if exc.response.status_code >= 500 and attempt < attempts - 1:
                    await asyncio.sleep(0.4 * (attempt + 1))
                    continue
                raise RealAgentTransportError(self._status_error_message(exc)) from exc
            except httpx.TimeoutException as exc:
                if attempt < attempts - 1:
                    await asyncio.sleep(0.4 * (attempt + 1))
                    continue
                raise RealAgentTransportError(
                    f"LLM request timed out after {self.timeout_seconds:g} seconds "
                    f"({type(exc).__name__}). Increase AGENT_REQUEST_TIMEOUT_SECONDS, "
                    "disable provider-side thinking, or check provider latency."
                ) from exc
            except httpx.HTTPError as exc:
                if attempt < attempts - 1:
                    await asyncio.sleep(0.4 * (attempt + 1))
                    continue
                raise RealAgentTransportError(
                    f"LLM request failed before completion ({type(exc).__name__})."
                ) from exc
        raise RealAgentTransportError("LLM request failed before completion.")

    async def _request_repair(
        self,
        input_data: AgentRunInput,
        *,
        original_content: str,
        validation_error: str,
        schema_name: str,
    ) -> str:
        if not self.api_key:
            raise RealAgentConfigurationError("Real agent integration is not configured yet.")
        repair_payload = self._build_payload(input_data)
        repair_payload["messages"] = [
            {
                "role": "system",
                "content": (
                    "You repair malformed structured JSON for AgentHub. "
                    f"Return only one valid JSON object matching {schema_name}. "
                    "Do not include markdown fences or explanation."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "schema_name": schema_name,
                        "validation_error": validation_error,
                        "original_output": original_content,
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        headers = {"Authorization": f"Bearer {self.api_key}"}
        response = await self._post_chat_completion(repair_payload, headers)
        return self._extract_content(response.json())

    async def _parse_agent_result_with_repair(
        self,
        input_data: AgentRunInput,
        content: str,
    ) -> AgentRunResult:
        try:
            return self._parse_result(content)
        except RealAgentSchemaError as exc:
            repaired_content = await self._request_repair(
                input_data,
                original_content=content,
                validation_error=str(exc),
                schema_name="AgentRunResult",
            )
            try:
                return self._parse_result(repaired_content)
            except RealAgentSchemaError as repaired_exc:
                salvaged = _salvage_unstructured_agent_result(content, self.id)
                if salvaged is not None:
                    return salvaged
                salvaged = _salvage_unstructured_agent_result(repaired_content, self.id)
                if salvaged is not None:
                    return salvaged
                raise RealAgentSchemaError(
                    "模型连续返回了不符合 AgentRunResult 结构的内容。"
                ) from repaired_exc

    async def stream(self, input_data: AgentRunInput) -> AsyncIterator[str]:
        if not self.api_key:
            raise RealAgentConfigurationError("Real agent integration is not configured yet.")
        if self.provider not in {"openai", "openai-compatible"}:
            raise RealAgentConfigurationError(f"Provider {self.provider!r} is not supported yet.")

        payload = {**self._build_payload(input_data), "stream": True}
        headers = {"Authorization": f"Bearer {self.api_key}"}

        try:
            if self._http_client is not None:
                async with self._http_client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                ) as response:
                    response.raise_for_status()
                    async for chunk in _iter_stream_deltas(response):
                        yield chunk
            else:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    async with client.stream(
                        "POST",
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                    ) as response:
                        response.raise_for_status()
                        async for chunk in _iter_stream_deltas(response):
                            yield chunk
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {401, 403}:
                raise RealAgentConfigurationError(self._status_error_message(exc)) from exc
            raise RealAgentTransportError(self._status_error_message(exc)) from exc
        except httpx.TimeoutException as exc:
            raise RealAgentTransportError(
                f"LLM streaming request timed out after {self.timeout_seconds:g} seconds."
            ) from exc
        except httpx.HTTPError as exc:
            raise RealAgentTransportError(
                f"LLM streaming request failed before completion ({type(exc).__name__})."
            ) from exc

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
        except json.JSONDecodeError as exc:
            extracted_payload = _extract_json_object(payload_text)
            if extracted_payload and not _looks_like_json(payload_text):
                try:
                    payload = json.loads(extracted_payload)
                except json.JSONDecodeError:
                    return AgentRunResult(
                        agent_id=self.id,
                        content=content,
                        artifacts=_extract_markdown_code_artifacts(content, self.id),
                        next_actions=[],
                    )
            elif _looks_like_json(payload_text):
                raise RealAgentSchemaError("Structured LLM response was not valid JSON.") from exc
            else:
                return AgentRunResult(
                    agent_id=self.id,
                    content=content,
                    artifacts=_extract_markdown_code_artifacts(content, self.id),
                    next_actions=[],
                )

        if isinstance(payload, list):
            payload = _payload_from_json_list(payload, self.id)
        if not isinstance(payload, dict):
            raise RealAgentSchemaError("Structured LLM response must be a JSON object.")
        payload = _unwrap_agent_result_payload(payload)
        payload = _normalize_agent_result_payload(payload, self.id)
        payload.setdefault("agent_id", self.id)
        payload.setdefault("artifacts", [])
        payload.setdefault("next_actions", [])
        if not isinstance(payload["artifacts"], list):
            raise RealAgentSchemaError("Structured LLM artifacts field must be a list.")
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
            raise RealAgentSchemaError(
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


def _parse_structured_model(content: str, model: type[StructuredModel]) -> StructuredModel:
    payload_text = _strip_json_fence(content)
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        extracted_payload = _extract_json_object(payload_text)
        if not extracted_payload:
            if _looks_like_json(payload_text):
                salvaged = _salvage_structured_model_payload(
                    content,
                    None,
                    model,
                    chat_if_no_tasks=False,
                )
                if salvaged is not None:
                    return model.model_validate(salvaged)
                raise RealAgentSchemaError("Structured LLM response was not valid JSON.") from exc
            salvaged = _salvage_structured_model_payload(
                content,
                None,
                model,
                chat_if_no_tasks=False,
            )
            if salvaged is not None:
                return model.model_validate(salvaged)
            raise RealAgentSchemaError("Structured LLM response was not valid JSON.") from exc
        if _looks_like_json(payload_text):
            salvaged = _salvage_structured_model_payload(content, None, model)
            if salvaged is not None:
                return model.model_validate(salvaged)
            raise RealAgentSchemaError("Structured LLM response was not valid JSON.") from exc
        try:
            payload = json.loads(extracted_payload)
        except json.JSONDecodeError as extracted_exc:
            salvaged = _salvage_structured_model_payload(content, None, model)
            if salvaged is not None:
                return model.model_validate(salvaged)
            raise RealAgentSchemaError(
                "Structured LLM response was not valid JSON."
            ) from extracted_exc
    if not isinstance(payload, dict):
        salvaged = _salvage_structured_model_payload(content, payload, model)
        if salvaged is not None:
            return model.model_validate(salvaged)
        raise RealAgentSchemaError("Structured LLM response must be a JSON object.")
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        salvaged = _salvage_structured_model_payload(content, payload, model)
        if salvaged is not None:
            return model.model_validate(salvaged)
        raise RealAgentSchemaError(
            f"Structured LLM response did not match {model.__name__} schema."
        ) from exc


def _salvage_structured_model_payload(
    content: str,
    payload: object,
    model: type[StructuredModel],
    *,
    chat_if_no_tasks: bool = True,
) -> dict[str, Any] | None:
    if model.__name__ != "OrchestratorDecision":
        return None
    if isinstance(payload, list) and payload and all(isinstance(item, dict) for item in payload):
        return {
            "mode": "plan",
            "content": "## 任务拆解",
            "plan": {"summary": "LLM task list", "tasks": payload},
        }
    if isinstance(payload, dict):
        for key in ("steps", "tasks", "subtasks", "agents"):
            value = payload.get(key)
            if isinstance(value, list):
                return {
                    "mode": "plan",
                    "content": str(
                        payload.get("content") or payload.get("summary") or "## 任务拆解"
                    ),
                    "plan": {"summary": str(payload.get("summary") or ""), "tasks": value},
                }
        content_value = payload.get("content")
        if isinstance(content_value, str):
            return _salvage_orchestrator_decision_from_text(content_value, chat_if_no_tasks=False)
        return None
    display_content = _display_content_from_unstructured_output(content)
    if display_content != content:
        salvaged = _salvage_orchestrator_decision_from_text(
            display_content,
            chat_if_no_tasks=chat_if_no_tasks,
        )
        if salvaged is not None:
            return salvaged
    return _salvage_orchestrator_decision_from_text(
        content,
        chat_if_no_tasks=chat_if_no_tasks,
    )


def _salvage_orchestrator_decision_from_text(
    content: str,
    *,
    chat_if_no_tasks: bool = True,
) -> dict[str, Any] | None:
    text = content.strip()
    if not text:
        return None
    lowered = text.lower()
    tasks: list[dict[str, object]] = []
    if "code-agent" in lowered or "code agent" in lowered:
        tasks.append(
            {
                "task_id": "task-code",
                "agent_id": "code-agent",
                "instruction": (
                    "根据 context.user_request 实现用户需求，并输出 code artifact "
                    "和 diff artifact。"
                ),
                "depends_on": [],
            }
        )
    if "review-agent" in lowered or "review agent" in lowered:
        tasks.append(
            {
                "task_id": "task-review",
                "agent_id": "review-agent",
                "instruction": "审查前序代码和 diff，输出 findings 与 risk_level。",
                "depends_on": ["task-code"] if tasks else [],
            }
        )
    if "preview-agent" in lowered or "preview agent" in lowered:
        depends_on = (
            ["task-review"] if any(task["agent_id"] == "review-agent" for task in tasks) else []
        )
        tasks.append(
            {
                "task_id": "task-preview",
                "agent_id": "preview-agent",
                "instruction": "验证 workspace preview 状态，输出 preview artifact。",
                "depends_on": depends_on,
            }
        )
    if tasks:
        return {
            "mode": "plan",
            "content": text,
            "plan": {"summary": "LLM text plan", "tasks": tasks},
        }
    if not chat_if_no_tasks:
        return None
    return {"mode": "chat", "content": text, "plan": None}


def _salvage_unstructured_agent_result(content: str, agent_id: str) -> AgentRunResult | None:
    normalized_content = _display_content_from_unstructured_output(content)
    artifacts = _extract_markdown_code_artifacts(normalized_content, agent_id)
    if not artifacts:
        artifacts = _extract_html_document_artifacts(normalized_content, agent_id)
    if not artifacts and normalized_content != content:
        artifacts = _extract_markdown_code_artifacts(content, agent_id)
    if not artifacts and normalized_content != content:
        artifacts = _extract_html_document_artifacts(content, agent_id)
    if not artifacts:
        return None
    return AgentRunResult(
        agent_id=agent_id,
        content=normalized_content,
        artifacts=artifacts,
        next_actions=[],
    )


def _display_content_from_unstructured_output(content: str) -> str:
    parsed = _parse_json_like_string(content)
    if isinstance(parsed, dict):
        normalized = _normalize_agent_result_payload(parsed, "agent")
        content_value = normalized.get("content")
        if isinstance(content_value, str) and content_value.strip():
            return content_value
    content_match = re.search(r'"content"\s*:\s*"(?P<content>(?:\\.|[^"\\])*)"', content)
    if content_match:
        try:
            decoded = json.loads(f'"{content_match.group("content")}"')
            return decoded if isinstance(decoded, str) else str(decoded)
        except json.JSONDecodeError:
            return content_match.group("content")
    loose_content = _extract_loose_json_string_field(content, "content")
    if loose_content:
        return loose_content
    return content


def _extract_loose_json_string_field(content: str, field_name: str) -> str:
    pattern = re.compile(rf'"{re.escape(field_name)}"\s*:\s*"')
    match = pattern.search(content)
    if match is None:
        return ""

    start = match.end()
    delimiter = re.search(
        r'"\s*,\s*"(?:artifacts|next_actions|agent_id|plan|mode)"\s*:',
        content[start:],
    )
    if delimiter is not None:
        raw_value = content[start : start + delimiter.start()]
    else:
        raw_value = content[start:].strip()
        raw_value = re.sub(r'"\s*[,}]?\s*$', "", raw_value, count=1, flags=re.DOTALL)

    return _decode_loose_json_text(raw_value.strip())


def _decode_loose_json_text(value: str) -> str:
    if not value:
        return ""
    return (
        value.replace(r"\/", "/")
        .replace(r"\n", "\n")
        .replace(r"\r", "\r")
        .replace(r"\t", "\t")
        .replace(r"\"", '"')
        .replace(r"\\", "\\")
    ).strip()


def _parse_json_like_string(value: str) -> object | None:
    stripped = value.strip()
    if not _looks_like_json(stripped):
        return None
    try:
        return cast(object, json.loads(stripped))
    except json.JSONDecodeError:
        extracted = _extract_json_object(stripped)
        if not extracted:
            return None
        try:
            return cast(object, json.loads(extracted))
        except json.JSONDecodeError:
            return None


def _looks_like_json(content: str) -> bool:
    stripped = content.lstrip()
    return stripped.startswith("{") or stripped.startswith("[")


def _extract_json_object(content: str) -> str | None:
    start = content.find("{")
    if start < 0:
        return None

    in_string = False
    escaped = False
    depth = 0
    for index in range(start, len(content)):
        char = content[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue
        if char == "{":
            depth += 1
            continue
        if char == "}":
            depth -= 1
            if depth == 0:
                return content[start : index + 1].strip()

    return None


def _normalize_agent_result_payload(payload: dict[str, Any], agent_id: str) -> dict[str, Any]:
    values = dict(payload)
    if not isinstance(values.get("agent_id"), str) or not values.get("agent_id"):
        values["agent_id"] = agent_id

    values = _unwrap_nested_json_content_payload(values, agent_id)

    if "content" not in values or not isinstance(values.get("content"), str):
        for key in ("summary", "message", "reply", "description"):
            value = values.get(key)
            if isinstance(value, str) and value.strip():
                values["content"] = value
                break
    if "content" not in values or not isinstance(values.get("content"), str):
        values["content"] = _content_from_loose_payload(values)

    artifacts = values.get("artifacts")
    if isinstance(artifacts, dict):
        if _looks_like_loose_artifact(artifacts):
            artifacts = [artifacts]
        else:
            artifacts = _coerce_artifact_mapping(artifacts, agent_id)
    elif not isinstance(artifacts, list):
        artifacts = []
    values["artifacts"] = [
        *_coerce_loose_artifacts(artifacts),
        *_artifacts_from_loose_payload(values, agent_id),
    ]

    next_actions = values.get("next_actions", [])
    if isinstance(next_actions, str):
        values["next_actions"] = [next_actions]
    elif not isinstance(next_actions, list):
        values["next_actions"] = []

    return values


def _unwrap_nested_json_content_payload(payload: dict[str, Any], agent_id: str) -> dict[str, Any]:
    content = payload.get("content")
    if not isinstance(content, str):
        return payload
    nested = _parse_json_like_string(content)
    if not isinstance(nested, dict) or not _looks_like_agent_result_payload(nested):
        return payload

    nested_values = _normalize_agent_result_payload(
        {**nested, "agent_id": nested.get("agent_id") or agent_id},
        agent_id,
    )
    merged = dict(payload)
    merged["content"] = nested_values.get("content", "")
    existing_artifacts = payload.get("artifacts", [])
    if not isinstance(existing_artifacts, list):
        existing_artifacts = []
    nested_artifacts = nested_values.get("artifacts", [])
    if isinstance(nested_artifacts, list):
        merged["artifacts"] = [*existing_artifacts, *nested_artifacts]
    if "next_actions" not in merged and "next_actions" in nested_values:
        merged["next_actions"] = nested_values["next_actions"]
    return merged


def _unwrap_agent_result_payload(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("result", "data", "response", "agent_result"):
        value = payload.get(key)
        if isinstance(value, dict) and _looks_like_agent_result_payload(value):
            merged = dict(value)
            for outer_key in ("agent_id", "next_actions"):
                if outer_key not in merged and outer_key in payload:
                    merged[outer_key] = payload[outer_key]
            return merged
    return payload


def _payload_from_json_list(payload: list[object], agent_id: str) -> dict[str, Any] | object:
    if all(isinstance(item, str) and item.strip() for item in payload):
        lines = [str(item).strip() for item in payload]
        return {
            "agent_id": agent_id,
            "content": "\n".join(f"- {line}" for line in lines),
            "artifacts": [],
            "next_actions": [],
        }
    if payload and all(isinstance(item, dict) for item in payload):
        artifact_like_items = [
            item for item in payload if isinstance(item, dict) and _looks_like_loose_artifact(item)
        ]
        if artifact_like_items:
            return {
                "agent_id": agent_id,
                "content": _content_from_loose_payload({"artifacts": artifact_like_items}),
                "artifacts": artifact_like_items,
                "next_actions": [],
            }
    return payload


def _looks_like_agent_result_payload(payload: dict[str, Any]) -> bool:
    return any(
        key in payload
        for key in {
            "agent_id",
            "content",
            "summary",
            "message",
            "reply",
            "artifacts",
            "files",
            "file_changes",
            "generated_files",
            "filename",
            "code",
            "html",
        }
    )


def _content_from_loose_payload(payload: dict[str, Any]) -> str:
    content_parts: list[str] = []
    for artifact in _artifacts_from_loose_payload(payload, "agent"):
        if not isinstance(artifact, dict):
            continue
        artifact_payload = _artifact_payload(artifact)
        filename = artifact_payload.get("filename")
        code_content = artifact_payload.get("content")
        if not isinstance(code_content, str) or not code_content:
            continue
        language = str(artifact_payload.get("language") or _language_from_filename(str(filename)))
        if not isinstance(filename, str) or not filename:
            filename = _default_filename_for_language(language, len(content_parts) + 1)
        content_parts.append(f'```{language} filename="{filename}"\n{code_content.rstrip()}\n```')
    if content_parts:
        return "已生成代码。\n\n" + "\n\n".join(content_parts)
    return "已生成结果。"


def _coerce_loose_artifacts(artifacts: list[object]) -> list[object]:
    coerced: list[object] = []
    for index, artifact in enumerate(artifacts, start=1):
        if isinstance(artifact, dict):
            coerced.extend(_coerce_one_loose_artifact(artifact))
        elif isinstance(artifact, str) and artifact.strip():
            coerced.append(
                {
                    "id": f"artifact-file-{index}",
                    "type": "file",
                    "title": f"Artifact {index}",
                    "data": {"content": artifact.strip()},
                }
            )
    return coerced


def _coerce_artifact_mapping(artifacts: dict[str, Any], agent_id: str) -> list[object]:
    coerced: list[object] = []
    for key, value in artifacts.items():
        if isinstance(value, dict):
            artifact = dict(value)
            artifact.setdefault("title", key)
            if key in {"code", "html", "css", "javascript", "js", "typescript", "tsx"}:
                artifact.setdefault("type", "code")
            elif key in {"diff", "patch"}:
                artifact.setdefault("type", "diff")
            coerced.extend(_coerce_one_loose_artifact(artifact))
            continue

        if isinstance(value, str) and value.strip():
            filename = _filename_from_mapping_key(key)
            if filename:
                coerced.append(
                    {
                        "id": f"artifact-{agent_id}-{key}",
                        "type": "code",
                        "title": filename,
                        "data": {
                            "filename": filename,
                            "language": _language_from_filename(filename),
                            "content": value,
                        },
                    }
                )
            else:
                coerced.append(
                    {
                        "id": f"artifact-{agent_id}-{key}",
                        "type": "file",
                        "title": key,
                        "data": {"content": value},
                    }
                )
    return coerced


def _artifacts_from_loose_payload(payload: dict[str, Any], agent_id: str) -> list[object]:
    artifacts: list[object] = []
    for key in ("files", "file_changes", "generated_files"):
        value = payload.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    artifacts.extend(_coerce_one_loose_artifact(item))

    for key in ("code", "html", "css", "javascript", "js", "typescript", "tsx"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            filename = _filename_from_loose_payload(payload, key)
            artifacts.append(
                {
                    "id": f"artifact-{agent_id}-{key}",
                    "type": "code",
                    "title": filename,
                    "data": {
                        "filename": filename,
                        "language": _language_from_loose_key_or_filename(key, filename),
                        "content": value,
                    },
                }
            )

    if {"filename", "content"}.issubset(payload):
        artifacts.extend(_coerce_one_loose_artifact(payload))

    artifact = payload.get("artifact")
    if isinstance(artifact, dict):
        artifacts.extend(_coerce_one_loose_artifact(artifact))

    return artifacts


def _coerce_one_loose_artifact(artifact: dict[str, Any]) -> list[object]:
    payload = _artifact_payload(artifact)
    filename = _string_value(payload, "filename", "file", "path", "name")
    code_content = _string_value(payload, "content", "code", "source")
    diff = _string_value(payload, "diff", "patch")

    if filename and code_content:
        return [
            {
                **artifact,
                "type": artifact.get("type") or "code",
                "title": artifact.get("title") or filename,
                "data": {
                    **payload,
                    "filename": filename,
                    "language": payload.get("language") or _language_from_filename(filename),
                    "content": code_content,
                },
            }
        ]
    if filename and diff:
        return [
            {
                **artifact,
                "type": artifact.get("type") or "diff",
                "title": artifact.get("title") or f"{filename} diff",
                "data": {
                    **payload,
                    "filename": filename,
                    "diff": diff,
                },
            }
        ]
    return [artifact]


def _looks_like_loose_artifact(artifact: dict[str, Any]) -> bool:
    payload = _artifact_payload(artifact)
    if any(key in artifact for key in {"id", "type", "title", "data"}):
        return True
    if any(
        _string_value(payload, key)
        for key in {"filename", "file", "path", "content", "code", "source", "diff", "patch"}
    ):
        return True
    return False


def _filename_from_loose_payload(payload: dict[str, Any], key: str) -> str:
    filename = _string_value(payload, "filename", "file", "path", "name")
    if filename:
        return filename
    return {
        "html": "index.html",
        "css": "style.css",
        "javascript": "script.js",
        "js": "script.js",
        "typescript": "src/App.ts",
        "tsx": "src/App.tsx",
        "code": "index.html",
    }.get(key, "index.html")


def _filename_from_mapping_key(key: str) -> str | None:
    if _looks_like_filename(key):
        return key
    return {
        "html": "index.html",
        "code": "index.html",
        "css": "style.css",
        "javascript": "script.js",
        "js": "script.js",
        "typescript": "src/App.ts",
        "tsx": "src/App.tsx",
    }.get(key)


def _language_from_loose_key_or_filename(key: str, filename: str) -> str:
    return {
        "html": "html",
        "css": "css",
        "javascript": "javascript",
        "js": "javascript",
        "typescript": "typescript",
        "tsx": "tsx",
    }.get(key, _language_from_filename(filename))


def _string_value(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


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


async def _iter_stream_deltas(response: httpx.Response) -> AsyncIterator[str]:
    async for line in response.aiter_lines():
        value = line.strip()
        if not value or not value.startswith("data:"):
            continue
        data = value.removeprefix("data:").strip()
        if data == "[DONE]":
            break
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            continue
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            continue
        first = choices[0]
        if not isinstance(first, dict):
            continue
        delta = first.get("delta")
        if not isinstance(delta, dict):
            continue
        content = delta.get("content")
        if isinstance(content, str) and content:
            yield content


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


def _extract_html_document_artifacts(content: str, agent_id: str) -> list[Artifact]:
    match = re.search(
        r"(?is)(<!doctype\s+html[^<]*>\s*)?<html\b.*?</html>",
        content,
    )
    if match is None:
        return []
    html = match.group(0).strip()
    if not html:
        return []
    return [
        Artifact(
            id=f"artifact-{agent_id}-html-document",
            type="code",
            title="index.html",
            data={
                "filename": "index.html",
                "language": "html",
                "content": html,
            },
        )
    ]


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
