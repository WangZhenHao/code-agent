"""用户接口：手机号 + 验证码登录注册，以及一个受保护的示例接口。

路径沿用 chat 模块的显式动作名风格（/user/send_code、/user/login），
不用 REST 风格的 POST /user + GET /user。
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.user.code.code_store import CodeStore, get_code_store
from app.api.user.schemas import (
    LoginRequest,
    LoginResponse,
    MeResponse,
    SendCodeRequest,
    SendCodeResponse,
)
from app.api.user.service import login_or_register, send_code, to_me_response
from app.api.user.code.sms import SmsSender, get_sms_sender
from app.db.models.user import User
from app.db.session import get_session
from app.security import get_current_user

router = APIRouter(prefix="/user", tags=["user"])


@router.post(
    "/send_code",
    response_model=SendCodeResponse,
    summary="发送短信验证码",
    description=(
        "给手机号下发一条 6 位验证码，同一号码 60 秒内不可重发。\n\n"
        "**不区分手机号是否已注册**——响应形态完全一致，"
        "避免这个接口被用来探测某个号是否注册过。\n\n"
        "`CODE_AGENT_DEBUG=true` 时响应里的 `code` 会带上验证码本身，"
        "方便本地联调；生产恒为 `null`，只走短信。"
    ),
    responses={
        422: {"description": "手机号格式不正确"},
        429: {"description": "重发冷却中，响应头带 `Retry-After`"},
    },
)
async def user_send_code(
    req: SendCodeRequest,
    store: CodeStore = Depends(get_code_store),
    sender: SmsSender = Depends(get_sms_sender),
) -> SendCodeResponse:
    return await send_code(req.phone, store=store, sender=sender)


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="登录 / 注册（合一）",
    description=(
        "手机号 + 验证码。号码没注册过则**自动建号**，注册过则直接登录，"
        "前端无需区分两个流程。\n\n"
        "用响应里的 `user.is_new` 判断本次是否新建了账号。\n\n"
        "验证码校验通过后立即失效（单次使用）。同一验证码连续校验失败 5 次即作废，"
        "需重新获取。"
    ),
    responses={
        400: {
            "description": (
                "验证码错误，或不存在 / 已过期 / 已使用 / 已因失败次数过多而作废。"
                "这几种情况响应完全一致，不区分——区分开等于告诉攻击者"
                "「这个号确实刚发过码，继续试」"
            )
        },
        422: {"description": "手机号格式不正确"},
        429: {"description": "本次校验使失败次数达到上限，验证码已作废，请重新获取"},
    },
)
async def user_login(
    req: LoginRequest,
    store: CodeStore = Depends(get_code_store),
    session: AsyncSession = Depends(get_session),
) -> LoginResponse:
    return await login_or_register(req.phone, req.code, store=store, session=session)


@router.get(
    "/me",
    response_model=MeResponse,
    summary="当前登录用户",
    description=(
        "鉴权示例接口。请求头带 `Authorization: Bearer <access_token>`，"
        "返回该令牌对应的用户。\n\n"
        "其它模块要给接口加鉴权时，在路由函数签名里加一行"
        "`user: User = Depends(get_current_user)` 即可。"
    ),
    responses={
        401: {"description": "缺少令牌，或令牌无效 / 已过期 / 用户已不存在"},
    },
)
async def user_me(user: User = Depends(get_current_user)) -> MeResponse:
    return to_me_response(user)
