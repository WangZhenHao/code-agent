"""对话的业务编排。

会话落到 sessions 表（见 app/db/models/session.py）；列表接口还没接数据库，
仍是进程内字典占位，进程重启即丢。落地时换成真实查询，函数签名保持不变。
"""

import logging

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.memory.checkpointer import get_checkpointer
from app.api.chat.schemas import (
    ChatCreateRequest,
    ChatCreateResponse,
    ChatDeleteResponse,
    ChatDetailResponse,
    MessageItem,
    MessageListResponse,
)
from app.api.sandbox.service import delete_sandbox
from app.db.models.session import MessageStatus, Messages, Role, Session, SessionStatus


async def chat_detail(
    id: str, user_id: int, session: AsyncSession
) -> ChatDetailResponse:
    """取某个会话的详情。

    id 是会话 id（= LangGraph thread_id）。先确认这个会话属于 user_id——
    不属于就当 404 而不是 403：不泄露「这个 id 存在但不归你」，
    拿别人的 id 来探测时两种情况响应一致。
    """
    chat = await session.scalar(
        select(Session).where(
            Session.id == id,
            Session.user_id == user_id,
            Session.status != SessionStatus.delete,
        )
    )
    if chat is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不存在",
        )

    # from_attributes=True 让 Pydantic 直接读 ORM 实例的属性，无需手工搬字段。
    return ChatDetailResponse.model_validate(chat)

async def chat_message(
    id: str, user_id: int, session: AsyncSession
) -> MessageListResponse:
    """取某个会话的消息列表，按时间正序。

    id 是会话 id（= LangGraph thread_id）。先确认这个会话属于 user_id——
    不属于就当 404 而不是 403：不泄露「这个 id 存在但不归你」，
    拿别人的 id 来探测时两种情况响应一致。
    """
    owner = await session.scalar(
        select(Session.id).where(
            Session.id == id,
            Session.user_id == user_id,
            Session.status != SessionStatus.delete,
        )
    )
    if owner is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不存在",
        )

    rows = await session.scalars(
        select(Messages)
        .where(Messages.session_id == id)
        .order_by(Messages.created_at.asc())
    )
    items = [MessageItem.model_validate(m) for m in rows]
    return MessageListResponse(data=items, total=len(items))

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




async def delete_chat(
    id: str, user_id: int, session: AsyncSession
) -> ChatDeleteResponse:
    """删除会话：销毁沙箱、清掉 LangGraph 线程、软删 DB 行。

    三步做的事不一样，分开说：

    1. **沙箱用 `delete_sandbox`（销毁）而不是 `stop_sandbox`（暂停）**。
       service.py 里写得很清楚：暂停保留 PVC，用户下次进来还能看到代码；销毁删掉
       SandboxClaim，卷跟着走、不可逆。会话被真正删掉了，这份数据确定不再需要，
       留着只会白占 warmpool，所以走销毁。
    2. **LangGraph 线程用 `adelete_thread`**，不是同步的 `delete_thread`。后者在
       事件循环所在线程调用时会直接抛 InvalidStateError（它内部要
       run_coroutine_threadsafe 到自己的 loop 上），路由函数就运行在这个线程里。
    3. **DB 行是软删**（`status = SessionStatus.delete`），不是 DELETE。messages
       一并/CASCADE 删掉是不可逆的，而软删让误删的会话还留在库里可查可恢复；
       硬删只在用户注销那种路径上由 ondelete="CASCADE" 兜底。

    **顺序**：先删外围资源（checkpointer → 沙箱），最后落库改状态。理由是两个
    外围删除都幂等（会话没跑过就没有线程/沙箱，直接跳过），但库里的 status 一改，
    下面那句存在性查询就查不到了——先改状态会让「删一半失败」的会话变成查无此
    会话，外围资源再也清不掉。最后落库 + commit 保证「status 已删」等价于
    「外围已清干净」。

    id 是会话 id（= LangGraph thread_id）。先确认这个会话属于 user_id——
    不属于就当 404 而不是 403：不泄露「这个 id 存在但不归你」，
    拿别人的 id 来探测时两种情况响应一致。

    幂等：重复调用同一 id，第二次仍然 404（status 已不是 running），
    不会二次删沙箱，也不会报错。
    """
    chat = await session.scalar(
        select(Session).where(
            Session.id == id,
            Session.user_id == user_id,
            Session.status != SessionStatus.delete,
        )
    )
    if chat is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不存在",
        )

    # 会话即 thread（README 约定 #4），thread_id 就是 id，没有第二条映射。
    checkpointer = await get_checkpointer()
    await checkpointer.adelete_thread(id)

    # 沙箱自己开 DB 会话写 preview 状态，与这里的 session 互不干扰；它内部和
    # start_sandbox 共用按 id 的进程内锁，不会和并发的 start 交叉。
    await delete_sandbox(id)

    chat.status = SessionStatus.delete
    await session.commit()

    return ChatDeleteResponse(id=chat.id, status=chat.status)
