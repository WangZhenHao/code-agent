"""Alembic 运行时环境。

连接串不写在 alembic.ini 里，而是复用 app 的配置（CODE_AGENT_DATABASE_URL），
本地 / CI / 生产同一份代码，只靠环境变量切换。

注意 import 顺序：`app` 在 src/ 下，不是装到 site-packages 的顶层包也差不多
（uv_build 以 src 为 module-root），所以这里靠 alembic.ini 的
`prepend_sys_path = .` + 下面的 sys.path 兜底，保证 `import app` 可用。
"""

import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# 兜底：允许从任意目录执行 `alembic`（例如仓库根目录 make db-migrate）
_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from app.db.base import Base  # noqa: E402
from app.db.models import *  # noqa: E402,F401,F403  —— 触发全部模型注册
from app.settings import settings  # noqa: E402

config = context.config

# 用 app 的配置覆盖 ini 里的占位值。URL 里的特殊字符（密码中的 @ / # 等）
# 由 asyncpg 的 URL 解析处理，这里不做字符串拼接。
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线模式：只渲染 SQL，不连库（`alembic upgrade head --sql`）。"""
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        include_schemas=False,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # 打开类型/默认值比对，否则改 VARCHAR 长度、改 server_default
        # 这类变更 autogenerate 会漏掉
        compare_type=True,
        compare_server_default=True,
        include_schemas=False,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
