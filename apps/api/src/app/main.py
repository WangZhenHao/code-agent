"""FastAPI 应用入口。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import api_router
from app.redis import close_redis
from app.settings import settings


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """进程启停钩子。

    目前只做一件事：退出时关掉 Redis 连接池（见 app/redis.py）。

    为什么必须显式关：redis-py 的连接池挂在 client 实例上，进程结束时若不 aclose()，
    这些连接会被内核直接 RST 掉而不是走正常的 FIN 挥手。开发期看不出问题，
    生产滚动更新时（deploy/api/index.yaml 是 maxUnavailable: 0）就会有
    若干请求正好卡在被硬断的连接上。以后接 LangGraph checkpointer 之类的
    长连接资源，也都挂在这里。
    """
    yield
    await close_redis()


def create_app() -> FastAPI:
    app = FastAPI(
        title=f"{settings.app_name} API",
        version=__version__,
        summary="对话式代码 Agent 后端（FastAPI + LangGraph）",
        docs_url="/docs",
        debug=settings.debug,
        lifespan=lifespan,
    )

    # 允许的来源由 CODE_AGENT_CORS_ORIGINS 控制（逗号分隔）。
    # 前端 web(3000) / admin(5174) 开发期直连时用得上；
    # 生产走代理同源，可置空。
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)
    return app


app = create_app()


def main() -> None:
    """`uv run code-agent-api` 或 `uv run python -m app.main` 的入口。"""
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    main()
