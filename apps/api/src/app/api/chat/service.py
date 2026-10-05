"""对话的业务编排。

会话落到 sessions 表（见 app/db/models/session.py）；列表接口还没接数据库，
仍是进程内字典占位，进程重启即丢。落地时换成真实查询，函数签名保持不变。
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.chat.schemas import (
    ChatCreateRequest,
    ChatCreateResponse,
    ChatListResponse,
    ChatSession,
)
from app.db.models.session import MessageStatus, Messages, PreviewStatus, Role, Session, SessionStatus

# thread_id -> 会话（列表接口的临时占位，未接数据库）
_SESSIONS: dict[str, ChatSession] = {}


async def create_chat(
    req: ChatCreateRequest, user_id: int, session: AsyncSession
) -> ChatCreateResponse:
    """新建会话，落库并返回。

    尚未接入 LangGraph：现在只登记会话，不真的跑模型。
    """
    # add() 没有返回值，必须先把对象存进变量再登记，否则拿不到这个实例。
    # 不传 id：主键的 default=new_id 会生成 12 位 cuid2，显式传 id 会绕过它。
    # 会话和它的第一条消息是一次业务操作，放一个事务里：一起成功或一起回滚，
    # 不会出现「会话建了、消息插入失败」留下的空会话。
    chat = Session(
        title="",
        status=SessionStatus.running,
        user_id=user_id,
    )
    session.add(chat)
    # flush 而非 commit：id 的 default=new_id 是 Python 端默认值，flush 后就填好了，
    # 下一句拿 chat.id 建 message 不用等真正提交。
    await session.flush()

    # 用户这一轮的消息落 messages 表。没有 content/mode 列：
    # 内容存 parts（JSONB），role/status/model 是独立列。
    # parts 是 JSON 列，Pydantic 对象要先 model_dump() 成 dict 才写得进去。
    message = Messages(
        session_id=chat.id,
        role=Role.user,
        status=MessageStatus.complete,
        model=req.model,
        parts=[p.model_dump() for p in req.parts],
        mode=req.mode,
    )
    session.add(message)

    # 一次提交两张表，然后把 DB 端生成的 created_at 取回来。
    await session.commit()
    await session.refresh(chat)

    return ChatCreateResponse(
        id=chat.id,
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
