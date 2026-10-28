"""进程内推送中心：devbox_id → 本地连接集合。

后端想通知前端时调 `publish_devbox_event(...)`，消息体是标准 JSON-RPC 通知
（无 id），前端按 `method` 分发自己的业务逻辑。典型用法：

    await publish_devbox_event(session_id, "web.server_status_changed", {"preview": {...}})

**为什么不用 Redis**：这里的消息是「状态变了」这类可重复获取的信息，丢一条的代价
是前端显示过期，重连或再问一次 `preview.status` 就能补齐；为它背上 Stream + seq +
回放窗口的复杂度不划算。代价是**多副本部署时只有发布方所在副本上的连接能收到**。
要跨副本时，把这个模块的实现换成 Redis Pub/Sub 即可，调用方一行不用改——
所以对外只暴露 `subscribe` / `unsubscribe` / `publish_devbox_event` 三个函数。

并发：`_subscribers` 只在事件循环线程里改（FastAPI / uvicorn 单线程跑 asyncio），
不需要锁；`notify` 是非阻塞的入队操作，发布方不会被慢客户端拖住。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.api.ws.core.connection import ConnectionContext

logger = logging.getLogger(__name__)

_subscribers: dict[str, set[ConnectionContext]] = {}


def subscribe(devbox_id: str, ctx: ConnectionContext) -> None:
    _subscribers.setdefault(devbox_id, set()).add(ctx)


def unsubscribe(devbox_id: str, ctx: ConnectionContext) -> None:
    """连接关闭时调用。集合空了就把 key 删掉，避免 devbox 数量把 dict 撑大。"""
    peers = _subscribers.get(devbox_id)
    if peers is None:
        return
    peers.discard(ctx)
    if not peers:
        _subscribers.pop(devbox_id, None)


def publish_devbox_event(devbox_id: str, method: str, params: dict[str, Any]) -> int:
    """把一条通知推给该 devbox 的所有本地连接，返回推给了几个。

    没有连接时静默返回 0：这类消息丢掉是安全的（见模块 docstring）。
    单个连接推送失败只记日志——一个坏连接不能挡住其它连接收消息。
    """
    peers = list(_subscribers.get(devbox_id, ()))
    for ctx in peers:
        try:
            ctx.notify(method, params)
        except Exception:
            logger.warning(
                "WS 推送失败 devbox=%s method=%s", devbox_id, method, exc_info=True
            )
    return len(peers)


def subscriber_count(devbox_id: str) -> int:
    """给测试和排查用。"""
    return len(_subscribers.get(devbox_id, ()))
