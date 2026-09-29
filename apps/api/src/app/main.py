"""FastAPI 应用入口。"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.agents.graphs import get_graph
from app.agents.memory import close_checkpointer, init_checkpointer
from app.api import api_router
from app.redis import close_redis
from app.settings import settings


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    """进程启停钩子：管理长连接资源的生命周期。

    启动：建 checkpointer 的连接池（含建表）并编译一次图。
    退出：按**启动的逆序**关掉它们——先关后建的，因为连接池和 Redis client
    之间虽然无依赖，但逆序是不用思考就能保证正确的顺序。

    为什么在这里建连而不是等第一个请求：数据库连不上就该启动失败。
    deploy/api/index.yaml 是 maxUnavailable: 0 的滚动更新，拿不到健康检查的
    副本会被回滚——好过带病上线、让每个请求各失败一次。

    关闭不能省：redis-py 和 psycopg_pool 的连接池都挂在 client 实例上，进程
    结束时若不释放，这些连接会被内核直接 RST 掉而不是走正常的 FIN 挥手。
    开发期看不出问题，生产滚动更新时就会有若干请求正好卡在被硬断的连接上。
    """
    await init_checkpointer()
    # 先把图编译出来，免得第一个请求额外承担一次编译。
    await get_graph()

    yield

    await close_checkpointer()
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
