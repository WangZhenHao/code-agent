"""对话接口的请求/响应模型。

注意：流式返回的事件模型不在这里，归 packages/protocol，api 层只做转译。
"""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

class AttachmentType(StrEnum):
    image = "image"
    file = "file"

# 分类结果。
#
# 注意与节点名的错位：mode == "plan" 走的是 planAgent 节点，
# mode == "agent" 走的是 codeAgent 节点。"agent" 这个词描述的是
# "直接动手改代码"这一档，而不是"进入某个 agent"——所有节点都是 agent。
# 值域必须与 graphs.py 里 add_conditional_edges 的映射表逐字一致。
Branch = Literal["plan", "agent"]

class Part(BaseModel):
    """一条消息里除文本外的附加内容。"""

    type: AttachmentType = Field(
        description="附件类型",
        examples=["image", "file"],
    )
    content: str = Field(
        min_length=1,
        description="附件地址，沙箱内读得到或 api 能拉取的 URL",
        examples=["https://example.com/a.png"],
    )
class PartText(BaseModel):
    type: str = "text"

    content: str = Field(
        min_length=1,
        description="文本内容",
        examples=["请写一个快排"],
    )



class ChatCreateRequest(BaseModel):

    model: str = Field(
        default="deepseek-v4-flash",
        description="模型名称",
        examples=["deepseek-v4-flash", "deepseek-v4-pro"],
    )

    mode: Branch = Field(
        default="agent",
        description="用哪个 agent，见 /agents",
        examples=["agent", "plan"],
    )
    parts: list[PartText | Part] = Field(
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
    mode: Branch = Field(examples=["agent"])
    parts: list[Part | PartText] | None = Field(
        default=None,
        description="消息内容片段",
        examples=[[{"type": "text", "content": "帮我写个快排"}]],
    )
    duration: int | None = Field(default=None, description="这一轮耗时，毫秒")
    created_at: datetime


class MessageListResponse(BaseModel):
    data: list[MessageItem]
    total: int = Field(description="消息总数", examples=[2])


