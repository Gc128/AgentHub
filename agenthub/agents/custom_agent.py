import re

from agenthub.agents.langchain_agent import LangChainAgent
from agenthub.config import Settings
from agenthub.schemas.agent import AgentRunInput, AgentRunResult
from agenthub.schemas.custom_agent import CustomAgent


class CustomAgentAdapter:
    def __init__(self, agent: CustomAgent, settings: Settings | None = None) -> None:
        self.id = agent.id
        self.name = agent.name
        self.capabilities = agent.capabilities or ["custom"]
        self._agent = agent
        self._settings = settings

    async def run(self, input_data: AgentRunInput) -> AgentRunResult:
        display_input = input_data.model_copy(
            update={
                "user_message": _clean_custom_agent_user_message(
                    input_data.user_message, self._agent
                ),
                "context": input_data.context,
            }
        )
        if self._settings is None or self._settings.use_mock_agents:
            return AgentRunResult(
                agent_id=self.id,
                content=(
                    f"{self.name} 已收到：{display_input.user_message}\n\n"
                    f"系统提示词：{self._agent.system_prompt}"
                ),
                artifacts=[],
                next_actions=[],
            )

        llm = LangChainAgent(
            agent_id=self.id,
            provider=self._settings.agent_provider,
            model=self._settings.agent_model,
            api_key=self._settings.openai_api_key,
            base_url=self._settings.agent_base_url,
            timeout_seconds=self._settings.agent_request_timeout_seconds,
            response_format=self._settings.agent_response_format,
            thinking=self._settings.agent_thinking,
            max_tokens=self._settings.agent_max_tokens,
            system_prompt=self._agent.system_prompt,
        )
        content = await llm.request_text(display_input, force_text=True)
        return AgentRunResult(
            agent_id=self.id,
            content=_clean_custom_agent_output(content, self.id),
            artifacts=[],
            next_actions=[],
        )


def _clean_custom_agent_user_message(message: str, agent: CustomAgent) -> str:
    cleaned = message
    labels = {agent.id, agent.name, agent.name.replace(" ", "")}
    for label in labels:
        if not label:
            continue
        cleaned = re.sub(
            rf"@{re.escape(label)}(?=$|\s|[，,。.!！?？:：])\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
    return cleaned.strip() or message.strip()


def _clean_custom_agent_output(content: str, agent_id: str) -> str:
    return re.sub(
        rf"^\s*(?:{re.escape(agent_id)}|custom-agent[_-][a-zA-Z0-9]+)\s*[:：]\s*",
        "",
        content,
        count=1,
    ).lstrip()
