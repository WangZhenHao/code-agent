"""Agent 管理接口。"""

from fastapi import APIRouter

from app.api.agent.schemas import AgentInfo
from app.api.agent.service import list_agents

router = APIRouter(prefix="/agents", tags=["agent"])


@router.get(
    "",
    response_model=list[AgentInfo],
    summary="列出可用 agent",
    description=(
        "返回 agent 注册表。`available=false` 表示该 agent 已登记但尚未实现，"
        "调用 `/chat/create` 时传它的 `name` 不会生效。"
    ),
)
async def get_agents() -> list[AgentInfo]:
    return list_agents()
