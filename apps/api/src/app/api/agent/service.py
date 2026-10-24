"""Thread 命令 / 事件流 / 中止：Agent Streaming Protocol 的业务层。

三条路径对应三个 HTTP 接口（见 app/api/agent/router.py）：

- `agent_command`        POST /threads/{session_id}/commands
- `agent_stream_events`  POST /threads/{session_id}/stream
- `agent_abort`          POST /threads/{session_id}/abort（及旧的 /agents/abort/{id}）

和旧实现的区别：发起对话和接收事件拆成了两个请求。commands 只落库、起沙箱、
登记后台 run 就返回 JSON；事件由 run 写进 Redis，任何 stream 连接都能回放。
"""

import json
import logging
from collections.abc import AsyncIterator
from typing import Any, cast

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.node.state import State
from app.agents.threading.thread_session import ThreadSession
from app.api.agent.schemas import SubscribeParams
from app.api.chat.schemas import ChatCreateRequest
from app.api.sandbox.service import start_sandbox
from app.db.models.session import Messages, MessageStatus, Role

# ORM 模型起别名 SessionModel：app.agents.node.state 里有个**同名**的 Session
# （图状态的数据类，只有 id/user_id 两个注解，不是 ORM 模型）。两边一起 import
# 时后者会盖掉前者，select(Session.id) 就在一个普通类上取属性，报
# AttributeError。别名让两个名字互不干扰。
from app.db.models.session import Session as SessionModel
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)

# 沙箱里常驻的 Next.js 开发服务器。每次起 run 都跑一遍：命令是幂等的
# （nohup 重启），保证沙箱被回收重建后预览仍然可用。
_PREVIEW_COMMAND = "sh -c 'cd /workspace && nohup npm run dev > /tmp/next.log 2>&1 &'"


async def _require_owned_session(session: AsyncSession, session_id: str, user_id: int) -> None:
    """归属校验。拿别人的 id 来探测时响应 404，不泄露「存在但不归你」。"""
    exists = await session.scalar(
        select(SessionModel.id)
        .where(SessionModel.id == session_id)
        .where(SessionModel.user_id == user_id)
    )
    if exists is None:
        raise HTTPException(status_code=404, detail="会话不存在")


async def _retalk_state(
    session: AsyncSession, session_id: str, user_id: int
) -> State:
    """续跑分支：以最后一条 user 消息的 mode/parts/model 作为本轮输入。

    只有「上一轮被中断或没跑完（最后一条是 user 消息）」才允许续跑。最后一条
    是 assistant 说明那轮已经完整结束，再续等于凭空多跑一轮，返回 409。
    """
    last_message = await session.scalar(
        select(Messages)
        .where(Messages.session_id == session_id)
        .order_by(Messages.created_at.desc())
        .limit(1)
    )
    if last_message is None:
        raise HTTPException(status_code=404, detail="会话没有消息，无法继续对话")
    if last_message.role != Role.user:
        raise HTTPException(status_code=409, detail="当前会话没有中断的消息，无法继续对话")

    # 先取成普通值：session 关闭后 ORM 属性就不再保证可读（expire_on_commit
    # 是 False，已加载的属性本来也在，这里只是把生命周期写明白）。
    # cast：State 里的 session 声明成 `Session` 类，而运行时就是一个普通 dict
    # （LangGraph 只按字段名传递，不校验注解）。写法沿用旧实现，不改结构。
    return cast(State, {
        "mode": last_message.mode,
        "session": {"id": session_id, "user_id": user_id},
        "input": last_message.parts or [],
        "model": last_message.model,
    })


async def _new_message_state(
    session: AsyncSession,
    session_id: str,
    user_id: int,
    req: ChatCreateRequest,
) -> State:
    """新消息分支：先落一条 user 消息，再以请求体作为本轮输入。"""
    session.add(
        Messages(
            session_id=session_id,
            role=Role.user,
            status=MessageStatus.complete,
            model=req.model,
            parts=req.parts,
            mode=req.mode,
        )
    )
    await session.commit()

    return cast(State, {
        "mode": req.mode,
        "session": {"id": session_id, "user_id": user_id},
        "input": req.parts,
        "model": req.model,
    })


async def agent_command(
    session_id: str,
    user_id: int,
    req: ChatCreateRequest,
    session: AsyncSession,
) -> dict[str, Any]:
    """处理一条 thread 命令：校验 → 落库 → 起沙箱 → 后台起 run → 返回 run_id。

    入参是 `ChatCreateRequest`（和旧的 /talking、/retalk 共用），用 `parts`
    是否为空区分两个分支：

    - `parts == []`（默认值）→ 相当于旧 /retalk，续跑最后一条 user 消息；
    - `parts` 非空         → 相当于旧 /talking，新落一条 user 消息再跑。
    """
    await _require_owned_session(session, session_id, user_id)

    if req.parts:
        state = await _new_message_state(session, session_id, user_id, req)
    else:
        state = await _retalk_state(session, session_id, user_id)

    # start_sandbox 幂等（已有则复用），且直接返回句柄——别再调
    # create_sandbox_for_id，那个不去重，每调一次建一个。
    sandbox = await start_sandbox(session_id)
    sandbox.commands.run(_PREVIEW_COMMAND)

    run_id = await ThreadSession(session_id).start_run(state)
    return {"type": "success", "id": None, "result": {"run_id": run_id}}


async def agent_stream_events(
    session_id: str,
    user_id: int,
    params: SubscribeParams,
) -> AsyncIterator[str]:
    """订阅该线程的 SSE 事件流。

    这个接口**不接收 session 参数**，自己开一个。原因：`session: AsyncSession
    = Depends(get_session)` 是带 yield 的依赖，FastAPI 在响应头发出前就会退出
    它的 `async with` 把连接还池；而 generator 要到响应体开始 iteration 才执行
    ——那时 session 早就关了。这不是写法问题，是依赖生命周期的顺序。

    归属校验失败只能走 SSE error 帧：响应头在第一次 yield 时已经发出去了，
    之后没有状态码可改。
    """
    try:
        async with SessionLocal() as session:
            try:
                await _require_owned_session(session, session_id, user_id)
            except HTTPException as exc:
                yield _error_frame(exc.status_code, str(exc.detail))
                return

        async for frame in ThreadSession(session_id).stream(params.model_dump()):
            yield frame

    except Exception as exc:
        logger.exception("agent_stream_events 失败 session_id=%s", session_id)
        yield _error_frame(500, str(exc))


def _error_frame(code: int, detail: str) -> str:
    """把错误也包成 SSE 帧。

    形状对齐命令接口的 ErrorResponse（`{"type":"error","error","message"}`），
    另带一个 HTTP 语义的 `code` 方便前端分流。
    """
    payload = {
        "type": "error",
        "code": code,
        "error": "not_found" if code == 404 else "internal_error",
        "message": detail,
    }
    return f"event: message\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def agent_abort(
    session_id: str,
    user_id: int,
    session: AsyncSession,
) -> dict:
    """中止某个会话正在跑的 agent 轮次。

    返回 {"aborted": bool}：
      - true  = 有 run 在跑（本副本接住信号则模型和工具会停下来；别的副本
                收到 Redis 广播同样会停）。
      - false = 没有在跑的 run（已经跑完了）。

    没有 run 返回 false 而不是报错：前端重复点「停止」、或点在 run 刚结束
    之后，都不是错误，不该弹窗。
    """
    await _require_owned_session(session, session_id, user_id)
    return {"aborted": await ThreadSession(session_id).cancel()}
