"""agent 路由层的离线测试：路径、参数绑定、依赖注入、SSE 响应头。

**为什么单独测路由**：service 层的用例直接调函数，绕过了 FastAPI 的参数解析。
而这里出过一类典型的静默错误——路径参数名和 `{session_id}` 不一致时，FastAPI
会把它降级成**查询参数** `?id=`，接口不报错，只是永远拿不到值。这类问题只有
走真实 HTTP 栈才测得出来。

用最小 app（只 include 要测的 router）+ 依赖覆盖，不 import app.main：那边一
加载就会去连 checkpointer/Redis，离线环境起不来。

跑法：uv run python -m unittest tests.api.agent.test_router
"""

from __future__ import annotations

import unittest
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.agent import router as agent_router_module
from app.api.agent.router import router as agent_router
from app.db.models.user import User
from app.db.session import get_session
from app.security import get_current_user

FAKE_USER = User(id=7, phone="13800138000")


class _FakeSession:
    """路由层只负责把它传下去；具体行为由 service 的假对象负责。"""


def build_client() -> TestClient:
    app = FastAPI()
    app.include_router(agent_router)
    app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    app.dependency_overrides[get_session] = lambda: _FakeSession()
    return TestClient(app)


class CommandRouteTestCase(unittest.TestCase):
    def setUp(self):
        self.client = build_client()
        self.addCleanup(self.client.close)
        self.cmd = mock.AsyncMock(
            return_value={"type": "success", "id": None, "result": {"run_id": "r1"}}
        )
        patcher = mock.patch.object(agent_router_module, "agent_command", self.cmd)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_returns_plain_json_not_sse(self):
        resp = self.client.post(
            "/agents/s1/commands",
            json={"model": "m1", "mode": "agent", "parts": [{"type": "text", "text": "hi"}]},
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers["content-type"], "application/json")
        self.assertEqual(resp.json()["result"]["run_id"], "r1")

    def test_path_param_reaches_service(self):
        # 路径参数名写错会退化成 ?session_id=/id= 查询参数，接口仍 200 但值为空。
        self.client.post("/agents/s1/commands", json={"parts": [{"type": "text", "text": "x"}]})

        kwargs = self.cmd.await_args.kwargs
        self.assertEqual(kwargs["session_id"], "s1")
        self.assertEqual(kwargs["user_id"], 7)

    def test_request_body_is_parsed_into_schema(self):
        self.client.post(
            "/agents/s1/commands",
            json={"model": "m1", "mode": "plan", "parts": [{"type": "text", "text": "x"}]},
        )
        req = self.cmd.await_args.kwargs["req"]
        self.assertEqual(req.model, "m1")
        # MessageMode 是 StrEnum：Pydantic 会把字符串解析成枚举，service 拿到的
        # 已经是枚举值，不需要再转一层。
        self.assertEqual(req.mode, "plan")

    def test_invalid_mode_is_422(self):
        resp = self.client.post(
            "/agents/s1/commands",
            json={"mode": "bogus", "parts": [{"type": "text", "text": "x"}]},
        )
        self.assertEqual(resp.status_code, 422)
        self.cmd.assert_not_awaited()


class StreamRouteTestCase(unittest.TestCase):
    def setUp(self):
        self.client = build_client()
        self.addCleanup(self.client.close)

    def _patch_stream(self):
        async def fake_stream(**kwargs):
            yield "event: message\ndata: {}\n\n"

        patcher = mock.patch.object(agent_router_module, "agent_stream_events", fake_stream)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_stream_headers_disable_buffering(self):
        # SSE 必须关掉中间层缓冲，否则事件会攒在网关里一次性吐出。
        self._patch_stream()
        resp = self.client.post("/agents/s1/stream")

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.headers["content-type"].startswith("text/event-stream"))
        self.assertEqual(resp.headers["cache-control"], "no-cache")
        self.assertEqual(resp.headers["x-accel-buffering"], "no")

    def test_body_is_optional(self):
        # 不传 body 也要能用（SubscribeParams 的字段全可省）。
        self._patch_stream()
        self.assertEqual(self.client.post("/agents/s1/stream").status_code, 200)

    def test_events_alias_path_registered(self):
        # @langchain/react 的适配器默认打 /stream/events；两个路径都要通。
        self._patch_stream()
        resp = self.client.post("/agents/s1/stream/events")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.headers["content-type"].startswith("text/event-stream"))


class AbortRouteTestCase(unittest.TestCase):
    def setUp(self):
        self.client = build_client()
        self.addCleanup(self.client.close)
        self.abort = mock.AsyncMock(return_value={"aborted": True})
        patcher = mock.patch.object(agent_router_module, "agent_abort", self.abort)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_new_path(self):
        resp = self.client.post("/agents/s1/abort")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"aborted": True})
        self.assertEqual(self.abort.await_args.kwargs["session_id"], "s1")

    def test_legacy_path_still_works(self):
        # 旧路径保留给已发布的调用方，行为必须一致。
        resp = self.client.post("/agents/abort/s1")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.abort.await_args.kwargs["session_id"], "s1")


class AuthTestCase(unittest.TestCase):
    def test_missing_token_is_401(self):
        # 不覆盖 get_current_user：缺 Authorization 头时必须是 401 且带
        # WWW-Authenticate（浏览器/Swagger 靠它识别鉴权方式）。
        app = FastAPI()
        app.include_router(agent_router)
        app.dependency_overrides[get_session] = lambda: _FakeSession()
        client = TestClient(app)
        self.addCleanup(client.close)

        resp = client.post("/agents/s1/abort")

        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.headers.get("www-authenticate"), "Bearer")


if __name__ == "__main__":
    unittest.main()
