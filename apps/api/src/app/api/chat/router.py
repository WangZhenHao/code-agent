"""对话接口。

路径用显式的动作名（/chat/create、/chat/list）而不是 REST 风格的
POST /chat + GET /chat，是为了后面加 /chat/stop、/chat/resume 这类
操作时路径形态保持一致。
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.chat.schemas import (
    ChatCreateRequest,
    ChatCreateResponse,
    ChatDeleteResponse,
    ChatDetailResponse,
    LangchainHistoryResponse,
    MessageListResponse,
)
from app.api.chat.service import (
    chat_detail,
    chat_langchain_history,
    chat_message,
    create_chat,
    delete_chat,
)
from app.db.models.user import User
from app.db.session import get_session
from app.security import get_current_user

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post(
    "/create",
    response_model=ChatCreateResponse,
    summary="新建或复用会话",
    responses={422: {"description": "message 为空，或 agent 名非法"}},
)
async def chat_create(
    req: ChatCreateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    return await create_chat(req, user_id=user.id, session=session)


@router.get(
    "/message/{id}",
    response_model=MessageListResponse,
    summary="获取会话消息",
    responses={404: {"description": "会话不存在或不属于当前用户"}},
)
async def message(
    id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """获取会话消息，按时间正序。"""
    return await chat_message(id, user.id, session)


@router.get(
    "/detail/{id}",
    response_model=ChatDetailResponse,
    summary="获取对话详情",
    responses={404: {"description": "会话不存在或不属于当前用户"}},
)
async def detail(
    id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    return await chat_detail(id, user.id, session)


@router.post(
    "/delete/{id}",
    response_model=ChatDeleteResponse,
    summary="删除会话",
    description=(
        "删除会话，**不可逆**：同时销毁会话沙箱（删 SandboxClaim，/workspace 的卷"
        "一起释放）、清掉该会话的 LangGraph 线程状态，并把 sessions 行置为已删除。\n\n"
        "与会话的其它动作不同，这条路径**不走暂停**——暂停保留卷和 CR，下次进来代码"
        "还在；删除按语义就是用户确定不再要这份数据了。\n\n"
        "幂等：重复删除同一个 id 一律 404，不会重复销毁。"
    ),
    responses={404: {"description": "会话不存在、已删除，或不属于当前用户"}},
)
async def chat_delete(
    id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """删除会话。路径参数名要跟 `{id}` 逐字一致，否则会退化成查询参数 `?id=`。"""
    return await delete_chat(id, user.id, session)


@router.get(
    "/message/langchain/{id}",
    response_model=LangchainHistoryResponse,
    summary="获取会话的对话历史（来自 LangGraph）",
    description=(
        "直接读 checkpointer 里的图状态，返回该会话的对话历史（user 与 ai 的消息），"
        "**按时间正序**。\n\n"
        "与 `GET /chat/message/{id}` 的区别：那个读 messages 表（业务落库、一轮一条），"
        "这个读图状态（含工具调用、中间推理等更细粒度，且可能包含没落库的轮次）。"
        "排查「前端显示的和实际跑的不一致」时拿两个接口对照。"
    ),
    responses={404: {"description": "会话不存在、已删除，或不属于当前用户"}},
)
async def langchain_history(
    id: str,
    # path 参数名必须与 {id} 逐字一致，写成别的会退化成查询参数 ?id=。
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """获取会话的对话历史（来自 LangGraph 图状态）。"""
    return await chat_langchain_history(id, user.id, session)
