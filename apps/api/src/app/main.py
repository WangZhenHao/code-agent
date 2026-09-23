"""FastAPI 应用入口。"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import api_router
from app.settings import settings


def create_app() -> FastAPI:
    app = FastAPI(
        title=f"{settings.app_name} API",
        version=__version__,
        summary="对话式代码 Agent 后端（FastAPI + LangGraph）",
        docs_url="/docs",
        redoc_url="/redoc",
        debug=settings.debug,
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
