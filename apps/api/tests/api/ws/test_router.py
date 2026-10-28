"""WS 路由层离线测试：路径绑定、accept-then-close 鉴权、JSON-RPC 往返、推送。

为什么不能用 dependency_overrides：ws 鉴权不是 FastAPI 依赖（见 ws/core/auth.py），
所以这里 patch 模块属性——和 tests/api/agent/test_router.py 的 patched() 同一套做法。

用最小 app（只 include ws router）+ 不 import app.main：那边一加载就连
checkpointer/Redis，离线起不来。

跑法：uv run python -m unittest tests.api.ws.test_router
"""

from __future__ import annotations

import json
import unittest
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api.ws import router as ws_router_module
from app.api.ws import service as ws_service_module
from app.api.ws.core import hub
from app.api.ws.core.auth import WsAuthError
from app.api.ws.router import router as ws_router
from app.db.models.user import User

FAKE_USER = User(id=7, phone="13800138000")
SNAPSHOT = {
    "worktree_name": "",
    "branch": "main",
    "status": "running",
    "preview_enabled": True,
    "preview_url": "http://abc.localtest.me/",
    "running_previews": 1,
    "max_previews": 5,
    "sub_id": None,
    "project_type": None,
}


def build_client() -> TestClient:
    app = FastAPI()
    app.include_router(ws_router)
    return TestClient(app)


class _Patched:
    """把 (模块, 属性, 值) 一起 patch，setUp 里登记，addCleanup 里还原。"""

    def __init__(self, test: unittest.TestCase, targets: dict) -> None:
        self._test = test
        self._patchers = []
        for key, value in targets.items():
            module_name, attr = key.rsplit(".", 1)
            module = {
                "router": ws_router_module,
                "service": ws_service_module,
            }[module_name]
            p = mock.patch.object(module, attr, value)
            p.start()
            test.addCleanup(p.stop)


class AuthenticatedRoundTripTestCase(unittest.TestCase):
    def setUp(self):
        self.client = build_client()
        self.addCleanup(self.client.close)
        _Patched(
            self,
            {
                "router.authenticate_ws": mock.AsyncMock(return_value=FAKE_USER),
                "router.resolve_devbox": mock.AsyncMock(return_value=object()),
                "service.resolve_devbox": mock.AsyncMock(return_value=object()),
                "service.preview_params": mock.Mock(return_value=dict(SNAPSHOT)),
            },
        )
        self.addCleanup(hub._subscribers.clear)

    def test_preview_status_round_trip(self):
        with self.client.websocket_connect("/ws/devbox/s1?token=t") as ws:
            ws.send_text(
                '{"jsonrpc":"2.0","id":6,"method":"preview.status","params":{}}'
            )
            frame = ws.receive_json()

        self.assertEqual(frame["jsonrpc"], "2.0")
        self.assertEqual(frame["id"], 6)
        self.assertEqual(frame["result"]["status"], "running")
        self.assertEqual(frame["result"]["preview_url"], SNAPSHOT["preview_url"])

    def test_path_param_is_session_id(self):
        with self.client.websocket_connect("/ws/devbox/s1?token=t") as ws:
            ws.send_text(
                '{"jsonrpc":"2.0","id":1,"method":"preview.status","params":{}}'
            )
            ws.receive_json()

        self.assertEqual(
            ws_service_module.resolve_devbox.await_args.args, ("s1", FAKE_USER.id)
        )

    def test_unknown_method(self):
        with self.client.websocket_connect("/ws/devbox/s1?token=t") as ws:
            ws.send_text('{"jsonrpc":"2.0","id":2,"method":"nope","params":{}}')
            frame = ws.receive_json()

        self.assertEqual(frame["error"]["code"], -32601)

    def test_push_reaches_connected_client(self):
        with self.client.websocket_connect("/ws/devbox/s1?token=t") as ws:
            # 连接已建立 → 已在 hub 订阅。同进程直接发布，模拟 start_sandbox 的调用。
            hub.publish_devbox_event(
                "s1",
                "web.server_status_changed",
                {"status": "ready", "preview": SNAPSHOT},
            )
            frame = ws.receive_json()

        self.assertNotIn("id", frame)
        self.assertEqual(frame["method"], "web.server_status_changed")
        self.assertEqual(frame["params"]["status"], "ready")

    def test_heartbeat_shape(self):
        # 心跳是定时任务；这里只验证它构造的那条消息形状（直接调 notify）。
        from app.api.ws import schemas

        payload = schemas.dumps(schemas.notification("ping", {"ts": 1}))
        self.assertEqual(json.loads(payload)["method"], "ping")
        self.assertNotIn("id", json.loads(payload))


class AuthFailureTestCase(unittest.TestCase):
    """不 patch authenticate_ws：验证的是「先 accept 再带码 close」本身。"""

    def setUp(self):
        self.client = build_client()
        self.addCleanup(self.client.close)

    def _expect_close(self, url: str, code: int) -> None:
        with (
            self.client.websocket_connect(url) as ws,
            self.assertRaises(WebSocketDisconnect) as cm,
        ):
            ws.receive_text()
        self.assertEqual(cm.exception.code, code)

    def test_missing_token_closes_4401(self):
        self._expect_close("/ws/devbox/s1", 4401)

    def test_bad_token_closes_4401(self):
        self._expect_close("/ws/devbox/s1?token=not-a-jwt", 4401)

    def test_foreign_devbox_closes_4404(self):
        _Patched(
            self,
            {
                "router.authenticate_ws": mock.AsyncMock(return_value=FAKE_USER),
                "router.resolve_devbox": mock.AsyncMock(
                    side_effect=WsAuthError(4404, "devbox 不存在")
                ),
            },
        )
        self._expect_close("/ws/devbox/s1?token=t", 4404)

    def test_bad_snapshot_returns_resource_not_found(self):
        _Patched(
            self,
            {
                "router.authenticate_ws": mock.AsyncMock(return_value=FAKE_USER),
                "router.resolve_devbox": mock.AsyncMock(return_value=object()),
                "service.resolve_devbox": mock.AsyncMock(
                    side_effect=WsAuthError(4404, "devbox 不存在")
                ),
            },
        )
        with self.client.websocket_connect("/ws/devbox/s1?token=t") as ws:
            ws.send_text(
                '{"jsonrpc":"2.0","id":6,"method":"preview.status","params":{}}'
            )
            frame = ws.receive_json()
        # 连接期间会话被删：handler 抛 WsAuthError → WsAuthError 不是 JsonRpcError，
        # 走 INTERNAL_ERROR 兜底还是资源不存在都可以，但绝不能 200 正常结果。
        self.assertIn("error", frame)


if __name__ == "__main__":
    unittest.main()
