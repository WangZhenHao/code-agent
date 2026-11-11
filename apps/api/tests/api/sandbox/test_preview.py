"""`api/sandbox/preview.py` 的离线测试：不连沙箱、不连库、不连 WS。

测的是「就绪判据 + 状态机」这两件最容易静默出错的事：

  - dev server 已经在跑时不能重启（重启等于白等一次编译）；
  - 只有探测到 200 才算 running，超时是 failed——不能因为命令跑完了就报成功；
  - 无论成败都要写库并推一条，否则前端永远等不到地址。

`_ensure` 直接 await，不经过 `start_preview`：后者只是 create_task 的壳。

跑法：uv run python -m unittest tests.api.sandbox.test_preview
"""

from __future__ import annotations

import unittest
from unittest import mock

from app.api.sandbox import preview
from app.db.models.session import PreviewStatus

SID = "s1"


class PreviewTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # 替代同步 SDK 的时间开销：探测序列由 ready_after 控制（第几次探测返回 True）。
        self.sandbox = mock.Mock()
        self._persist = mock.AsyncMock()
        self._publish = mock.Mock()
        stack = [
            mock.patch.object(preview, "persist_preview", self._persist),
            mock.patch.object(preview, "_publish", self._publish),
            mock.patch.object(
                preview, "sandbox_url", lambda s: "http://abc.localtest.me/"
            ),
        ]
        for p in stack:
            p.start()
            self.addCleanup(p.stop)

    async def test_already_running_does_not_restart(self):
        # 同一会话第二次发消息的常态：dev server 还在，直接 running。
        with (
            mock.patch.object(preview, "_probe", return_value=True),
            mock.patch.object(preview, "_start_and_wait") as start,
        ):
            await preview._ensure(SID, self.sandbox)

        start.assert_not_called()
        self._persist.assert_awaited_once()
        args = self._persist.await_args.args
        self.assertEqual(args[1], PreviewStatus.running)
        self.assertEqual(args[2], "http://abc.localtest.me/")
        self._publish.assert_called_once_with(
            SID, PreviewStatus.running, "http://abc.localtest.me/"
        )

    async def test_not_running_goes_building_then_running(self):
        with (
            mock.patch.object(preview, "_probe", return_value=False),
            mock.patch.object(preview, "_start_and_wait", return_value=True),
        ):
            await preview._ensure(SID, self.sandbox)

        statuses = [c.args[1] for c in self._persist.await_args_list]
        self.assertEqual(statuses, [PreviewStatus.building, PreviewStatus.running])
        # building 阶段不带地址：dev server 还没起来，给了也是假的。
        self.assertIsNone(self._persist.await_args_list[0].args[2])
        self._publish.assert_called_once_with(
            SID, PreviewStatus.running, "http://abc.localtest.me/"
        )

    async def test_timeout_is_failed_and_still_publishes(self):
        with (
            mock.patch.object(preview, "_probe", return_value=False),
            mock.patch.object(preview, "_start_and_wait", return_value=False),
        ):
            await preview._ensure(SID, self.sandbox)

        statuses = [c.args[1] for c in self._persist.await_args_list]
        self.assertEqual(statuses, [PreviewStatus.building, PreviewStatus.failed])
        self._publish.assert_called_once_with(
            SID, PreviewStatus.failed, "http://abc.localtest.me/"
        )

    async def test_start_and_wait_polls_until_200(self):
        # 不打补丁测真实循环：第二次探测才 200，间隔与次数都压到 0 免等待。
        probe = mock.Mock(side_effect=[False, True])
        with (
            mock.patch.object(preview, "_probe", probe),
            mock.patch.object(preview, "_PROBE_INTERVAL", 0),
        ):
            self.assertTrue(preview._start_and_wait(self.sandbox))

        self.sandbox.commands.run.assert_called_once_with(preview.PREVIEW_COMMAND)
        self.assertEqual(probe.call_count, 2)

    async def test_start_and_wait_gives_up_after_attempts(self):
        with (
            mock.patch.object(preview, "_probe", return_value=False),
            mock.patch.object(preview, "_PROBE_INTERVAL", 0),
            mock.patch.object(preview, "_PROBE_ATTEMPTS", 3),
        ):
            self.assertFalse(preview._start_and_wait(self.sandbox))

    def test_probe_treats_errors_as_not_ready(self):
        self.sandbox.commands.run.side_effect = RuntimeError("pod gone")
        self.assertFalse(preview._probe(self.sandbox))

    def test_payload_shape_matches_rpc(self):
        # 推送和 web.preview_status 应答必须同形状，否则前端要写两套解析。
        payload = preview.preview_payload("running", "http://x/")
        self.assertEqual(payload["status"], "running")
        self.assertEqual(payload["preview_url"], "http://x/")
        self.assertTrue(payload["preview_enabled"])
        self.assertFalse(preview.preview_payload("idle", None)["preview_enabled"])
        self.assertEqual(set(payload), {"status", "preview_url", "preview_enabled"})


if __name__ == "__main__":
    unittest.main()
