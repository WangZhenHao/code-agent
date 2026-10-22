"""FastAPI 应用入口。"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.agents.graphs import get_graph
from app.agents.memory import close_checkpointer, init_checkpointer
from app.api.router import api_router
from app.api.sandbox.sweeper import start_sweeper, stop_sweeper
from app.redis import close_redis
from app.settings import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    """进程启停钩子：管理长连接资源的生命周期。

    启动：建 checkpointer 的连接池（含建表）、编译一次图、起预览回收调度器。
    退出：按**启动的逆序**关掉它们——后建的先关，因为连接池和 Redis client
    之间虽然无依赖，但逆序是不用思考就能保证正确的顺序。

    为什么在这里建连而不是等第一个请求：数据库连不上就该启动失败。
    deploy/api/index.yaml 是 maxUnavailable: 0 的滚动更新，拿不到健康检查的
    副本会被回滚——好过带病上线、让每个请求各失败一次。

    关闭不能省：redis-py 和 psycopg_pool 的连接池都挂在 client 实例上，进程
    结束时若不释放，这些连接会被内核直接 RST 掉而不是走正常的 FIN 挥手。
    开发期看不出问题，生产滚动更新时就会有若干请求正好卡在被硬断的连接上。

    调度器同理，且必须显式停：`uvicorn --reload` 下每次重载都是一个新进程，
    不管的话旧进程的调度器会攥着 DB 连接不放。
    """
    await init_checkpointer()
    # 先把图编译出来，免得第一个请求额外承担一次编译。
    await get_graph()
    start_sweeper()

    yield

    stop_sweeper()
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
        # 让 Swagger UI 把「Authorize」里填的 token 落到 localStorage，
        # 否则它只存在页面内存里，刷新一下就没了。
        swagger_ui_parameters={"persistAuthorization": True},
    )

    # 兜住没被处理的异常，返回和 HTTPException 同形状的 {"detail": ...}。
    #
    # 不注册这个的话，未捕获异常会冒到 Starlette 的 ServerErrorMiddleware，
    # 那层**在所有中间件之外**，返回的是不带 CORS 头的纯文本 500。浏览器拿不到
    # Access-Control-Allow-Origin，就把整条响应丢给前端——axios 只能看到
    # "Network Error"，后端 traceback 里写清楚的原因（比如响应模型校验失败）
    # 前端一条都拿不到。这里把 500 变成普通响应，交给外层 CORSMiddleware 补头。
    #
    # 注意注册顺序：add_middleware 是插到列表头部（越晚加的越靠外），所以这个
    # 必须在 CORSMiddleware 之前注册，CORS 才是最外层、才能给这个 500 加头。
    @app.middleware("http")
    async def catch_unhandled_exception(request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as exc:
            logger.exception("unhandled error: %s %s", request.method, request.url.path)
            # 生产不把异常原文给客户端（可能带连接串、SQL、内部路径）；
            # debug 下透出来，本地排查不用回去翻日志。
            detail = f"{type(exc).__name__}: {exc}" if settings.debug else "服务器内部错误"
            return JSONResponse(status_code=500, content={"detail": detail})

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
