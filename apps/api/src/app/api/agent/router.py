"""Thread / Agent 接口。

Agent Streaming Protocol 的两个核心接口：

- `POST /threads/{session_id}/commands` — 发一条命令（新消息或续跑），立即返回
  `run_id`，图在后台跑；
- `POST /threads/{session_id}/stream`  — 订阅事件流（SSE），可带 `since` 回放。

外加 `POST /threads/{session_id}/abort`（取消正在跑的 run），以及保留在
`/agents/abort/{session_id}` 的旧路径。
"""

from fastapi import APIRouter, Body, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.agent.schemas import AbortResponse, CommandResponse, SubscribeParams
from app.api.agent.service import (
    agent_abort,
    agent_command,
    agent_stream_events,
)
from app.api.chat.schemas import ChatCreateRequest
from app.db.models.user import User
from app.db.session import get_session
from app.security import get_current_user

# threads_router = APIRouter(prefix="/threads", tags=["threads"])

# 旧路径的挂载点。/agents 下现在只剩 abort；talking / retalk 已删除。
router = APIRouter(prefix="/agents", tags=["agent"])

# SSE 必须关掉中间层缓冲，否则事件会攒在 nginx/网关里一次性吐出，流式就白做了。
# X-Accel-Buffering 是给 nginx 的显式开关。
_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


# ── Agent Streaming Protocol ──────────────────────────────────────────────


@router.post("/{session_id}/commands", response_model=CommandResponse)
async def thread_command(
    session_id: str,
    req: ChatCreateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """发起一轮对话或续跑上一轮，立即返回 run_id。

    入参与旧的 /agents/talking 相同（`ChatCreateRequest`）：
    `parts` 非空 ⇒ 落一条 user 消息再跑；`parts` 为空 ⇒ 续跑最后一条 user 消息。

    **普通 JSON 响应，不是 SSE。** 事件不从这里出去，由 /stream 单独订阅——
    这样客户端断线重连不会丢事件，也能多个订阅者同时看。

    路径参数名必须跟 `{session_id}` 逐字一致。写 `id: str` 的话 FastAPI 找不到
    同名路径参数，会把它当成**查询参数** `?id=`——接口不报错，但 session_id
    永远拿不到值，请求会 404（少参数则是 422）。
    """
    return await agent_command(
        session_id=session_id, user_id=user.id, req=req, session=session
    )


@router.post("/{session_id}/stream")
async def thread_stream(
    session_id: str,
    user: User = Depends(get_current_user),
    params: SubscribeParams = Body(default_factory=SubscribeParams),
):
    """订阅该线程的事件流（SSE，Agent Streaming Protocol 线格式）。

    body 可省；`{"since": <seq>}` 从上次的游标之后回放。

    **不注入 get_session**：带 yield 的依赖会在响应头发出前退出，而 generator
    要到那时才开跑，拿到的 session 已关闭。service 层自己开（同上一个接口的
    说明）。
    """
    return StreamingResponse(
        agent_stream_events(session_id=session_id, user_id=user.id, params=params),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


# @langchain/react 的 HttpAgentServerAdapter 默认路径是 `/stream/events`，
# 参考项目在客户端把它覆盖成 `/stream`。这里两个都提供，省得前端配。
@router.post("/{session_id}/stream/events", include_in_schema=False)
async def thread_stream_events(
    session_id: str,
    user: User = Depends(get_current_user),
    params: SubscribeParams = Body(default_factory=SubscribeParams),
):
    return StreamingResponse(
        agent_stream_events(session_id=session_id, user_id=user.id, params=params),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.post("/{session_id}/abort", response_model=AbortResponse)
async def thread_abort(
    session_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """中止该会话正在跑的轮次。

    **普通 JSON 响应，不是 SSE。** 前端拿到结果就该马上刷新按钮状态，不需要
    维持长连接。可以在注入的 session 上用：本函数不是 generator，依赖的生命
    周期正常。
    """
    return await agent_abort(session_id=session_id, user_id=user.id, session=session)


# ── 旧路径 ───────────────────────────────────────────────────────────────


@router.post("/abort/{session_id}", response_model=AbortResponse)
async def abort(
    session_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """中止该会话正在跑的轮次（旧路径，保留给已发布的调用方）。

    新代码用 `POST /threads/{session_id}/abort`，行为完全相同。
    """
    return await agent_abort(session_id=session_id, user_id=user.id, session=session)
