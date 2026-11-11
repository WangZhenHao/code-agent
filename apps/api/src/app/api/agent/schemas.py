"""Agent / Thread 接口的请求与响应模型。"""

from pydantic import BaseModel, Field


class AgentInfo(BaseModel):
    name: str = Field(
        description="agent 标识，传给 /chat/create 的 agent 字段", examples=["general"]
    )
    description: str = Field(description="用途说明", examples=["通用对话"])
    available: bool = Field(
        description="是否已实现；false 表示登记了但调用不生效",
        examples=[True],
    )


class SubscribeParams(BaseModel):
    """`/threads/{session_id}/stream` 的订阅参数（Agent Streaming Protocol）。

    全部可省：默认订阅所有通道、从缓冲开头回放。字段语义见
    app/agents/threading/_protocol/events.py 的 `matches_subscription` 与
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


class ThreadStateResponse(BaseModel):
    """`GET /threads/{session_id}/state` 的响应，形状对齐 LangGraph SDK 的 `ThreadState`。

    **故意不带 `values.messages`**：checkpoint 里的消息是 agent 的工作上下文，
    可能已被摘要压缩；用户可见的完整历史由 `GET /chat/message/{id}` 提供。
    两者混用会把压缩摘要漏进对话列表。

    SDK 的 `isThreadStateActive` 只看两个字段：
    - `next`：非空数组 ⇒ 图还在跑；
    - `tasks`：任一 task 带非空 `interrupts` ⇒ 等人输入（也视为活跃）。
    所以 idle 时必须显式给 `next: []`——字段缺失会被当成「非数组 ⇒ 活跃」。
    """

    values: dict = Field(
        default_factory=dict,
        description="图状态。本实现故意只给空对象，历史走 /chat/message/{id}",
    )
    next: list[str] = Field(
        default_factory=list,
        description="还有待执行节点的名称；空数组表示本轮已结束",
        examples=[[], ["codeAgent"]],
    )
    tasks: list[dict] = Field(
        default_factory=list,
        description="当前任务的 interrupt 快照；本实现暂不产生中断",
    )
    created_at: str | None = Field(
        default=None,
        description="会话创建时间（ISO 8601）",
        examples=["2026-11-09T10:00:00+08:00"],
    )


class ToolCallResponse(BaseModel):
    """`GET /agents/{session_id}/tools/{tool_call_id}` 的响应。

    SSE 的 `tool-finished` 只带 `tool_call_id` 和状态，工具输出由前端按 id
    查这个接口拿（见 app/agents/helper/tool_recorder.py）。
    """

    tool_call_id: str = Field(description="LangChain 的工具调用 id（call_xxx）")
    tool_name: str = Field(description="工具名", examples=["bash"])
    status: str = Field(
        description="工具调用状态：running / success / error / interrupted",
        examples=["success"],
    )
    input: dict | list | None = Field(
        default=None, description="模型给出的调用参数", examples=[{"command": "ls"}]
    )
    output: str | None = Field(
        default=None,
        description="工具返回文本；running 或 interrupted 时可能为空",
        examples=["README.md\nsrc\n"],
    )
