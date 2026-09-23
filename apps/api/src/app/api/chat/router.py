"""对话接口。

路径用显式的动作名（/chat/create、/chat/list）而不是 REST 风格的
POST /chat + GET /chat，是为了后面加 /chat/stop、/chat/resume 这类
操作时路径形态保持一致。
"""

from fastapi import APIRouter

from app.api.chat.schemas import (
    ChatCreateRequest,
    ChatCreateResponse,
    ChatListResponse,
)
from app.api.chat.service import create_chat, list_chats

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post(
    "/create",
    response_model=ChatCreateResponse,
    summary="新建或复用会话",
    description=(
        "传 `thread_id` 则复用已有会话（turns +1、刷新 updated_at）；"
        "不传则新建一个，返回的 `thread_id` 同时也是 LangGraph 的 thread_id "
        "与沙箱 Pod 标签的来源。\n\n"
        "当前尚未接入模型：只登记会话，不产生模型输出。"
    ),
    responses={422: {"description": "message 为空，或 agent 名非法"}},
)
async def chat_create(req: ChatCreateRequest) -> ChatCreateResponse:
    return create_chat(req)


@router.get(
    "/list",
    response_model=ChatListResponse,
    summary="列出会话",
    description=(
        "按最后活跃时间倒序返回。\n\n"
        "当前存在进程内内存里，进程重启即清空；接入数据库后此行为不变。"
    ),
)
async def chat_list() -> ChatListResponse:
    return list_chats()
