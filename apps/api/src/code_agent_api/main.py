"""FastAPI 应用入口。"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from code_agent_api import __version__
from code_agent_api.settings import settings


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        debug=settings.debug,
    )

    # 前端 web(3000) / admin(5174) 开发期直连时用得上；
    # admin 生产是走 nginx 反代同源，不依赖这里。
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://localhost:5174",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/healthz", tags=["meta"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    return app


app = create_app()


def main() -> None:
    """`uv run code-agent-api` 或 `uv run python -m code_agent_api.main` 的入口。"""
    import uvicorn

    uvicorn.run(
        "code_agent_api.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    main()
