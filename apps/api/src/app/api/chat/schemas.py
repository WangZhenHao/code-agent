"""对话接口的请求/响应模型。

注意：流式返回的事件模型不在这里，归 packages/protocol，api 层只做转译。
"""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.session import MessageMode
from langchain.messages import ContentBlock


class ChatCreateRequest(BaseModel):

    model: str = Field(
        default="deepseek-v4-flash",
        description="模型名称",
        examples=["deepseek-v4-flash", "deepseek-v4-pro"],
    )

    mode: MessageMode = Field(
        default=MessageMode.agent,
        description="用哪个 agent，见 /agents",
        examples=["agent", "plan"],
    )
    parts: list[ContentBlock] = Field(
        default_factory=list,
        description="附加内容，按顺序跟在 message 后面",
        examples=[[{"type": "text", "content": "帮我写个快排"}]],
    )


class ChatCreateResponse(BaseModel):
    id: str = Field(examples=["e9394c054c9641e8981ca78b99b70dde"])
    title: str = Field(examples=["帮我写个快排"])
    agent: str = Field(examples=["general"])
    # 会话状态码，见 app.db.models.session.SessionStatus：0=已删除，1=进行中
    status: int = Field(examples=[1])
    created_at: datetime


class MessageItem(BaseModel):
    """一条消息。对应 Messages 表的字段，parts 原样透出。"""
    model_config = ConfigDict(from_attributes=True)
    
    id: str = Field(examples=["an1hhebbsm8n"])
    role: str = Field(description="user / assistant / error", examples=["user"])
    status: str = Field(description="complete / interrupted", examples=["complete"])
    model: str = Field(examples=["deepseek-v4-flash"])
    mode: MessageMode = Field(examples=["agent"])
    parts: list[ContentBlock] | None = Field(
        default=None,
        description="消息内容片段",
        examples=[[{"type": "text", "content": "帮我写个快排"}]],
    )
    duration: int | None = Field(default=None, description="这一轮耗时，毫秒")
    created_at: datetime


class MessageListResponse(BaseModel):
    data: list[MessageItem]
    total: int = Field(description="消息总数", examples=[2])


class ChatDetailResponse(BaseModel):
    """一个会话的详情。对应 Session 表的列，id 即 LangGraph thread_id。

    不复用 ChatCreateResponse：那个是"刚建出来的会话"的摘要（id/title/agent/
    status/created_at），故意窄；详情要带预览、git 这些会话全貌，字段集不一样。
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(examples=["e9394c054c9641e8981ca78b99b70dde"])
    title: str = Field(examples=["帮我写个快排"])
    title_image: str | None = Field(default=None, description="封面图 URL")
    description: str | None = Field(default=None, description="会话描述")

    # 会话状态码，见 app.db.models.session.SessionStatus：0=已删除，1=进行中
    status: int = Field(examples=[1])
    publish: int = Field(default=0, description="是否已发布")
    views: int = Field(default=0, description="浏览量")

    preview_port: int | None = Field(default=None)
    preview_status: str = Field(default="idle", examples=["idle"])
    preview_url: str | None = Field(default=None)

    git_repo_name: str | None = Field(default=None)
    git_repo_url: str | None = Field(default=None)

    created_at: datetime
    updated_at: datetime




class ChatDeleteResponse(BaseModel):
    """删除会话的响应。

    带 status 而不是空响应：前端拿到就能直接更新本地那条记录（标灰/移出列表），
    不必再拉一次列表或详情。值恒为 SessionStatus.delete（0）。
    """

    id: str = Field(examples=["e9394c054c9641e8981ca78b99b70dde"])
    # 会话状态码，见 app.db.models.session.SessionStatus：0=已删除，1=进行中
    status: int = Field(examples=[0])
