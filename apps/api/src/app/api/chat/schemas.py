"""对话接口的请求/响应模型。

注意：流式返回的事件模型不在这里，归 packages/protocol，api 层只做转译。
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class SessionStatus(StrEnum):
    active = "active"
    archived = "archived"


class ChatCreateRequest(BaseModel):
    message: str = Field(
        min_length=1,
        description="用户这一轮说的话",
        examples=["帮我写个快排"],
    )
    thread_id: str | None = Field(
        default=None,
        description="会话 ID；不传则新建。同时也是沙箱 Pod 标签的来源",
        examples=["e9394c054c9641e8981ca78b99b70dde"],
    )
    agent: str = Field(
        default="general",
        description="用哪个 agent，见 /agents",
        examples=["general", "coding"],
    )


class ChatCreateResponse(BaseModel):
    thread_id: str = Field(examples=["e9394c054c9641e8981ca78b99b70dde"])
    title: str = Field(examples=["帮我写个快排"])
    agent: str = Field(examples=["general"])
    status: SessionStatus = Field(examples=["active"])
    created_at: datetime


class ChatSession(BaseModel):
    thread_id: str = Field(examples=["e9394c054c9641e8981ca78b99b70dde"])
    title: str = Field(examples=["帮我写个快排"])
    agent: str = Field(examples=["general"])
    status: SessionStatus = Field(examples=["active"])
    turns: int = Field(description="累计轮数", examples=[2])
    created_at: datetime
    updated_at: datetime = Field(description="最后活跃时间，列表按它倒序")


class ChatListResponse(BaseModel):
    items: list[ChatSession]
    total: int = Field(description="会话总数", examples=[2])
