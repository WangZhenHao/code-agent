"""验证码存储：Redis 实现（生产）+ 内存实现（本地/测试）。

**为什么不用进程内存当默认**：根 README 把「API 无状态」列为核心约定，
deploy/api/index.yaml 也是 `replicas: 2`。多副本下请求被负载均衡打到任意 Pod，
A Pod 发的码 B Pod 查不到，用户看到的是「随机提示验证码错误」——
比直接报错更难查。所以线上必须走 Redis。

**为什么还要留内存实现**：本地只是想跑通注册登录、不想起 Redis 时，
用 MemoryCodeStore 就够了。两者实现同一个 CodeStore 协议，上层无感。

**验证码只存 sha256 摘要，不存明文**。验证码是 6 位数字、TTL 五分钟，
本身不是长期秘密；但 Redis 的 RDB 快照、AOF、`MONITOR` 输出都可能被拿到，
存明文等于把「当下谁都还没用掉的有效验证码」白送。摘要比对成本可以忽略。

存明文还是摘要的决定不影响接口，只影响 store 内部，所以以后要换成
HMAC（加 pepper 防彩虹表）也只需改这里——6 位数字的搜索空间太小，
真要说 sha256 能挡住有心人是不诚实的，它的价值在于挡住顺手看一眼。
"""

import hashlib
import time
from typing import Protocol

from redis.asyncio import Redis

from app.settings import settings

CODE_KEY = "sms:code:{phone}"
COOLDOWN_KEY = "sms:cooldown:{phone}"
ATTEMPTS_KEY = "sms:attempts:{phone}"


def _digest(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


class VerifyResult:
    """校验结果的取值，用常量而非枚举，避免上层多 import 一层。"""

    OK = "ok"
    MISMATCH = "mismatch"
    EXPIRED = "expired"  # 不存在 / 已过期 / 已用过 / 失败次数超限作废
    TOO_MANY = "too_many"


class CodeStore(Protocol):
    """验证码的存取。所有方法都按「手机号」这个维度隔离。"""

    async def is_cooling_down(self, phone: str) -> bool:
        """同号是否还在重发冷却期内。"""
        ...

    async def issue(self, phone: str, code: str) -> None:
        """写入验证码并开始冷却计时，同时清掉历史失败次数。"""
        ...

    async def verify(self, phone: str, code: str) -> str:
        """校验并**消费**验证码：成功即删除（单次使用）。

        返回 VerifyResult 里的某个常量。失败时累加失败次数，
        超过 settings.sms_max_attempts 就把该码作废。
        """
        ...


# 校验动作必须原子：读 → 比对 → 删除/计数，中间不能让第二个请求插进来，
# 否则同一个码可以被并发请求重复消费。所以逻辑写在 Lua 里，
# 由 Redis 单线程串行执行。
_VERIFY_LUA = """
local code_key = KEYS[1]
local attempts_key = KEYS[2]
local max_attempts = tonumber(ARGV[1])
local ttl = tonumber(ARGV[2])
local digest = ARGV[3]

local stored = redis.call('GET', code_key)
if not stored then
  return 'expired'
end

if stored == digest then
  redis.call('DEL', code_key)
  redis.call('DEL', attempts_key)
  return 'ok'
end

local n = redis.call('INCR', attempts_key)
-- 只在第一次设置过期，避免每次失败都把作废时间往后推
if n == 1 then
  redis.call('EXPIRE', attempts_key, ttl)
end
if n >= max_attempts then
  redis.call('DEL', code_key)
  return 'too_many'
end
return 'mismatch'
"""


class RedisCodeStore:
    """生产实现。TTL 全部交给 Redis，进程重启不丢。"""

    def __init__(self, client: Redis) -> None:
        self._redis = client
        self._verify = self._redis.register_script(_VERIFY_LUA)

    async def is_cooling_down(self, phone: str) -> bool:
        return bool(await self._redis.exists(COOLDOWN_KEY.format(phone=phone)))

    async def issue(self, phone: str, code: str) -> None:
        ttl = settings.sms_code_ttl_seconds
        pipe = self._redis.pipeline()
        pipe.set(CODE_KEY.format(phone=phone), _digest(code), ex=ttl)
        pipe.set(
            COOLDOWN_KEY.format(phone=phone),
            "1",
            ex=settings.sms_resend_cooldown_seconds,
        )
        # 重新发码时清掉旧计数：上一轮的失败次数不该影响这一轮的码
        pipe.delete(ATTEMPTS_KEY.format(phone=phone))
        await pipe.execute()

    async def verify(self, phone: str, code: str) -> str:
        result = await self._verify(
            keys=[CODE_KEY.format(phone=phone), ATTEMPTS_KEY.format(phone=phone)],
            args=[
                settings.sms_max_attempts,
                settings.sms_code_ttl_seconds,
                _digest(code),
            ],
        )
        # redis-py 返回 bytes
        return result.decode() if isinstance(result, bytes) else result


class MemoryCodeStore:
    """本地/测试实现：dict + 过期时间戳。

    刻意实现得「够用就好」：单进程、无锁、不做淘汰。
    它的作用是让本地不装 Redis 也能跑通流程，不是给生产用的第二选择。
    """

    def __init__(self) -> None:
        self._codes: dict[str, tuple[str, float]] = {}
        self._cooldowns: dict[str, float] = {}
        self._attempts: dict[str, int] = {}

    def _alive(self, key: str) -> bool:
        entry = self._codes.get(key)
        if entry is None:
            return False
        if entry[1] < time.monotonic():
            del self._codes[key]
            return False
        return True

    async def is_cooling_down(self, phone: str) -> bool:
        deadline = self._cooldowns.get(phone)
        if deadline is None:
            return False
        if deadline < time.monotonic():
            del self._cooldowns[phone]
            return False
        return True

    async def issue(self, phone: str, code: str) -> None:
        now = time.monotonic()
        self._codes[phone] = (
            _digest(code),
            now + settings.sms_code_ttl_seconds,
        )
        self._cooldowns[phone] = now + settings.sms_resend_cooldown_seconds
        self._attempts.pop(phone, None)

    async def verify(self, phone: str, code: str) -> str:
        if not self._alive(phone):
            return VerifyResult.EXPIRED

        if self._codes[phone][0] == _digest(code):
            del self._codes[phone]
            self._attempts.pop(phone, None)
            return VerifyResult.OK

        n = self._attempts.get(phone, 0) + 1
        self._attempts[phone] = n
        if n >= settings.sms_max_attempts:
            self._codes.pop(phone, None)
            self._attempts.pop(phone, None)
            return VerifyResult.TOO_MANY
        return VerifyResult.MISMATCH


# 单例。Redis 客户端自己管连接池，每次请求新建会漏连接。
_redis_client: Redis | None = None
_store: CodeStore | None = None


def get_code_store() -> CodeStore:
    """FastAPI 依赖：`store: CodeStore = Depends(get_code_store)`。

    默认用 Redis（settings.redis_url 指向 docker-compose 里的实例）。
    本地想免 Redis 时改这里返回 MemoryCodeStore() 即可——
    这也是为什么所有实现都藏在 CodeStore 协议后面。
    """
    global _redis_client, _store
    if _store is None:
        _redis_client = Redis.from_url(settings.redis_url, decode_responses=False)
        _store = RedisCodeStore(_redis_client)
    return _store


async def close_code_store() -> None:
    """进程退出时释放连接池，挂到 main.py 的 lifespan 上。"""
    global _redis_client, _store
    if _redis_client is not None:
        await _redis_client.aclose()
    _redis_client = None
    _store = None
