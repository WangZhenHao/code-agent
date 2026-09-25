"""用户模块的请求/响应模型。

手机号的格式校验放在同目录的 phone.py 而不是这里的 pydantic 校验器：
归一化必须在查库前发生，且 service 层也要能调用同一份逻辑。
这里只保证「字段存在且非空」，格式不对由路由转成 422。
"""

from datetime import datetime

from pydantic import BaseModel, Field

_PHONE_EXAMPLE = "13800138000"


class SendCodeRequest(BaseModel):
    phone: str = Field(
        min_length=1,
        max_length=32,
        description="手机号，接受 13800138000 / +8613800138000 等写法，落库前会归一化",
        examples=[_PHONE_EXAMPLE],
    )


class SendCodeResponse(BaseModel):
    phone: str = Field(description="归一化后的手机号", examples=[_PHONE_EXAMPLE])
    expires_in: int = Field(description="验证码有效期（秒）", examples=[300])
    code: str | None = Field(
        default=None,
        description=(
            "开发便利字段：仅 `CODE_AGENT_DEBUG=true` 时返回验证码本身，"
            "生产恒为 null。生产环境验证码只会走短信，接口不泄漏。"
        ),
        examples=["483920", None],
    )


class LoginRequest(BaseModel):
    phone: str = Field(
        min_length=1,
        max_length=32,
        description="手机号，需与发验证码时同一个（归一化后一致即可）",
        examples=[_PHONE_EXAMPLE],
    )
    code: str = Field(
        min_length=1,
        max_length=16,
        description="收到的验证码",
        examples=["483920"],
    )


class UserInfo(BaseModel):
    id: int = Field(examples=[1])
    phone: str | None = Field(examples=[_PHONE_EXAMPLE])
    name: str | None = Field(examples=[None])
    is_new: bool = Field(
        default=False,
        description="本次请求是否新建了账号；老用户登录为 false",
        examples=[True],
    )


class LoginResponse(BaseModel):
    access_token: str = Field(description="JWT，放进 `Authorization: Bearer <token>`")
    token_type: str = Field(default="bearer", examples=["bearer"])
    expires_in: int = Field(description="令牌有效期（秒）", examples=[604800])
    user: UserInfo


class MeResponse(BaseModel):
    id: int = Field(examples=[1])
    phone: str | None = Field(examples=[_PHONE_EXAMPLE])
    name: str | None = Field(examples=[None])
    created_at: datetime = Field(description="注册时间")
