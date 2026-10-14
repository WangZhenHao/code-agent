"""Agent 管理接口。"""

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.agent.service import (
    agent_abort,
    agent_retalk_stream,
    agent_talk_stream,
)
from app.api.chat.schemas import ChatCreateRequest
from app.db.models.user import User
from app.db.session import get_session
from app.security import get_current_user
from sqlalchemy.ext.asyncio import AsyncSession


router = APIRouter(prefix="/agents", tags=["agent"])


@router.post("/talking/{session_id}")
async def talk(
    session_id: str,
    req: ChatCreateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """与 agent 对话。"""
    return StreamingResponse(
        agent_talk_stream(session_id=session_id, user_id=user.id, req=req, session=session),
        media_type="text/event-stream",
        headers={
            # SSE 必须关掉中间层缓冲，否则事件会攒在 nginx/网关里一次性吐出，
            # 流式就白做了。X-Accel-Buffering 是给 nginx 的显式开关。
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/retalk/{session_id}")
async def retalk(
    session_id: str,
    user: User = Depends(get_current_user),
):
    """与 agent 继续对话，SSE 流式返回。

    两个和普通 JSON 接口不同的地方：

    1. **不注入 get_session**。带 yield 的依赖在响应头发出前就退出了，而
       generator 要到那时才开跑，拿到的 session 已关闭。service 层自己开。
    2. 路径参数名必须跟 `{session_id}` 逐字一致。写 `id: str` 的话 FastAPI
       找不到同名路径参数，会把它当成**查询参数** `?id=`——接口不报错，
       但 session_id 永远拿不到值，请求会 404（少参数则是 422）。
    """
    return StreamingResponse(
        agent_retalk_stream(session_id=session_id, user_id=user.id),
        media_type="text/event-stream",
        headers={
            # SSE 必须关掉中间层缓冲，否则事件会攒在 nginx/网关里一次性吐出，
            # 流式就白做了。X-Accel-Buffering 是给 nginx 的显式开关。
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/abort/{session_id}")
async def abort(
    session_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """中止该会话正在跑的 agent 轮次。

    **普通 JSON 响应，不是 SSE。** 和上面两个接口不同：那两个是流，这里只是一次
    动作确认，前端拿到结果就该马上刷新按钮状态，不需要维持一条长连接。

    路径参数名 `session_id` 与 `{session_id}` 逐字一致，理由同 retalk 的 docstring：
    写成 `id` 的话 FastAPI 会当成查询参数 `?id=`，接口不报错但永远拿不到值。

    **可以在注入的 session 上用**（不像 retalk 必须自己开）：本函数不是 generator，
    依赖的生命周期正常。
    """
    return await agent_abort(session_id=session_id, user_id=user.id, session=session)
