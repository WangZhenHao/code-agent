"""Agent 注册表。目前只暴露有哪些 agent，未接编排。"""

from app.api.agent.schemas import AgentInfo

_AGENTS: dict[str, AgentInfo] = {
    "general": AgentInfo(name="general", description="通用对话", available=True),
    "coding": AgentInfo(name="coding", description="编码（沙箱内）", available=False),
    "web_search": AgentInfo(
        name="web_search", description="联网检索", available=False
    ),
}


def list_agents() -> list[AgentInfo]:
    return list(_AGENTS.values())
