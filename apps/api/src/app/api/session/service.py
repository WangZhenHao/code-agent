"""会话管理的业务编排。

会话的「管理」动作（列表、编辑、删除）都归这里。删除语义就一个实现，
放在本模块的 `delete_session`，chat 模块不再有自己的删除入口。
"""

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.memory.checkpointer import get_checkpointer
from app.api.sandbox.service import delete_sandbox
from app.api.session.schemas import (
    SessionDeleteResponse,
    SessionSort,
    SessionItem,
    SessionListRequest,
    SessionListResponse,
    SessionUpdateRequest,
)
from app.db.models.session import Session, SessionStatus


async def list_sessions(
    req: SessionListRequest, user_id: int, session: AsyncSession
) -> SessionListResponse:
    """分页取当前用户的会话列表，倒序（默认按 updated_at，最近活跃的在前）。

    `status != delete` 而不是 `== running`：以后加终态时新状态会自动出现在列表里。
    这和 sessions 表上 `ix_sessions_user_id_updated_at` 的索引形态一致。
    """
    conditions = [
        Session.user_id == user_id,
        Session.status != SessionStatus.delete,
    ]
    if req.keyword:
        # ILIKE 不做转义处理：keyword 里的 % / _ 会被当成通配符。对「搜索自己的
        # 会话」这种场景不影响正确性（最坏是匹配多了），所以不引入 ESCAPE 逻辑。
        conditions.append(Session.title.ilike(f"%{req.keyword}%"))
    if req.platform is not None:
        conditions.append(Session.platform == req.platform)
    # publish 是 0/1 的整数列，不是布尔：判断用 `is not None` 而不是真值，
    # 否则 publish=0（筛未部署）会被当成「没传」直接跳过。
    if req.publish is not None:
        conditions.append(Session.publish == int(req.publish))

    total = await session.scalar(
        select(func.count()).select_from(Session).where(*conditions)
    )

    order_column = (
        Session.created_at if req.sort is SessionSort.created_at else Session.updated_at
    )
    rows = await session.scalars(
        select(Session)
        .where(*conditions)
        .order_by(order_column.desc())
        .offset((req.page - 1) * req.page_size)
        .limit(req.page_size)
    )

    return SessionListResponse(
        data=[SessionItem.model_validate(s) for s in rows],
        total=total or 0,
        page=req.page,
        page_size=req.page_size,
    )


async def _get_owned_session(
    id: str, user_id: int, session: AsyncSession
) -> Session:
    """取一个属于 user_id 且未删除的会话。

    不属于就当 404 而不是 403：不泄露「这个 id 存在但不归你」，
    和 chat 模块其它接口的处理一致。
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
    return chat


async def update_session(
    id: str, req: SessionUpdateRequest, user_id: int, session: AsyncSession
) -> SessionItem:
    """编辑会话，只改请求里出现的字段。

    `exclude_unset=True` 是这里的核心：它只吐出调用方**显式传了**的键，于是
    「没传」=不动，「传 null」=清空（仅对可空字段有意义）能区分开。直接
    `for k, v in req.model_dump().items()` 会把没传的字段一律写成 None，
    等于整体覆盖，前端只想改标题就会把描述、封面全清掉。

    title 在 schema 里允许 null 只是为了表达「不传」，落到列上是 NOT NULL，
    所以显式传 `title: null` 时跳过、不写——否则 commit 会撞非空约束变 500。
    """
    chat = await _get_owned_session(id, user_id, session)

    changes = req.model_dump(exclude_unset=True)
    if changes.get("title") is None:
        changes.pop("title", None)
    # publish 是 IntEnum，落到 Integer 列前转成 int：IntEnum 虽然是 int 子类，
    # 但驱动层的类型适配不保证认它，显式转换省得在某版 psycopg 上踩坑。
    if changes.get("publish") is not None:
        changes["publish"] = int(changes["publish"])

    for field, value in changes.items():
        setattr(chat, field, value)

    # updated_at 由 TimestampMixin 的 onupdate=func.now() 在 UPDATE 时写入，
    # 不用手工赋值；它同时决定列表排序，编辑完的会话会排到最前面。
    await session.commit()
    await session.refresh(chat)

    return SessionItem.model_validate(chat)


async def delete_session(
    id: str, user_id: int, session: AsyncSession
) -> SessionDeleteResponse:
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
    存在性查询就查不到了——先改状态会让「删一半失败」的会话变成查无此会话，
    外围资源再也清不掉。最后落库 + commit 保证「status 已删」等价于
    「外围已清干净」。

    幂等：重复调用同一 id，第二次仍然 404（status 已不是 running），
    不会二次删沙箱，也不会报错。
    """
    chat = await _get_owned_session(id, user_id, session)

    # 会话即 thread（README 约定 #4），thread_id 就是 id，没有第二条映射。
    checkpointer = await get_checkpointer()
    await checkpointer.adelete_thread(id)

    # 沙箱自己开 DB 会话写 preview 状态，与这里的 session 互不干扰；它内部和
    # start_sandbox 共用按 id 的进程内锁，不会和并发的 start 交叉。
    await delete_sandbox(id)

    chat.status = SessionStatus.delete
    await session.commit()

    return SessionDeleteResponse(id=chat.id, status=chat.status)
