"""对话接口。

路径用显式的动作名（/chat/create、/chat/list）而不是 REST 风格的
POST /chat + GET /chat，是为了后面加 /chat/stop、/chat/resume 这类
操作时路径形态保持一致。
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.chat.schemas import (
    ChatCreateRequest,
    ChatCreateResponse,
    MessageListResponse,
)
from app.api.chat.service import chat_message, create_chat
from app.db.models.user import User
from app.db.session import get_session
from app.security import get_current_user

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post(
    "/create",
    response_model=ChatCreateResponse,
    summary="新建或复用会话",
    responses={422: {"description": "message 为空，或 agent 名非法"}},
)
async def chat_create(req: ChatCreateRequest,
                      user: User = Depends(get_current_user),
                      session: AsyncSession = Depends(get_session)
                      ):
    return await create_chat(req, user_id=user.id, session=session)


@router.get(
    "/message/{id}",
    response_model=MessageListResponse,
    summary="获取会话消息",
    responses={404: {"description": "会话不存在或不属于当前用户"}},
)
async def message(id: str,
                  user: User = Depends(get_current_user),
                  session: AsyncSession = Depends(get_session)
                  ):
    """获取会话消息，按时间正序。"""
    return await chat_message(id, user.id, session)


