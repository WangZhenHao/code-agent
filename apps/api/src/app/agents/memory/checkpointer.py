"""LangGraph 的会话持久化（PostgreSQL）。

会话 ID 即 thread_id，也是沙箱 Pod 名称与标签的来源。checkpointer 负责把每
个 thread_id 的图状态（messages、分支等）落库，进程重启后还能接着跑。

用 psycopg 的异步连接池，**不是** SQLAlchemy 那个 engine（见 app/db/session.py）：
两者驱动不同、用途不同，各建各的池。这里也**不建业务表**——业务表一律走
Alembic；本模块建的 4 张表由 LangGraph 自己管（见下面 setup() 的说明）。

生命周期由 app/main.py 的 lifespan 驱动：
启动时 init_checkpointer()，退出时 close_checkpointer()。
"""

from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.settings import settings

# 模块级单例，跟 app/redis.py 的 _client 是同一个思路。
_pool: AsyncConnectionPool | None = None
_saver: AsyncPostgresSaver | None = None


def _to_conninfo(url: str) -> str:
    """把 SQLAlchemy 连接串转成 psycopg 认识的 libpq 连接串。

    settings.database_url 形如 `postgresql+asyncpg://...`，那个 `+asyncpg` 是
    SQLAlchemy 的方言标记，libpq 不认，必须摘掉。不改 settings —— 那边给
    SQLAlchemy 用，方言前缀是必需的，两边各取所需。
    """
    return url.replace("+asyncpg", "", 1)


async def _build_saver() -> AsyncPostgresSaver:
    """建池 + 建 saver + 建表。只应由 get_checkpointer() 调用一次。"""
    global _pool, _saver

    # autocommit=True 和 prepare_threshold=0 是硬要求，跟 AsyncPostgresSaver
    # .from_conn_string() 内部给单连接设的参数一致（见 aio.py）。前者是因为
    # checkpointer 自己管事务边界，池再包一层事务会让写入不可见；后者是绕开
    # pgbouncer / 连接复用下的 prepared statement 冲突。
    #
    # open=False + 显式 await open()：不这么写，__init__ 会隐式开池并触发
    # psycopg_pool 的 deprecation 警告，而且建连失败的时机不受控。
    pool = AsyncConnectionPool(
        _to_conninfo(settings.database_url),
        min_size=settings.checkpoint_pool_min_size,
        max_size=settings.checkpoint_pool_max_size,
        timeout=settings.checkpoint_pool_timeout,
        kwargs={"autocommit": True, "prepare_threshold": 0},
        open=False,
    )
    await pool.open()

    saver = AsyncPostgresSaver(conn=pool)

    # setup() 必须由使用者主动调用，LangGraph 不会自动建表。它建 4 张表：
    # checkpoint_migrations / checkpoints / checkpoint_blobs / checkpoint_writes。
    #
    # 这几张表**不归 Alembic 管**，也不会出现在 Base.metadata 里，所以
    # `make db-check` 看不到它们——这是预期行为，不是漏配。别去 alembic 里找。
    #
    # 幂等：方法内部按 checkpoint_migrations 的版本号决定跑哪些 DDL，重复调用
    # 是空操作。多副本同时冷启动理论上可能撞车（版本号那行 INSERT 是主键），
    # 但概率极低且失败即启动失败、由 k8s 重试，所以不加分布式锁。
    await saver.setup()

    _pool, _saver = pool, saver
    return saver


async def get_checkpointer() -> AsyncPostgresSaver:
    """取全局 checkpointer 单例，首次调用时建连建表。

    懒初始化而不是 import 时建，理由同 app/redis.py：要保住「没配数据库也能
    import 应用」的能力；而且建连本身是 async 的，import 期根本做不了。

    并发调用是安全的：asyncio 单线程且 await 之外无让出点，两个协程不会同时
    走到赋值那一步。
    """
    global _saver
    if _saver is None:
        await _build_saver()
    assert _saver is not None  # 给类型检查器看：_build_saver 保证已赋值
    return _saver


async def init_checkpointer() -> AsyncPostgresSaver:
    """启动钩子：由 main.py 的 lifespan 在 yield 之前调用。

    这里是**故意**建连的（而不是等到第一个请求）：数据库连不上就该启动失败，
    deploy/api/index.yaml 是 maxUnavailable: 0 的滚动更新，拿不到健康检查的
    副本会被回滚，好过带病上线、每个请求各失败一次。
    """
    return await get_checkpointer()


async def close_checkpointer() -> None:
    """退出钩子：释放连接池。由 main.py 的 lifespan 在 yield 之后调用。

    不关的话池里的连接会被内核 RST 掉而不是走正常 FIN 挥手——和 app/redis.py
    里那个问题是同一个，滚动更新时表现成偶发 500。
    """
    global _pool, _saver
    if _pool is not None:
        await _pool.close()
    _pool, _saver = None, None
