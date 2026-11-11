"""WebSocket 鉴权与 Origin 校验。

**为什么不写成 FastAPI 依赖**：ws 的依赖在 `websocket.accept()` **之前**求值，
此时抛 `WebSocketException(4401)` 会让 Starlette 发 pre-accept close，uvicorn 把它
变成 **HTTP 403 握手失败**——浏览器只能看到 `1006`，拿不到关闭码，排查毫无线索。
uvicorn 也没实现 ASGI 的 `websocket.http.response` 扩展，所以正文/状态码都带不出去。

唯一能让客户端看见 4401/4404 的办法：**先 accept，再校验，再带码 close**。
所以鉴权写在路由函数体内；代价是 `app.dependency_overrides` 用不上，测试改 patch 模块属性。

令牌来源按优先级：`Authorization: Bearer` → `?token=` → `?access_token=`。
浏览器 WebSocket 构造函数设不了请求头，query 是唯一通用路径；头优先是给
非浏览器客户端一个「不把令牌写进 URL」的选项（URL 会进代理访问日志）。
**故意不认 `?user_id=` / `?ts=`**——那是 Coze 自家网关签好的身份，我们无从校验，
认了等于把鉴权关掉。
"""

from __future__ import annotations

import logging
from urllib.parse import urlsplit

from fastapi import HTTPException, WebSocket

from app.db.models.user import User
from app.db.session import SessionLocal
from app.security import decode_access_token
from app.settings import settings

logger = logging.getLogger(__name__)

# 4xxx 段是应用自定义关闭码。选这几个是因为和 HTTP 的 401/403/404 一一对应，
# 前端看到码就知道该重新登录、换 Origin、还是 id 写错了。
CLOSE_UNAUTHORIZED = 4401
CLOSE_FORBIDDEN = 4403
CLOSE_NOT_FOUND = 4404


class WsAuthError(Exception):
    """连接建立前的鉴权/归属失败。`code` 就是要发给客户端的关闭码。"""

    def __init__(self, code: int, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


def token_from_websocket(websocket: WebSocket) -> str | None:
    header = websocket.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        bearer = header[7:].strip()
        if bearer:
            return bearer
    for name in ("token", "access_token"):
        query_token = websocket.query_params.get(name)
        if query_token:
            return query_token
    return None


async def authenticate_ws(websocket: WebSocket) -> User:
    """校验令牌并查出 User 行（与 `get_current_user` 同语义：查库，不信任 token 里的 id）。"""
    token = token_from_websocket(websocket)
    if token is None:
        raise WsAuthError(CLOSE_UNAUTHORIZED, "缺少令牌")

    try:
        user_id = decode_access_token(token)
    except HTTPException as exc:
        # decode 只抛 401，语义和 4401 一一对应，不用再分原因
        # （过期 / 签名错 / 格式错对调用方都一样）。
        raise WsAuthError(CLOSE_UNAUTHORIZED, "令牌无效或已过期") from exc

    async with SessionLocal() as session:
        user = await session.get(User, user_id)
    if user is None:
        raise WsAuthError(CLOSE_UNAUTHORIZED, "用户不存在")
    # expire_on_commit=False + 只在 session 内读过属性，脱离上下文仍可读。
    return user


def origin_allowed(websocket: WebSocket) -> bool:
    """校验 Origin。

    **CORS 中间件不作用于 WebSocket**（它只看 http scope），所以这里必须自己做：
    跨站脚本可以拿着受害者的 query 令牌发起 WS 并读回推送，这是 WS 特有的风险面。

    放行规则：
    - 没有 Origin（非浏览器客户端）→ 放行；
    - Origin 的 host 与 Host 头一致 → 放行（生产走同源反代，cors_origins 可能是空的）；
    - 否则必须在 CODE_AGENT_CORS_ORIGINS 里。
    """
    origin = websocket.headers.get("origin")
    if not origin:
        return True

    host = websocket.headers.get("host", "")
    origin_host = urlsplit(origin).netloc
    if host and origin_host == host:
        return True

    return origin.rstrip("/") in settings.cors_origin_list
