"""对话接口的请求/响应模型。

注意：流式返回的事件模型不在这里，归 packages/protocol，api 层只做转译。
"""

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

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


class LangchainMessageItem(BaseModel):
    """LangGraph 状态里的一条消息。

    与 MessageItem 不是一回事：那个读的是 messages 表（业务落库的，只有 role/
    parts/status 这些列），这个读的是 checkpointer 里的图状态——同一轮对话，
    粒度更细（每个 checkpoint 一份快照，含工具调用、中间推理），而且**可能比
    messages 表多**：模型跑完但落库那步失败的轮次，库里没有、checkpointer 里有。

    message 原样透出消息对象 model_dump() 的结果，不在这里挑字段：langchain 的
    消息类型（HumanMessage / AIMessage / ToolMessage 等）字段集各不相同，按类型
    写死 schema 只会漏字段、且跟着上游版本变，前端按 type 判分支更稳。
    """

    type: str = Field(description="消息类型，如 human / ai / tool", examples=["ai"])
    message: dict[str, Any] = Field(description="消息对象 model_dump() 的结果，原样透出")


class LangchainCheckpointItem(BaseModel):
    """线程历史里的一个 checkpoint（一次图执行的快照）。"""

    checkpoint_id: str | None = Field(
        default=None,
        description="checkpoint 标识，只透出 config.configurable.checkpoint_id 这一项",
        examples=["1ef7b3d2-8a44-6b01-93aa-2c4f0e7d9b12"],
    )
    step: int = Field(description="该 checkpoint 在执行序列中的步号，越大越新", examples=[4])
    # 本快照累积的全部消息。currentRoundMessages 走 add_messages 收敛，所以是
    # 「到这一步为止」的全量，不是这一步的增量——前端要增量得自己跟上一个比。
    messages: list[LangchainMessageItem]
    # 该快照之后还要执行的节点。空列表即图已终止（走到 END）。
    next: list[str] = Field(default_factory=list, description="下一个待执行的节点")


class LangchainHistoryResponse(BaseModel):
    """线程的 checkpoint 历史。

    **按 checkpoint 从新到旧**返回，与 graph.get_state_history 的顺序一致——
    最新的那条（当前状态）在最前，而不是按时间正序。

    total 是本次返回的快照条数，不是消息条数。
    """

    data: list[LangchainCheckpointItem]
    total: int = Field(description="checkpoint 快照条数", examples=[6])
