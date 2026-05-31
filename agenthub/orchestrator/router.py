AGENT_MENTIONS = {
    "@Orchestrator": "orchestrator",
    "@CodeAgent": "code-agent",
    "@ReviewAgent": "review-agent",
    "@PreviewAgent": "preview-agent",
}


def route_agent(user_message: str) -> str:
    for mention, agent_id in AGENT_MENTIONS.items():
        if mention in user_message:
            return agent_id
    if any(keyword in user_message for keyword in ["写", "实现", "生成", "页面", "组件"]):
        return "code-agent"
    if any(keyword in user_message for keyword in ["检查", "优化", "问题", "review", "bug"]):
        return "review-agent"
    if any(keyword in user_message for keyword in ["预览", "效果", "页面展示"]):
        return "preview-agent"
    return "orchestrator"
