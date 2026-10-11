"""Agent 流式执行：把 state + config 跑成一条 SSE 事件流。

从 api/agent/service.py 抽出来，因为「跑图并透传事件」是编排层的事，
和「校验会话、装配 state」这种 HTTP 层的活分开。调用方只管前置校验，
拿到 state/config 后交给 agent_stream() 迭代即可。
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator

from app.agents.graphs import get_graph
from app.agents.node.state import State

logger = logging.getLogger(__name__)


def sse(event: str, data: dict) -> str:
    """把一条消息编成 SSE 帧。

    必须是 `data: <单行>` + 两个换行。json.dumps 默认会带换行吗？不会——
    ensure_ascii=False 保留中文原样，不转成 \\uXXXX，前端拿到的就是可读文本。
    """
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def agent_stream(state: State, config: dict) -> AsyncIterator[str]:
    """跑图，把节点推的 custom 事件透传成 SSE 帧。

    Args:
        state: 图状态（含 mode/session/input，见 app.agents.node.state）。
        config: LangGraph 运行配置，至少含 {"configurable": {"thread_id": ...}}。

    本函数**自己兜异常**：generator 里抛异常会变成半截响应，客户端只能看到连接
    断掉。兜住并转成 error 事件，断在哪一步至少是可见的。
    """
    # 会话 ID 从 state 里取（调用方已保证存在）。start 帧和 done 帧都要带它。
    session_id = state["session"]["id"]

    try:
        # start 帧在 get_graph() 之前发？不——放在之后。get_graph 首次会建连接池、
        # 建表，若它抛异常，此时还没 yield 过，能干净地走 except 分支。
        graph = await get_graph()

        yield sse("start", {"thread_id": session_id})

        
        async for data in graph.astream(
            state, config=config, stream_mode="custom"
        ):
            # 事件名取节点推的 data["type"]（node_start / token / tool_call ...），
            # 前端按事件名分流，不用先解析 JSON 再判断。
            # 节点直接推字符串（或没带 type）时兜底成 token，不然 SSE 的
            # event 字段会是 "None"，前端 addEventListener 挂不上。
            if isinstance(data, dict):
                yield sse(data.get("type") or "token", data)
            else:
                yield sse("token", {"text": str(data)})

        yield sse("done", {"thread_id": session_id})

    except Exception as exc:
        logger.exception("agent_stream 失败 session_id=%s", session_id)
        yield sse("error", {"code": 500, "detail": str(exc)})
