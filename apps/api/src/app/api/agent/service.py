"""Agent 注册表。目前只暴露有哪些 agent，未接编排。"""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.graphs import get_graph
from app.agents.node.state import Session, State
from app.api.chat.schemas import ChatCreateRequest
from app.db.models.session import Messages, Role


def agent_flows():

    pass


async def agent_retalk(session_id: str, user_id: int, session: AsyncSession):
    """与 agent 对话。"""
    session_data = await session.scalar(
        select(Session)
        .where(Session.id == session_id)
        .where(Session.user_id == user_id)
    )
    # 该会话一条消息都没有。没有这条判断的话下面读 .role 会先抛
    # AttributeError，接口返 500 而不是一个能讲清楚的 404。
    if session_data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不存在",
        )

    last_message = await session.scalar(
        select(Messages)
        .where(Messages.session_id == session_id)
        .order_by(Messages.created_at.desc())
        .limit(1)
    )

    if last_message.role != Role.user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="当前会话没有中断的消息，无法继续对话",
        )

    state: State = {
        "mode": last_message.mode,
        "session": {
            "id": session_id,
            "user_id": user_id,
        },
        "input": last_message.parts,
    }
    config = {
        "configurable": {
            "thread_id": session_id,
        }
    }

    graph = await get_graph()
    graph.invoke(state=state, config=config)

    return last_message


async def agent_talk(session_id: str, user_id: int, req: ChatCreateRequest, session: AsyncSession) -> str:
    """与 agent 对话。"""
    return "hello"
