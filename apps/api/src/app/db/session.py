"""数据库连接：async engine + session 工厂 + FastAPI 依赖。

连接串来自 settings.database_url（即 .env 的 CODE_AGENT_DATABASE_URL），
已经带 `+asyncpg` 驱动，所以这里不需要再改写 URL。

本模块不建表：表结构一律走 Alembic（见 apps/api/alembic/）。
"""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.settings import settings

# echo 跟随 CODE_AGENT_DEBUG：debug 时把 SQL 打到日志里，方便本地排错。
# pool_pre_ping 防连接被中间件/超时掐死后拿到坏连接。
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
)

# expire_on_commit=False：commit 之后对象不过期，路由里可以继续读字段而不用
# 再发一次 SELECT。对「返回刚创建的对象」这种场景是必需的。
SessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI 依赖：`session: AsyncSession = Depends(get_session)`。

    只负责开关会话，不自动 commit——写操作由调用方（service 层）显式 commit，
    这样一次请求里多个写操作的边界是清楚的。
    """
    async with SessionLocal() as session:
        yield session
