"""Agent 管理接口的模型。"""

from pydantic import BaseModel, Field


class AgentInfo(BaseModel):
    name: str = Field(description="agent 标识，传给 /chat/create 的 agent 字段",
                      examples=["general"])
    description: str = Field(description="用途说明", examples=["通用对话"])
    available: bool = Field(
        description="是否已实现；false 表示登记了但调用不生效",
        examples=[True],
    )
