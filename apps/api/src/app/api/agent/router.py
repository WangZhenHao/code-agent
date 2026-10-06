"""Agent 管理接口。"""

from fastapi import APIRouter, Depends

from app.api.chat.schemas import ChatCreateRequest
from app.db.models.user import User
from app.db.session import get_session
from app.security import get_current_user
from sqlalchemy.ext.asyncio import AsyncSession


router = APIRouter(prefix="/agents", tags=["agent"])


@router.post("/talking/{session_id}")
async def talk(
    session_id: str,
    req: ChatCreateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """与 agent 对话。"""
    return user


@router.post("/retalk/{session_id}")
async def retalk(id: str) -> str:
    """与 agent 对话。"""
    return "hello"
