"""验证码存储的离线测试。

两件事在这里被验证：

  1. `MemoryCodeStore` 的语义（本地/测试实现）——它是接口行为的参照物，
     冷却、单次消费、失败计数作废这些规则都写在这里；
  2. `RedisCodeStore` 的**协议**（key 名、Lua 脚本参数、字节解码），用假 Redis
     对象断言，不连真 Redis。Lua 脚本本身由 Redis 执行，这里不复刻。

为什么存储层值得单独测：验证码的失效方式全是静默的——同一个码能连用两次、
失败次数不清零、超限不作废，前端看到的都只是"验证码错误"，没人会往这里查。

跑法：uv run python -m unittest tests.api.test_code_store
"""

from __future__ import annotations

import unittest
from unittest import mock

from app.api.user.code.code_store import (
    ATTEMPTS_KEY,
    CODE_KEY,
    COOLDOWN_KEY,
    MemoryCodeStore,
    RedisCodeStore,
    VerifyResult,
    _digest,
)
from app.settings import settings


class MemoryCodeStoreTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.store = MemoryCodeStore()

    async def test_issue_then_verify_ok(self):
        await self.store.issue("13800138000", "123456")
        self.assertEqual(await self.store.verify("13800138000", "123456"), VerifyResult.OK)

    async def test_code_is_single_use(self):
        # 成功校验即删除：同一个码第二次必须当过期处理，否则这就是个万能码。
        await self.store.issue("13800138000", "123456")
        await self.store.verify("13800138000", "123456")
        self.assertEqual(await self.store.verify("13800138000", "123456"), VerifyResult.EXPIRED)

    async def test_mismatch_then_correct_still_ok(self):
        # 单次输错不该把码作废（用户手滑是常态），只有累计到上限才作废。
        await self.store.issue("13800138000", "123456")
        self.assertEqual(await self.store.verify("13800138000", "000000"), VerifyResult.MISMATCH)
        self.assertEqual(await self.store.verify("13800138000", "123456"), VerifyResult.OK)

    async def test_too_many_attempts_invalidates_code(self):
        await self.store.issue("13800138000", "123456")
        for _ in range(settings.sms_max_attempts - 1):
            self.assertEqual(await self.store.verify("13800138000", "x"), VerifyResult.MISMATCH)

        self.assertEqual(await self.store.verify("13800138000", "x"), VerifyResult.TOO_MANY)
        # 作废之后正确码也不能用——否则"超限"只是个提示而不是限制。
        self.assertEqual(await self.store.verify("13800138000", "123456"), VerifyResult.EXPIRED)

    async def test_reissue_resets_attempt_counter(self):
        # 上一轮的失败次数不该影响这一轮的码，否则用户重发密码时反而更快被锁。
        await self.store.issue("13800138000", "111111")
        for _ in range(settings.sms_max_attempts - 1):
            await self.store.verify("13800138000", "wrong")

        await self.store.issue("13800138000", "222222")
        self.assertEqual(await self.store.verify("13800138000", "222222"), VerifyResult.OK)

    async def test_verify_without_issue_is_expired(self):
        self.assertEqual(await self.store.verify("13800138000", "123456"), VerifyResult.EXPIRED)

    async def test_expiry(self):
        await self.store.issue("13800138000", "123456")
        # 时间单调递增，直接把它推到 TTL 之后即可，不必真睡五分钟。
        with mock.patch(
            "app.api.user.code.code_store.time.monotonic",
            return_value=__import__("time").monotonic() + settings.sms_code_ttl_seconds + 1,
        ):
            self.assertEqual(await self.store.verify("13800138000", "123456"), VerifyResult.EXPIRED)

    async def test_cooldown_then_expires(self):
        await self.store.issue("13800138000", "123456")
        self.assertTrue(await self.store.is_cooling_down("13800138000"))
        # 其他号码不受影响：冷却按手机号隔离。
        self.assertFalse(await self.store.is_cooling_down("13900139000"))

        with mock.patch(
            "app.api.user.code.code_store.time.monotonic",
            return_value=__import__("time").monotonic()
            + settings.sms_resend_cooldown_seconds
            + 1,
        ):
            self.assertFalse(await self.store.is_cooling_down("13800138000"))

    async def test_phones_are_isolated(self):
        await self.store.issue("13800138000", "aaaaaa")
        await self.store.issue("13900139000", "bbbbbb")
        self.assertEqual(await self.store.verify("13800138000", "aaaaaa"), VerifyResult.OK)
        self.assertEqual(await self.store.verify("13900139000", "bbbbbb"), VerifyResult.OK)


class _FakePipeline:
    """只记录 set/delete，execute 时交给假 client 落库。"""

    def __init__(self, client: "_FakeRedis"):
        self._client = client
        self._ops: list[tuple] = []

    def set(self, key, value, ex=None):
        self._ops.append(("set", key, value, ex))

    def delete(self, key):
        self._ops.append(("delete", key))

    async def execute(self):
        for op in self._ops:
            if op[0] == "set":
                self._client.data[op[1]] = (op[2], op[3])
            else:
                self._client.data.pop(op[1], None)


class _FakeRedis:
    """复刻 RedisCodeStore 用到的那几个命令，足够断言协议形状。"""

    def __init__(self, verify_result: str = "ok"):
        self.data: dict[str, tuple[bytes, int | None]] = {}
        self.calls: list[tuple] = []
        self._verify_result = verify_result.encode()

    def register_script(self, script):
        self.script = script

        async def run(keys=None, args=None):
            self.calls.append((keys, args))
            return self._verify_result

        return run

    def pipeline(self):
        return _FakePipeline(self)

    async def exists(self, key):
        return 1 if key in self.data else 0


class RedisCodeStoreTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_issue_writes_digest_never_plaintext(self):
        redis = _FakeRedis()
        await RedisCodeStore(redis).issue("13800138000", "123456")

        code_key = CODE_KEY.format(phone="13800138000")
        stored, ttl = redis.data[code_key]
        self.assertEqual(stored, _digest("123456"))
        self.assertNotIn("123456", stored)
        self.assertEqual(ttl, settings.sms_code_ttl_seconds)

        cooldown = redis.data[COOLDOWN_KEY.format(phone="13800138000")]
        self.assertEqual(cooldown[1], settings.sms_resend_cooldown_seconds)
        # 重发清掉上一轮失败计数，否则用户重发之后更快被锁。
        self.assertNotIn(ATTEMPTS_KEY.format(phone="13800138000"), redis.data)

    async def test_verify_passes_digest_and_limits_to_lua(self):
        redis = _FakeRedis()
        store = RedisCodeStore(redis)
        # _FakeRedis 的 register_script 拿到的就是待执行的脚本对象
        await store.issue("13800138000", "123456")
        redis.data.pop(ATTEMPTS_KEY.format(phone="13800138000"), None)

        await store.verify("13800138000", "123456")

        keys, args = redis.calls[-1]
        self.assertEqual(
            keys,
            [
                CODE_KEY.format(phone="13800138000"),
                ATTEMPTS_KEY.format(phone="13800138000"),
            ],
        )
        self.assertEqual(args[0], settings.sms_max_attempts)
        self.assertEqual(args[1], settings.sms_code_ttl_seconds)
        self.assertEqual(args[2], _digest("123456"))

    async def test_verify_decodes_bytes_result(self):
        # redis-py 返回 bytes；不解码的话上层用 == VerifyResult.OK 永远不成立。
        store = RedisCodeStore(_FakeRedis(verify_result="mismatch"))
        self.assertEqual(await store.verify("13800138000", "wrong"), VerifyResult.MISMATCH)
        self.assertIsInstance(await store.verify("13800138000", "wrong"), str)

    async def test_is_cooling_down_is_bool(self):
        redis = _FakeRedis()
        store = RedisCodeStore(redis)
        self.assertFalse(await store.is_cooling_down("13800138000"))
        redis.data[COOLDOWN_KEY.format(phone="13800138000")] = (b"1", 60)
        # EXISTS 返回整数，直接 return 会让调用方拿到 1/0——必须是 bool。
        self.assertIs(await store.is_cooling_down("13800138000"), True)


if __name__ == "__main__":
    unittest.main()
