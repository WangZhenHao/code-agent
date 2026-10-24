"""Agent / Thread 接口的请求与响应模型。"""

from pydantic import BaseModel, Field


class AgentInfo(BaseModel):
    name: str = Field(description="agent 标识，传给 /chat/create 的 agent 字段",
                      examples=["general"])
    description: str = Field(description="用途说明", examples=["通用对话"])
    available: bool = Field(
        description="是否已实现；false 表示登记了但调用不生效",
        examples=[True],
    )


class SubscribeParams(BaseModel):
    """`/threads/{session_id}/stream` 的订阅参数（Agent Streaming Protocol）。

    全部可省：默认订阅所有通道、从缓冲开头回放。字段语义见
    app/agents/threading/protocol.py 的 `matches_subscription` 与
    `is_after_replay_cursor`。
    """

    channels: list[str] | None = Field(
        default=None,
        description="要订阅的通道；空/缺省表示全部。填 `custom` 会同时匹配所有 `custom:*`",
        examples=[["messages", "tools", "lifecycle"]],
    )
    namespaces: list[list[str]] | None = Field(
        default=None,
        description="命名空间前缀过滤（逐段匹配）；缺省不按命名空间过滤",
        examples=[[["codeAgent:uuid"]]],
    )
    depth: int | None = Field(
        default=None,
        description="前缀之外最多允许的层级；配合 namespaces 使用",
        examples=[2],
    )
    since: int | None = Field(
        default=None,
        description="回放游标（事件的 seq）。只回放 seq 更大的事件；缺省回放全部",
        examples=[41],
    )


class CommandResponse(BaseModel):
    """`/threads/{session_id}/commands` 的响应。"""

    type: str = Field(default="success", examples=["success"])
    id: str | None = Field(
        default=None, description="客户端命令 id；本实现不解析命令信封，固定为 null"
    )
    result: dict = Field(
        description="run 信息",
        examples=[{"run_id": "2f1c9a1e-..."}],
    )


class AbortResponse(BaseModel):
    """中止结果。false 表示当时没有在跑的 run（已结束，不是错误）。"""

    aborted: bool = Field(examples=[True])
