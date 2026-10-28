"""WebSocket 接口：`/ws/devbox/{devbox_id}`。

════════════════════════════════════════════════════════════════════════════
ws 路由**不进 OpenAPI**（`/openapi.json` 里看不到），所以协议写在这里，
前端手写客户端时以本 docstring 为准。

## 地址

    ws(s)://<host>/ws/devbox/{devbox_id}?token=<access_token>

`devbox_id` 就是会话 id（sessions.id）。令牌也可以放 `Authorization: Bearer`
请求头（非浏览器客户端），query 只是浏览器唯一可用的通道。

## 线格式：JSON-RPC 2.0

请求（客户端 → 服务端）：

    {"jsonrpc":"2.0","id":6,"method":"preview.status","params":{}}

应答（服务端 → 客户端，id 原样回显）：

    {"jsonrpc":"2.0","id":6,"result":{...}}
    {"jsonrpc":"2.0","id":6,"error":{"code":-32601,"message":"未知方法: xxx"}}

推送（服务端 → 客户端，**没有 id**，前端按 method 分发）：

    {"jsonrpc":"2.0","method":"web.server_status_changed","params":{...}}
    {"jsonrpc":"2.0","method":"ping","params":{"ts":1729999999999}}

请求里不带 `id` 视为通知：服务端执行但不回包。

## 错误码

    -32700 解析失败          -32601 方法不存在       -32001 devbox 不存在/已删/不归你
    -32600 请求格式不合法    -32602 参数错误         -32002 请求太频繁（并发超上限）
    -32603 内部错误
    不支持批量请求（发数组回 -32600）。

## 关闭码

    4401 未鉴权（缺令牌/无效/过期/用户不存在）—— 应重新登录
    4403 Origin 不被允许
    4404 devbox 不存在、已删除或不属于当前用户
    1009 单帧超长（默认 256 KiB）

**鉴权是先 accept 再 close 的**（理由见 `ws/core/auth.py`），所以浏览器拿到的是
上面的关闭码而不是握手的 HTTP 403——这也是为什么 ws 不能写成 FastAPI 依赖。

## 已注册方法

    preview.status    {} → 预览状态快照
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket

# 这一行同时完成方法注册：import methods → import 各方法模块 → 跑 @rpc_method。
# 放在 router.py 而不是 methods/__init__.py 里由别人 import，是为了让注册
# 只发生在「真正挂载 ws 路由」的进程里。
from app.api.ws import (
    config,
    methods,  # noqa: F401
)
from app.api.ws.core.auth import (
    CLOSE_FORBIDDEN,
    WsAuthError,
    authenticate_ws,
    origin_allowed,
)
from app.api.ws.core.connection import Connection, ConnectionContext
from app.api.ws.service import resolve_devbox

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["ws"])


@router.websocket("/devbox/{devbox_id}")
async def devbox_ws(websocket: WebSocket, devbox_id: str) -> None:
    """建立 devbox 的 JSON-RPC 长连接。协议见模块 docstring。

    路径参数名必须与 `{devbox_id}` 逐字一致——写错会静默降级成查询参数。
    """
    # 先 accept：不 accept 就没法带关闭码（见 ws/core/auth.py 的说明）。
    await websocket.accept()

    try:
        if not origin_allowed(websocket):
            raise WsAuthError(CLOSE_FORBIDDEN, "Origin 不被允许")
        user = await authenticate_ws(websocket)
        await resolve_devbox(devbox_id, user.id)
    except WsAuthError as exc:
        await websocket.close(code=exc.code, reason=exc.reason)
        return
    except Exception:
        # 鉴权阶段的意外（DB 挂了等）不能让连接悬着：1011 是规范里的内部错误码。
        logger.exception("WS 握手后校验失败 devbox=%s", devbox_id)
        await websocket.close(code=1011, reason="internal error")
        return

    connection = Connection(
        websocket,
        queue_size=config.SEND_QUEUE_SIZE,
        heartbeat_seconds=config.HEARTBEAT_SECONDS,
    )
    ctx = ConnectionContext(
        connection=connection,
        user=user,
        devbox_id=devbox_id,
        max_inflight=config.MAX_INFLIGHT,
        max_bytes=config.MAX_MESSAGE_BYTES,
    )
    await connection.serve(ctx)

    # serve 正常返回代表读循环结束了（客户端断开或协议错误）。退出前补一次
    # close：客户端断开时这是空操作，1009 那个分支已经关过了，也不重复。
    try:
        await websocket.close()
    except RuntimeError:
        # 已经关过了（Starlette 在重复 close 时抛 RuntimeError）
        pass
