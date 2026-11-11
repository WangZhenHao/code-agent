"""工具调用记录中间件：执行前后各写一次 `tool_calls` 表。

为什么放在中间件而不是从图事件里捞：`awrap_tool_call(request, handler)` 拿到的
`request.tool_call` 就是 `{id, name, args}`，`handler` 的返回值就是 `ToolMessage`
——id、参数、输出在这一处同时可见。从 `values` 快照里反推要等快照出现，而且工具
结果一进摘要压缩就再也捞不到了。

写库用自开的短会话（`SessionLocal`）：run 跑在后台 task 里，拿不到路由注入的
session，和 message_persistence 同款做法。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ToolCallRequest
from langchain_core.messages import ToolCall as LangChainToolCall
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from sqlalchemy.dialects.postgresql import insert

from app.db.models.tool_call import ToolCall as ToolCallRow
from app.db.models.tool_call import ToolCallStatus
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


def _output_text(message: ToolMessage) -> str:
    """把 ToolMessage.content 归一成字符串。

    content 可能是 str，也可能是内容块列表（多模态）。列表用 json 落库，
    前端拿到原样展示即可，不需要在这里猜格式。
    """
    content = message.content
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False)


class ToolRecorder(AgentMiddleware):
    """把每一次工具调用的参数、结果、状态写进 `tool_calls`。

    `session_id` 在构造时绑死：一个实例只服务一轮里的一个会话。
    """

    def __init__(self, session_id: str) -> None:
        super().__init__()
        self._session_id = session_id

    async def _upsert(
        self,
        *,
        tool_call_id: str,
        tool_name: str,
        input: Any,
        output: str | None,
        status: ToolCallStatus,
    ) -> None:
        stmt = insert(ToolCallRow).values(
            tool_call_id=tool_call_id,
            session_id=self._session_id,
            tool_name=tool_name,
            input=input,
            output=output,
            status=status,
        )
        # 重试同一 call id（模型重发、工具层重试）时覆盖而不是撞主键。
        stmt = stmt.on_conflict_do_update(
            index_elements=[ToolCallRow.tool_call_id],
            set_={
                "output": output,
                "status": status,
            },
        )
        async with SessionLocal() as session:
            await session.execute(stmt)
            await session.commit()

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        tool_call = request.tool_call
        tool_call_id = str(tool_call.get("id") or "")
        tool_name = str(tool_call.get("name") or "")

        # 没有 id 就没法被前端查询，记下来也没有意义——直接放行，不影响执行。
        if not tool_call_id:
            return await handler(request)

        # 先落 running：前端轮询能看到「在跑」，进程崩了也留得下痕迹
        # （由 finish 节点收成 interrupted）。
        try:
            await self._upsert(
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                input=tool_call.get("args") or {},
                output=None,
                status=ToolCallStatus.running,
            )
        except Exception:
            # 记录失败不能拖垮工具执行本身。
            logger.exception("tool_calls 写 running 失败 tool_call_id=%s", tool_call_id)

        # tools 通道只推 id / 名称 / 参数 / 状态，输出一律不推（前端按 id 查）。
        #
        # 这比对 `values` 快照合成可靠：codeAgent 是子图，根命名空间上根本没有
        # 它的 values 快照；而工具正文又在 messages 通道被过滤掉了，不在这里发，
        # 前端就永远看不到工具状态。
        self._emit_tool_event("tool-started", tool_call_id, tool_name, tool_call)

        try:
            result = await handler(request)
        except Exception as exc:
            await self._record_failure(tool_call_id, tool_name, tool_call, exc)
            self._emit_tool_event(
                "tool-finished",
                tool_call_id,
                tool_name,
                tool_call,
                status=ToolCallStatus.error,
            )
            raise

        if isinstance(result, ToolMessage):
            status = await self._record_result(
                tool_call_id, tool_name, tool_call, result
            )
            self._emit_tool_event(
                "tool-finished", tool_call_id, tool_name, tool_call, status=status
            )
        return result

    def _emit_tool_event(
        self,
        event: str,
        tool_call_id: str,
        tool_name: str,
        tool_call: LangChainToolCall,
        status: ToolCallStatus | None = None,
    ) -> None:
        """往本线程的 SSE 流里补一条 tools 通道事件。

        延迟 import：thread_session 会经 helper → node → code_agent 绕回来，
        模块级 import 成环。session_id 就是 LangGraph 的 thread_id。
        """
        from app.agents.threading.thread_session import get_session

        data: dict[str, Any] = {
            "event": event,
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
        }
        # 参数只在 tool-started 里带一次；tool-finished 只带 id + 终态。
        if status is None:
            data["input"] = tool_call.get("args") or {}
        else:
            data["status"] = status
        try:
            get_session(self._session_id)._emit(
                {
                    "type": "event",
                    "method": "tools",
                    "params": {"namespace": [], "data": data},
                }
            )
        except Exception:
            # 推事件失败不影响工具结果与落库。
            logger.exception("tools 事件推送失败 tool_call_id=%s", tool_call_id)

    async def _record_result(
        self,
        tool_call_id: str,
        tool_name: str,
        tool_call: LangChainToolCall,
        message: ToolMessage,
    ) -> ToolCallStatus:
        # ToolMessage.status 是 "success" / "error"，工具函数自己把可预期错误
        # 转成文本返回（见 _common.safe_call），所以这个字段通常也是 success。
        status = (
            ToolCallStatus.error
            if message.status == "error"
            else ToolCallStatus.success
        )
        try:
            await self._upsert(
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                input=tool_call.get("args") or {},
                output=_output_text(message),
                status=status,
            )
        except Exception:
            logger.exception("tool_calls 写结果失败 tool_call_id=%s", tool_call_id)
        return status

    async def _record_failure(
        self,
        tool_call_id: str,
        tool_name: str,
        tool_call: LangChainToolCall,
        exc: BaseException,
    ) -> None:
        try:
            await self._upsert(
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                input=tool_call.get("args") or {},
                output=f"错误：{type(exc).__name__}: {exc}",
                status=ToolCallStatus.error,
            )
        except Exception:
            logger.exception("tool_calls 写失败态时出错 tool_call_id=%s", tool_call_id)
