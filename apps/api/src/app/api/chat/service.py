"""对话的业务编排。

会话落到 sessions 表（见 app/db/models/session.py）；列表接口还没接数据库，
仍是进程内字典占位，进程重启即丢。落地时换成真实查询，函数签名保持不变。
"""


from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.chat.schemas import (
    ChatCreateRequest,
    ChatCreateResponse,
    ChatDetailResponse,
    LangchainHistoryResponse,
    LangchainMessageItem,
    MessageItem,
    MessageListResponse,
)
from app.db.models.session import Messages, Session, SessionStatus


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
    id: str, user_id: int, session: AsyncSession, limit: int = 50
) -> MessageListResponse:
    """取某个会话的消息列表，按时间正序，最多 limit 条（取的是最新的）。

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

    # 倒序取 limit 条再翻正：要的是「最新的一段」，直接升序 + limit 会拿到最旧的。
    # 同一毫秒内 created_at 可能相同（server_default 是事务时间），用 id 兜底保证
    # 翻回之后的顺序稳定。
    rows = list(
        await session.scalars(
            select(Messages)
            .where(Messages.session_id == id)
            .order_by(Messages.created_at.desc())
            .limit(limit)
        )
    )
    rows.reverse()
    items = [MessageItem.model_validate(m) for m in rows]
    # total 仍是会话里的消息总数，不受 limit 影响，前端靠它判断还有没有更早的。
    total = await session.scalar(
        select(func.count()).select_from(Messages).where(Messages.session_id == id)
    )
    return MessageListResponse(data=items, total=total or 0)

async def create_chat(
    req: ChatCreateRequest, user_id: int, session: AsyncSession
) -> ChatCreateResponse:
    """新建会话并**立刻跑起第一轮**。

    用户消息的落库和 run 的启动都交给 `agent_command`——和之后在同一会话里继续
    发消息走的是同一条路径，省得「新建」和「继续」两处各写一遍落库 + 起沙箱。

    两段事务是分开的：会话行先 commit（拿到 chat.id），`agent_command` 再在同一个
    session 上落消息、起沙箱、起 run。如果起 run 失败，会话已经存在但没有任何
    回复——前端刷新会看到一个空会话，再发一条消息即可继续，比整段回滚更可恢复。
    """
    # add() 没有返回值，必须先把对象存进变量再登记，否则拿不到这个实例。
    # 不传 id：主键的 default=new_id 会生成 12 位 cuid2，显式传 id 会绕过它。
    chat = Session(
        title="",
        status=SessionStatus.running,
        user_id=user_id,
    )
    session.add(chat)
    # flush 而非 commit：id 的 default=new_id 是 Python 端默认值，flush 后就填好了，
    # 下一句拿 chat.id 建 message 不用等真正提交。
    await session.flush()
    await session.commit()
    await session.refresh(chat)

    # 延迟 import：agent.service 会拉进 agents/threading（langgraph），而本模块
    # 在 app.api.chat 下、被 agent.service 反过来 import schemas——顶层互相引
    # 会绕成环。放函数里规避。
    from app.api.agent.service import agent_command

    await agent_command(
        session_id=chat.id, user_id=user_id, req=req, session=session
    )

    return ChatCreateResponse(
        id=chat.id,
        title=chat.title,
        status=chat.status,
        created_at=chat.created_at,
        description=chat.description,
    )


def _message_item(m: object) -> LangchainMessageItem:
    """把 checkpoint 里的一条消息转成响应模型。

    两种形态都兜：正常是 langchain 的 BaseMessage（.type / .model_dump()），
    但图状态是同进程反序列化出来的，别处（自建 CompiledStateGraph、手工写入
    状态）可能塞进普通 dict。只认 BaseMessage 的话，dict 形态会 AttributeError
    变 500——排查历史本就是为了搞清"到底存了什么"，恰恰最不该在这时候崩。
    """
    if isinstance(m, dict):
        return LangchainMessageItem(
            type=str(m.get("type") or m.get("role") or "unknown"),
            message=m,
        )
    return LangchainMessageItem(
        # model_dump() 的结果是 JSON 可序列化的（content 里的 dataclass 会被展开
        # 成 dict），直接进响应体没问题。
        type=getattr(m, "type", "unknown"),
        message=m.model_dump(),
    )

async def chat_langchain_history(
    id: str, user_id: int, session: AsyncSession
) -> LangchainHistoryResponse:
    """取某个会话的对话历史（user 与 ai 的消息，按时间正序）。

    和 `chat_message` 的分工：那个读 `messages` 表（业务侧落库的结果，一轮一条），
    这个直接读 checkpointer 里的图状态。**两个源不是同一份数据**：图状态里粒度更
    细（含工具调用、中间推理），也可能更多（模型跑完但落库失败的轮次，库里没有、
    checkpointer 里有）。排查"前端显示的和实际跑的不一致"时就靠这个接口对照。

    **只取最新一个 state，不遍历 checkpoint 历史**：currentRoundMessages 走
    add_messages 收敛，每个 checkpoint 存的都是"到那一步为止的全量"，所以最新的
    那个 state 本身就带着完整对话。遍历历史只会拿到一堆互相重复的全量快照。

    id 是会话 id（= LangGraph thread_id）。先确认这个会话属于 user_id——
    不属于就当 404 而不是 403，和同模块其它接口一致，不泄露
    "这个 id 存在但不归你"：拿别人的 id 来探测时两种情况响应一致。
    """
    # 只校验归属、不读 Session 对象：下面的数据全来自 checkpointer，不用 ORM 的行。
    # 用路由注入的 session（不是自开）：这里没有 generator，函数体在响应头发出前
    # 就跑完了，注入的那个还活着——agent/service.py 自开是因为它返回生成器。
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

    # 延迟 import：app.agents.graphs 那条链会拉进 app.agents.node.state，而它又
    # 从 app.api.chat.schemas 导类型——模块级的循环导入。放函数里规避，顺带让
    # 本模块在没起数据库的环境里也能 import（同 checkpointer 懒初始化的思路）。
    from app.agents.graphs import get_graph

    graph = await get_graph()
    config = {"configurable": {"thread_id": id}}

    # aget_state 而非 ainvoke/astream：只读当前状态，不触发任何节点执行。
    # 空线程（会话建了但没跑过图）返回的 snapshot.values 为空 dict。
    snapshot = await graph.aget_state(config)
    # values 是 TypedDict 形态的图状态，可能缺 currentRoundMessages（图还没跑过
    # 任何节点），.get 兜住。
    raw_messages = (snapshot.values or {}).get("messages") or []
    items = [_message_item(m) for m in raw_messages]

    return LangchainHistoryResponse(data=items, total=len(items))
