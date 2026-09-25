"""用户模块的业务编排。

两个约定值得留意：

1. **归一化一律发生在查库之前**（`normalize_phone` 是第一行）。
   `users.phone` 上有 partial unique index，同一个号以两种写法入库就是两个账号。

2. **建号发生在验证码校验通过之后**，不是之前。否则任何人拿着任意手机号
   连点发送验证码，就能批量建出空账号。校验通过才写库，
   意味着「能建号」等价于「能收到短信」，这是这个流程唯一的所有权证明。
"""

import logging
import secrets

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.user.code.code_store import CodeStore, VerifyResult
from app.api.user.code.phone import InvalidPhoneError, normalize_phone
from app.api.user.schemas import (
    LoginResponse,
    MeResponse,
    SendCodeResponse,
    UserInfo,
)
from app.api.user.code.sms import SmsSender
from app.db.models.user import User
from app.security import create_access_token
from app.settings import settings

logger = logging.getLogger(__name__)


def _normalized(raw: str) -> str:
    """归一化并校验；非法输入转成 422（与 pydantic 校验失败的语义一致）。"""
    try:
        return normalize_phone(raw)
    except InvalidPhoneError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="手机号格式不正确",
        ) from exc


async def send_code(
    raw_phone: str,
    *,
    store: CodeStore,
    sender: SmsSender,
) -> SendCodeResponse:
    """生成并下发验证码。

    刻意**不**检查手机号是否已注册：响应形态对「已注册」和「未注册」完全一致，
    否则这个接口就成了注册用户探测器。真实业务的注册/登录分流也不依赖这里，
    而是靠 /user/login 的 is_new 字段。
    """
    phone = _normalized(raw_phone)

    if await store.is_cooling_down(phone):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"发送过于频繁，请 {settings.sms_resend_cooldown_seconds} 秒后再试",
            headers={"Retry-After": str(settings.sms_resend_cooldown_seconds)},
        )

    # secrets 而非 random：random 的种子可预测，验证码是可被枚举的短字符串，
    # 用可预测随机数等于把「撞码」从 10^6 次降到几次。
    code = f"{secrets.randbelow(1_000_000):06d}"

    await store.issue(phone, code)
    await sender.send_code(phone, code)

    return SendCodeResponse(
        phone=phone,
        expires_in=settings.sms_code_ttl_seconds,
        # 仅 debug 下回显，生产恒为 None
        code=code if settings.debug else None,
    )


async def login_or_register(
    raw_phone: str,
    code: str,
    *,
    store: CodeStore,
    session: AsyncSession,
) -> LoginResponse:
    """校验验证码；手机号没注册过就建号，注册过就直接登录。

    返回的 is_new 让前端能区分「刚注册」和「回来了」，而不用额外发一个
    「该号是否已注册」的探测请求。
    """
    phone = _normalized(raw_phone)

    result = await store.verify(phone, code)
    if result == VerifyResult.TOO_MANY:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="验证码错误次数过多，请重新获取",
        )
    if result != VerifyResult.OK:
        # MISMATCH（码错）和 EXPIRED（不存在/已过期/已用过）返回同一句话：
        # 区分开等于告诉攻击者「这个号确实刚发过码，继续试」。
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="验证码错误或已失效",
        )

    user = await session.scalar(select(User).where(User.phone == phone))
    is_new = user is None

    if user is None:
        user = User(phone=phone)
        session.add(user)
        try:
            await session.commit()
        except IntegrityError:
            # 同一号两个请求同时走到这里，其中一个会撞上 uq_users_phone 唯一索引。
            # 这不是错误状态——回滚后按「已注册」重查一次即可。
            await session.rollback()
            user = await session.scalar(select(User).where(User.phone == phone))
            if user is None:
                # 唯一索引冲突却不是手机号重复（理论上到不了），原样抛出
                raise
            is_new = False
        else:
            await session.refresh(user)

    token, expires_in = create_access_token(user.id)
    logger.info("用户登录 id=%s phone=%s is_new=%s", user.id, phone, is_new)

    return LoginResponse(
        access_token=token,
        expires_in=expires_in,
        user=UserInfo(id=user.id, phone=user.phone, name=user.name, is_new=is_new),
    )


def to_me_response(user: User) -> MeResponse:
    """把 ORM 对象转成 /user/me 的响应。

    User 上有 email / uid / password_hash 等字段，不该出现在响应里——
    所以不直接用 `MeResponse.model_validate(user)`（那要求 model_config
    开 from_attributes 且会把同名字段全带上），而是显式挑字段。
    """
    return MeResponse(
        id=user.id,
        phone=user.phone,
        name=user.name,
        created_at=user.created_at,
    )
