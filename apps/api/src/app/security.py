"""JWT 签发 / 校验，以及 `get_current_user` 鉴权依赖。

无状态方案：token 自包含，服务端不查任何存储。代价是签发后在过期前
无法吊销（想强制下线得再叠一层 jti 黑名单）。本阶段接受这个代价——
接口形态不用变，以后要加强只是往校验里多查一次黑名单。

密钥不设默认值（见 settings.py），缺失即启动失败。HS256 是对称的，
所以密钥泄漏 = 任何人可伪造任意用户，生产必须从 secret 注入且够长。
"""

from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import User
from app.db.session import get_session
from app.settings import settings

ALGORITHM = "HS256"

# auto_error=False：默认行为是缺 header 时直接抛 403（且响应体是框架文案）。
# 我们自己控制成 401 + 统一文案，所以关掉自动报错。
_bearer = HTTPBearer(auto_error=False, description="Bearer <access_token>")


def create_access_token(user_id: int) -> tuple[str, int]:
    """签发访问令牌，返回 (token, 有效期秒数)。

    有效期秒数一并返回给路由，用作响应里的 expires_in——
    让前端不必自己解析 JWT 的 exp。
    """
    expires_in = settings.jwt_expire_days * 24 * 3600
    now = datetime.now(UTC)
    payload = {
        # sub 必须是字符串：PyJWT 会把 sub 原样返回，且对非字符串 sub 有校验，
        # 直接塞 int 会在校验时报错。取回时再 int() 转回来。
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)
    return token, expires_in


def decode_access_token(token: str) -> int:
    """校验令牌并取出 user_id。任何问题都抛 401，不区分原因。"""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    except jwt.PyJWTError as exc:
        # 过期、签名不符、格式错——对外都只说「令牌无效或已过期」，
        # 具体是哪种对调用方没用，细分反而给攻击者提供反馈。
        raise _unauthorized() from exc

    sub = payload.get("sub")
    if sub is None:
        raise _unauthorized()
    try:
        return int(sub)
    except (TypeError, ValueError) as exc:
        raise _unauthorized() from exc


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="令牌无效或已过期",
        # 带上 WWW-Authenticate 是 HTTP 规范要求，前端 / Swagger 也靠它识别鉴权方式
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> User:
    """鉴权依赖：`user: User = Depends(get_current_user)`。

    拿到的是**数据库里的** User 对象而不是 token 里的 id，原因是
    账号可能在这张令牌签发之后被删掉。查库多一次往返，换来的是
    「令牌有效但用户已不存在」不会变成一个幽灵身份。
    """
    if creds is None:
        # 请求头缺失或不是 Bearer 前缀；HTTPBearer 已经帮我们把这两种情况
        # 归并成 credentials=None
        raise _unauthorized()

    user_id = decode_access_token(creds.credentials)
    user = await session.get(User, user_id)
    if user is None:
        raise _unauthorized()
    return user
