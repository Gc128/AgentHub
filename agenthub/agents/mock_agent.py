import json
from collections.abc import AsyncIterator
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

from agenthub.schemas.agent import AgentRunInput, AgentRunResult
from agenthub.schemas.artifact import Artifact


@lru_cache
def load_demo_responses() -> dict[str, Any]:
    response_path = Path(__file__).resolve().parents[2] / "mock" / "demo_responses" / "agents.json"
    if not response_path.exists():
        return {}
    data = json.loads(response_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {}
    return cast(dict[str, Any], data)


def format_demo_value(value: Any, variables: dict[str, str]) -> Any:
    if isinstance(value, str):
        return value.format(**variables)
    if isinstance(value, list):
        return [format_demo_value(item, variables) for item in value]
    if isinstance(value, dict):
        return {key: format_demo_value(item, variables) for key, item in value.items()}
    return value


class MockAgent:
    def __init__(self, agent_id: str = "mock-agent") -> None:
        self.id = agent_id
        self.name = agent_id.replace("-", " ").title()
        self.capabilities = ["demo", "offline", "artifact"]

    async def run(self, input_data: AgentRunInput) -> AgentRunResult:
        response = load_demo_responses().get(self.id, load_demo_responses().get("mock-agent", {}))
        variables = {
            "agent_name": self.name,
            "user_message": input_data.user_message,
            "workspace_id": input_data.workspace_id,
        }
        content_template = response.get("content", "{agent_name} received: {user_message}")
        content = str(content_template).format(**variables)
        artifacts = [
            Artifact.model_validate(artifact)
            for artifact in format_demo_value(
                response.get(
                    "artifacts",
                    [
                        {
                            "id": f"artifact-{self.id}",
                            "type": "code",
                            "title": "Mock response",
                            "data": {
                                "filename": "README.md",
                                "language": "markdown",
                                "content": f"# Response for {input_data.user_message}",
                                "workspace_id": input_data.workspace_id,
                            },
                        }
                    ],
                ),
                variables,
            )
        ]
        return AgentRunResult(
            agent_id=self.id,
            content=content,
            artifacts=artifacts,
            next_actions=list(
                format_demo_value(
                    response.get("next_actions", ["review", "preview"]),
                    variables,
                )
            ),
        )

    async def stream(self, input_data: AgentRunInput) -> AsyncIterator[str]:
        result = await self.run(input_data)
        words = result.content.split()
        if not words:
            return
        for index, word in enumerate(words):
            separator = "" if index == 0 else " "
            yield f"{separator}{word}"
