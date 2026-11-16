from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.agents.helper.agent_prompt import meta_data_system_prompt


class TitleOutput(BaseModel):
    title: str = Field(description="网站标题")
    description: str = Field(description="网站描述")


def create_message(message: str) -> list[BaseMessage]:
    """创建消息列表，包含系统消息和用户消息"""
    return [
        SystemMessage("\n".join(meta_data_system_prompt)),
        HumanMessage(content=message),
    ]
