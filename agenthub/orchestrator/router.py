AGENT_MENTIONS = {
    "@Orchestrator": "orchestrator",
    "@CodeAgent": "code-agent",
    "@ReviewAgent": "review-agent",
    "@PreviewAgent": "preview-agent",
}


def route_agent(user_message: str) -> str | None:
    normalized = user_message.lower()
    for mention, agent_id in AGENT_MENTIONS.items():
        if mention.lower() in normalized:
            return agent_id
    return None
