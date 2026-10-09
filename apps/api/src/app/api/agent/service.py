"""Agent 注册表。目前只暴露有哪些 agent，未接编排。"""

from sqlalchemy.ext.asyncio import AsyncSession


def agent_retalk(session_id: str, user_id: int, session: AsyncSession) -> str:
    """与 agent 对话。"""
    return "hello"

def agent_talk(session_id: str, user_id: int, req, session: AsyncSession) -> str:
    """与 agent 对话。"""
    return "hello"