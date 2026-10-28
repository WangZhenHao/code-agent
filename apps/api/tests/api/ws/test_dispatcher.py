"""分发器单测：纯 JSON-RPC 语义，不起 FastAPI、不碰 DB/Redis。

注意必须 `import app.api.ws.methods`（或 import 某个方法模块）来触发注册，
否则 dispatch 会对所有方法回 -32601。

跑法：uv run python -m unittest tests.api.ws.test_dispatcher
"""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from pydantic import BaseModel, ConfigDict

import app.api.ws.methods  # noqa: F401  触发方法注册
from app.api.ws import schemas
from app.api.ws.core.dispatcher import dispatch
from app.api.ws.core.registry import get_method, rpc_method


class EchoParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: int = 0


calls: list[int] = []


@rpc_method("test.echo", params_model=EchoParams)
async def _echo(ctx, params: EchoParams) -> dict:
    calls.append(params.value)
    return {"value": params.value}


@rpc_method("test.notify_only")
async def _notify_only(ctx, params) -> dict:
    calls.append(-1)
    return {"ok": True}


@rpc_method("test.rpc_error")
async def _rpc_error(ctx, params) -> dict:
    raise schemas.JsonRpcError(schemas.RESOURCE_NOT_FOUND, "没找到")


@rpc_method("test.boom")
async def _boom(ctx, params) -> dict:
    raise RuntimeError("secret details / internal path")


CTX = SimpleNamespace(user=SimpleNamespace(id=7), devbox_id="d1")


def call(payload) -> dict | None:
    import asyncio

    raw = payload if isinstance(payload, str) else json.dumps(payload)
    text = asyncio.run(dispatch(raw, CTX))
    return None if text is None else json.loads(text)


class DispatchTestCase(unittest.TestCase):
    def setUp(self):
        calls.clear()

    def test_id_echoed_with_same_type(self):
        for id_ in (6, "6", 0):
            frame = call(
                {
                    "jsonrpc": "2.0",
                    "id": id_,
                    "method": "test.echo",
                    "params": {"value": 3},
                }
            )
            self.assertEqual(frame["id"], id_)
            self.assertIs(type(frame["id"]), type(id_))
            self.assertEqual(frame["result"], {"value": 3})
            self.assertEqual(frame["jsonrpc"], "2.0")

    def test_null_id_is_still_answered(self):
        # 有 "id" 键（值 null）要回包；缺 "id" 键才是通知。
        frame = call(
            {"jsonrpc": "2.0", "id": None, "method": "test.notify_only", "params": {}}
        )
        self.assertIsNotNone(frame)
        self.assertIsNone(frame["id"])

    def test_notification_runs_but_returns_nothing(self):
        self.assertIsNone(
            call({"jsonrpc": "2.0", "method": "test.notify_only", "params": {}})
        )
        self.assertEqual(calls, [-1])

    def test_parse_error(self):
        frame = call("{not json")
        self.assertEqual(frame["error"]["code"], schemas.PARSE_ERROR)
        self.assertIsNone(frame["id"])

    def test_non_object_payload(self):
        self.assertEqual(call("[]")["error"]["code"], schemas.INVALID_REQUEST)
        self.assertEqual(call('"x"')["error"]["code"], schemas.INVALID_REQUEST)
        self.assertEqual(call("1")["error"]["code"], schemas.INVALID_REQUEST)

    def test_batch_rejected_with_reason(self):
        frame = call('[{"jsonrpc":"2.0","id":1,"method":"test.notify_only"}]')
        self.assertEqual(frame["error"]["code"], schemas.INVALID_REQUEST)
        self.assertEqual(frame["error"]["message"], schemas.BATCH_UNSUPPORTED)

    def test_wrong_jsonrpc_version(self):
        frame = call({"jsonrpc": "1.0", "id": 1, "method": "test.echo"})
        self.assertEqual(frame["error"]["code"], schemas.INVALID_REQUEST)

    def test_unknown_method(self):
        frame = call({"jsonrpc": "2.0", "id": 6, "method": "nope.nope", "params": {}})
        self.assertEqual(frame["error"]["code"], schemas.METHOD_NOT_FOUND)
        self.assertEqual(frame["id"], 6)

    def test_invalid_params(self):
        frame = call(
            {"jsonrpc": "2.0", "id": 6, "method": "test.echo", "params": {"value": "x"}}
        )
        self.assertEqual(frame["error"]["code"], schemas.INVALID_PARAMS)
        # data 必须可 JSON 序列化（回归：pydantic 的 errors() 里可能带异常实例）
        json.dumps(frame)

        frame = call(
            {"jsonrpc": "2.0", "id": 6, "method": "test.echo", "params": {"vlaue": 1}}
        )
        self.assertEqual(frame["error"]["code"], schemas.INVALID_PARAMS)

    def test_positional_params_rejected(self):
        # params 是数组：模型不允许，落到 INVALID_REQUEST/INVALID_PARAMS 之一都行，
        # 但绝不能悄悄当空参数执行。
        frame = call({"jsonrpc": "2.0", "id": 6, "method": "test.echo", "params": [1]})
        self.assertIn(
            frame["error"]["code"], (schemas.INVALID_PARAMS, schemas.INVALID_REQUEST)
        )
        self.assertEqual(calls, [])

    def test_jsonrpc_error_maps_to_code(self):
        frame = call(
            {"jsonrpc": "2.0", "id": 6, "method": "test.rpc_error", "params": {}}
        )
        self.assertEqual(frame["error"]["code"], schemas.RESOURCE_NOT_FOUND)
        self.assertEqual(frame["error"]["message"], "没找到")

    def test_unknown_exception_does_not_leak(self):
        frame = call({"jsonrpc": "2.0", "id": 6, "method": "test.boom", "params": {}})
        self.assertEqual(frame["error"]["code"], schemas.INTERNAL_ERROR)
        self.assertNotIn("secret", json.dumps(frame, ensure_ascii=False))

    def test_duplicate_registration_raises(self):
        with self.assertRaises(RuntimeError):

            @rpc_method("test.echo")
            async def _dup(ctx, params):
                return {}

    def test_preview_status_registered(self):
        self.assertIsNotNone(get_method("preview.status"))


if __name__ == "__main__":
    unittest.main()
