"""单个 WebSocket 连接的运行时。

三层结构：

- `ConnectionContext` —— handler 看到的全部东西（user / devbox_id / notify）。handler
  不该摸到 WebSocket，否则协议层一改就要动业务代码。
- `Connection` —— 出站队列 + 唯一 writer + 心跳。所有写操作都进队列，由 writer
  一个协程串行发出。
- `serve()` —— 读循环：收到一帧就开一个 task 去 dispatch。

**为什么是「队列 + 单 writer」而不是 send_lock**：Starlette 的 `send` 没有内部锁，
两个协程同时 `send_text` 会 RuntimeError；而用锁的话，慢应答会把推送一起堵在锁后面。
队列天然把两者分开：应答用阻塞 `put`（客户端读得慢，背压传回请求任务），
通知用 `put_nowait`（满了直接丢——状态类消息丢得起）。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from typing import TYPE_CHECKING

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

from app.api.ws import schemas
from app.api.ws.core import hub
from app.api.ws.core.dispatcher import dispatch as default_dispatch

if TYPE_CHECKING:
    from app.db.models.user import User

logger = logging.getLogger(__name__)

_CLOSE_TOO_BIG = 1009


class ConnectionContext:
    """handler 视角的连接。也用作 hub 的订阅键（所以要可哈希，默认按身份哈希）。"""

    def __init__(
        self,
        *,
        connection: Connection,
        user: User,
        devbox_id: str,
        max_inflight: int,
        max_bytes: int,
    ) -> None:
        self.connection = connection
        self.user = user
        self.devbox_id = devbox_id
        self.max_inflight = max_inflight
        self.max_bytes = max_bytes

    def notify(self, method: str, params: dict) -> None:
        """推一条无 id 的通知。**同步、非阻塞**：hub 在同步调用链里，不能 await。"""
        self.connection.send_nowait(schemas.dumps(schemas.notification(method, params)))


class Connection:
    def __init__(
        self, websocket: WebSocket, *, queue_size: int, heartbeat_seconds: int
    ) -> None:
        self._ws = websocket
        # None 是 writer 的退出信号：只有它有权限往队列里放 None。
        self._out: asyncio.Queue[str | None] = asyncio.Queue(maxsize=queue_size)
        self._heartbeat_seconds = heartbeat_seconds
        self._closed = asyncio.Event()
        self._warned_full = False

    @property
    def closed(self) -> bool:
        return self._closed.is_set()

    async def send(self, text: str) -> None:
        """应答走这里。队列满会阻塞——这就是背压，不需要额外策略。"""
        if self.closed:
            return
        await self._out.put(text)

    def send_nowait(self, text: str) -> None:
        """通知 / 心跳走这里。满了丢弃：宁可少一条推送，也不能让 writer 之外的
        路径卡住 hub 的发布方（它是同步调用链）。"""
        if self.closed:
            return
        try:
            self._out.put_nowait(text)
        except asyncio.QueueFull:
            # 限频告警：客户端不读的时候每帧都刷一条日志没有意义。
            if not self._warned_full:
                self._warned_full = True
                logger.warning("WS 出站队列已满，开始丢弃通知")

    async def _writer(self) -> None:
        """唯一真正调用 ws.send_text 的地方。"""
        while (text := await self._out.get()) is not None:
            await self._ws.send_text(text)

    async def _heartbeat(self) -> None:
        """应用层心跳。uvicorn 协议层 ping 有些代理不认/不转发，补一层数据帧。"""
        while True:
            await asyncio.sleep(self._heartbeat_seconds)
            self.send_nowait(
                schemas.dumps(
                    schemas.notification("ping", {"ts": int(time.time() * 1000)})
                )
            )

    async def _handle(self, raw: str, ctx: ConnectionContext, dispatch) -> None:
        """处理一帧。**必须吞掉所有异常**：ws scope 不在 main.py 的 HTTP 中间件里，
        漏出去就是 uvicorn 用 1011 裸关 + traceback。"""
        try:
            text = await dispatch(raw, ctx)
            if text:
                await self.send(text)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("WS 帧处理异常 devbox=%s", ctx.devbox_id)
            with contextlib.suppress(Exception):
                await self.send(
                    schemas.dumps(
                        schemas.error_response(
                            None, schemas.INTERNAL_ERROR, "服务器内部错误"
                        )
                    )
                )

    async def serve(self, ctx: ConnectionContext, dispatch=default_dispatch) -> None:
        """读循环，直到客户端断开或协议错误。调用方负责 accept / 鉴权 / 关连接。"""
        hub.subscribe(ctx.devbox_id, ctx)
        writer = asyncio.create_task(self._writer())
        heartbeat = asyncio.create_task(self._heartbeat())
        inflight: set[asyncio.Task[None]] = set()

        try:
            while True:
                message = await self._ws.receive()
                if message["type"] == "websocket.disconnect":
                    break

                raw = message.get("text")
                if raw is None:
                    # JSON-RPC 的线格式是文本；二进制帧不猜编码，直接回一条错误。
                    await self.send(
                        schemas.dumps(
                            schemas.error_response(
                                None, schemas.INVALID_REQUEST, "只能发送文本帧"
                            )
                        )
                    )
                    continue

                if len(raw.encode("utf-8", "ignore")) > ctx.max_bytes:
                    # 超限就直接关：继续读只会让攻击者白烧内存。1009 是规范里
                    # "message too big" 的关闭码，客户端能据此区分"我发太大了"。
                    await self._ws.close(
                        code=_CLOSE_TOO_BIG, reason="message too large"
                    )
                    break

                if len(inflight) >= ctx.max_inflight:
                    await self.send(
                        schemas.dumps(
                            schemas.error_response(
                                None, schemas.SERVER_BUSY, "请求太频繁"
                            )
                        )
                    )
                    continue

                task = asyncio.create_task(self._handle(raw, ctx, dispatch))
                inflight.add(task)
                task.add_done_callback(inflight.discard)
        except WebSocketDisconnect:
            pass
        except Exception:
            logger.exception("WS 读循环异常 devbox=%s", ctx.devbox_id)
        finally:
            self._closed.set()
            hub.unsubscribe(ctx.devbox_id, ctx)
            for task in inflight:
                task.cancel()
            writer.cancel()
            heartbeat.cancel()
            await asyncio.gather(writer, heartbeat, *inflight, return_exceptions=True)
