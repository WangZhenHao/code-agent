"""Agent 注册表。目前只暴露有哪些 agent，未接编排。"""

import logging
from collections.abc import AsyncIterator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.helper import agent_stream, sse
from app.agents.node.state import State
from app.api.chat.schemas import ChatCreateRequest
# ORM 模型起别名 SessionModel：app.agents.node.state 里有个**同名**的 Session
# （图状态的数据类，只有 id/user_id 两个注解，不是 ORM 模型）。两边一起 import
# 时后者会盖掉前者，select(Session.id) 就在一个普通类上取属性，报
# AttributeError。别名让两个名字互不干扰。
from app.api.sandbox.service import start_sandbox
from app.db.models.session import Messages, Role
from app.db.models.session import Session as SessionModel
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


def agent_flows():

    pass


async def agent_retalk_stream(
    session_id: str, user_id: int
) -> AsyncIterator[str]:
    """与 agent 对话，SSE 流式返回。

    这个接口**不接收 session 参数**，自己开一个。

    原因：`session: AsyncSession = Depends(get_session)` 是带 yield 的依赖，
    FastAPI 在响应头发出之前就会退出它的 `async with` 把连接还池。而本函数
    返回的是 generator，函数体要到响应体开始 iteration 才执行——那时 session
    早就关了，任何查询都会抛 `Session is closed`。这不是写法问题，是依赖
    生命周期的顺序，绕不过去，只能自己开。
    """
    # generator 里不能直接 raise HTTPException 让路由转成状态码：响应头
    # （200 + text/event-stream）在第一次 yield 时就发出去了，之后没有状态码
    # 可改。所以错误一律走 SSE 的 error 事件，由前端处理。
    try:
        async with SessionLocal() as session:
            session_data = await session.scalar(
                select(SessionModel.id)
                .where(SessionModel.id == session_id)
                .where(SessionModel.user_id == user_id)
            )
            if session_data is None:
                yield sse("error", {"code": 404, "detail": "会话不存在"})
                return

            last_message = await session.scalar(
                select(Messages)
                .where(Messages.session_id == session_id)
                .order_by(Messages.created_at.desc())
                .limit(1)
            )
            if last_message is None:
                # 会话在但一条消息都没有。原来的同步版没这层判断，读 .role
                # 会 AttributeError 变 500，这里给个能讲清楚的说法。
                yield sse("error", {"code": 404, "detail": "会话没有消息，无法继续对话"})
                return

            if last_message.role != Role.user:
                yield sse("error", {"code": 409, "detail": "当前会话没有中断的消息，无法继续对话"})
                return

            # 先取成普通值。下面 commit/rollback 之后 ORM 对象可能过期，
            # 而且 session 一关就读不到了——不过 expire_on_commit=False，
            # 已加载的属性本来也还在，取出来纯粹是为了让生命周期一目了然。
            mode = last_message.mode
            parts = last_message.parts or []

        state: State = {
            "mode": mode,
            "session": {"id": session_id, "user_id": user_id},
            "input": parts,
            "model": last_message.model,
        }
        # 会话 ID 即 thread_id（仓库根 README 约定 #4）。
        config = {"configurable": {"thread_id": session_id}}

        # 跑图 + 透传事件都在 agent_stream 里（含 start/done/error 帧与内部异常兜底）。
        # 这里只负责前置校验和装配 state/config。
        # start_sandbox 幂等（已有则复用），且直接返回句柄——别再调 create_sandbox_for_id，
        # 那个不去重，每调一次建一个。
        sandbox = await start_sandbox(session_id)
        sandbox.commands.run(
            "sh -c 'cd /workspace && nohup npm run dev > /tmp/next.log 2>&1 &'"
        )
        async for frame in agent_stream(state, config):
            yield frame

        

    except Exception as exc:
        # 前置校验阶段的异常（如 DB 查询失败）。generator 里抛异常会变成半截响应，
        # 客户端只能看到连接断掉，所以兜住转成 error 事件。跑图阶段的异常已被
        # agent_stream 兜住，不会冒到这里。
        logger.exception("agent_retalk_stream 失败 session_id=%s", session_id)
        yield sse("error", {"code": 500, "detail": str(exc)})

        
async def agent_talk_stream(session_id: str, user_id: int, req: ChatCreateRequest) -> AsyncIterator[str]:
    try:
        state: State = {
            "mode": req.mode,
            "session": {"id": session_id, "user_id": user_id},
            "input": req.parts,
            "model": req.model,
        }
        # 会话 ID 即 thread_id（仓库根 README 约定 #4）。
        config = {"configurable": {"thread_id": session_id}}
        sandbox = await start_sandbox(session_id)

        sandbox.commands.run(
            "sh -c 'cd /workspace && nohup npm run dev > /tmp/next.log 2>&1 &'"
        )
        async for frame in agent_stream(state, config):
            yield frame

    except Exception as exc:
        logger.exception("agent_talk_stream 失败 session_id=%s", session_id)
        yield sse("error", {"code": 500, "detail": str(exc)})

