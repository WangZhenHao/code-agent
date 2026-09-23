"""API 路由汇总。

业务路由不带统一前缀，各自在子 router 里定义（如 /chat/create）。
main.py 只 include 这一个 router。
"""

from fastapi import APIRouter

from app.api.agent.router import router as agent_router
from app.api.chat.router import router as chat_router

api_router = APIRouter()
api_router.include_router(chat_router)
api_router.include_router(agent_router)
