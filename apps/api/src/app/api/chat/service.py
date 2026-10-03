"""对话的业务编排。

会话落到 sessions 表（见 app/db/models/session.py）；列表接口还没接数据库，
仍是进程内字典占位，进程重启即丢。落地时换成真实查询，函数签名保持不变。
"""

from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.chat.schemas import (
    ChatCreateRequest,
    ChatCreateResponse,
    ChatListResponse,
    ChatSession,
)
from app.db.models.session import PreviewStatus, Session, SessionStatus

# thread_id -> 会话（列表接口的临时占位，未接数据库）
_SESSIONS: dict[str, ChatSession] = {}


async def create_chat(
    req: ChatCreateRequest, user_id: int, session: AsyncSession
) -> ChatCreateResponse:
    """新建会话，落库并返回。

    尚未接入 LangGraph：现在只登记会话，不真的跑模型。
    """
    # add() 没有返回值，必须先把对象存进变量再登记，否则拿不到这个实例。
    chat = Session(
        id=str(uuid4()),
        title=req.message[:30],
        status=SessionStatus.running,
        user_id=user_id    
    )
    session.add(chat)
    await session.commit()
    # commit 后取回 DB 端生成的 created_at（server_default），否则该字段仍是 None。
    await session.refresh(chat)

    return ChatCreateResponse(
        thread_id=chat.id,
        title=chat.title,
        agent=req.mode,
        status=chat.status,
        created_at=chat.created_at,
    )


def list_chats() -> ChatListResponse:
    """按最后活跃时间倒序列出会话。"""
    items = sorted(_SESSIONS.values(),
                   key=lambda s: s.updated_at, reverse=True)
    return ChatListResponse(items=items, total=len(items))
