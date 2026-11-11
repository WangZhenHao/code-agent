"""Redis 连接：client 单例 + FastAPI 依赖 + 生命周期回收。

**这里只给连接，不包命令。** 跟 db/session.py 一样——那层也只给你 engine 和
session，不管你往里面发什么 SQL。Redis 命令上百个（SET/GET/INCR/EXPIRE/
HSET/LPUSH/ZADD/EVAL...），包不全；只包常用的那几个，反而让调用方要猜
「哪些能用现成的、哪些得自己拿 client 写」，不如一开始就统一。

所以 key 的命名前缀（比如验证码的 `sms:`）也归业务方自己带，
这里不做 namespace 约定。

用法：

    from app.redis import get_redis

    async def do_something(redis: Redis = Depends(get_redis)) -> None:
        await redis.set("some:key", "value", ex=60)
"""

from redis.asyncio import Redis

from app.settings import settings

# 模块级单例，跟 db/session.py 的 `engine` 是同一个思路。
# 单例是必须的而不是优化：redis-py 的连接池挂在 client 实例上，
# 每次调用新建一个 client 会各自开池，连接数只增不减。
_client: Redis | None = None


def get_redis() -> Redis:
    """FastAPI 依赖：`redis: Redis = Depends(get_redis)`。

    也允许非路由代码直接 `get_redis()` 调用。

    懒初始化，而不是像 db/session.py 那样在 import 时就建：`create_async_engine`
    只是构造对象不真连库，而这里要保持「没配 Redis 也能 import 应用」的能力
    （以后若把某些功能拆成独立服务，它们不该因为没 Redis 就 import 失败）。
    代价是首次调用才建连接，第一个请求稍慢——这个量级可以接受。

    decode_responses=False：返回 bytes 而非 str，**这是刻意保持的既有行为**。
    要字符串的调用方自己 `.decode()`。不设 True 是为了不挡非 UTF-8 安全的用法
    （二进制值、msgpack、pickle 等），那些在 True 之下会被静默损坏。
    """
    global _client
    if _client is None:
        _client = Redis.from_url(settings.redis_url, decode_responses=False)
    return _client


async def close_redis() -> None:
    """释放连接池。由 main.py 的 lifespan 在进程退出时调用。

    不 aclose() 的话，连接会被内核直接 RST 掉而不是走正常的 FIN 挥手。
    开发期看不出来，但 deploy/api/index.yaml 是 maxUnavailable: 0 的滚动更新，
    每次发版都会有请求正好卡在被硬断的连接上，表现成偶发 500。
    """
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
