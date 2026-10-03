"""对话接口的请求/响应模型。

注意：流式返回的事件模型不在这里，归 packages/protocol，api 层只做转译。
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

class AttachmentType(StrEnum):
    image = "image"
    file = "file"


class Part(BaseModel):
    """一条消息里除文本外的附加内容。"""

    type: AttachmentType = Field(
        description="附件类型",
        examples=["image", "file"],
    )
    url: str = Field(
        min_length=1,
        description="附件地址，沙箱内读得到或 api 能拉取的 URL",
        examples=["https://example.com/a.png"],
    )


class ChatCreateRequest(BaseModel):
    message: str = Field(
        min_length=1,
        description="用户这一轮说的话",
        examples=["帮我写个快排"],
    )
    mode: str = Field(
        default="agent",
        description="用哪个 agent，见 /agents",
        examples=["agent", "plan"],
    )
    parts: list[Part] = Field(
        default_factory=list,
        description="附加内容，按顺序跟在 message 后面",
        examples=[[{"type": "image", "url": "https://example.com/a.png"}]],
    )


class ChatCreateResponse(BaseModel):
    thread_id: str = Field(examples=["e9394c054c9641e8981ca78b99b70dde"])
    title: str = Field(examples=["帮我写个快排"])
    agent: str = Field(examples=["general"])
    # 会话状态码，见 app.db.models.session.SessionStatus：0=已删除，1=进行中
    status: int = Field(examples=[1])
    created_at: datetime


class ChatSession(BaseModel):
    thread_id: str = Field(examples=["e9394c054c9641e8981ca78b99b70dde"])
    title: str = Field(examples=["帮我写个快排"])
    agent: str = Field(examples=["general"])
    # 会话状态码，见 app.db.models.session.SessionStatus：0=已删除，1=进行中
    status: int = Field(examples=[1])
    turns: int = Field(description="累计轮数", examples=[2])
    created_at: datetime
    updated_at: datetime = Field(description="最后活跃时间，列表按它倒序")


class ChatListResponse(BaseModel):
    items: list[ChatSession]
    total: int = Field(description="会话总数", examples=[2])
