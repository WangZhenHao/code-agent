"""对话的业务编排。

目前用进程内字典存会话，只为把接口跑通；进程重启即丢。
落地时换成数据库 + LangGraph checkpointer，函数签名保持不变。
"""

from datetime import UTC, datetime
from uuid import uuid4

from app.api.chat.schemas import (
    ChatCreateRequest,
    ChatCreateResponse,
    ChatListResponse,
    ChatSession,
    SessionStatus,
)

# thread_id -> 会话
_SESSIONS: dict[str, ChatSession] = {}


def create_chat(req: ChatCreateRequest) -> ChatCreateResponse:
    """新建或复用会话，返回 thread_id。

    尚未接入 LangGraph：现在只登记会话，不真的跑模型。
    """
    thread_id = req.thread_id or uuid4().hex
    now = datetime.now(UTC)

    existing = _SESSIONS.get(thread_id)
    if existing is not None:
        existing.turns += 1
        existing.updated_at = now
        return ChatCreateResponse(
            thread_id=thread_id,
            title=existing.title,
            agent=existing.agent,
            status=existing.status,
            created_at=existing.created_at,
        )

    session = ChatSession(
        thread_id=thread_id,
        title=req.message[:30],
        agent=req.agent,
        status=SessionStatus.active,
        turns=1,
        created_at=now,
        updated_at=now,
    )
    _SESSIONS[thread_id] = session
    return ChatCreateResponse(
        thread_id=thread_id,
        title=session.title,
        agent=session.agent,
        status=session.status,
        created_at=session.created_at,
    )


def list_chats() -> ChatListResponse:
    """按最后活跃时间倒序列出会话。"""
    items = sorted(_SESSIONS.values(), key=lambda s: s.updated_at, reverse=True)
    return ChatListResponse(items=items, total=len(items))
