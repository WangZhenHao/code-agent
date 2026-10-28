"""进程内推送中心单测。

跑法：uv run python -m unittest tests.api.ws.test_hub
"""

from __future__ import annotations

import unittest

from app.api.ws.core import hub


class FakeCtx:
    def __init__(self) -> None:
        self.received: list[tuple[str, dict]] = []
        self.fail = False

    def notify(self, method: str, params: dict) -> None:
        if self.fail:
            raise RuntimeError("closed")
        self.received.append((method, params))


class HubTestCase(unittest.TestCase):
    def tearDown(self):
        # 全局状态，用例间必须清干净
        hub._subscribers.clear()

    def test_publish_reaches_subscribers(self):
        a, b = FakeCtx(), FakeCtx()
        hub.subscribe("d1", a)
        hub.subscribe("d1", b)

        n = hub.publish_devbox_event(
            "d1", "web.server_status_changed", {"status": "ready"}
        )

        self.assertEqual(n, 2)
        self.assertEqual(
            a.received, [("web.server_status_changed", {"status": "ready"})]
        )
        self.assertEqual(len(b.received), 1)

    def test_duplicate_subscribe_pushes_once(self):
        a = FakeCtx()
        hub.subscribe("d1", a)
        hub.subscribe("d1", a)

        self.assertEqual(hub.publish_devbox_event("d1", "m", {}), 1)
        self.assertEqual(len(a.received), 1)

    def test_unsubscribe_stops_delivery(self):
        a = FakeCtx()
        hub.subscribe("d1", a)
        hub.unsubscribe("d1", a)

        self.assertEqual(hub.publish_devbox_event("d1", "m", {}), 0)
        self.assertEqual(a.received, [])
        self.assertEqual(hub.subscriber_count("d1"), 0)

    def test_ids_are_isolated(self):
        a, b = FakeCtx(), FakeCtx()
        hub.subscribe("d1", a)
        hub.subscribe("d2", b)

        hub.publish_devbox_event("d1", "m", {})

        self.assertEqual(len(a.received), 1)
        self.assertEqual(b.received, [])

    def test_publish_without_subscribers_is_silent(self):
        self.assertEqual(hub.publish_devbox_event("nobody", "m", {}), 0)

    def test_one_bad_connection_does_not_block_others(self):
        bad, good = FakeCtx(), FakeCtx()
        bad.fail = True
        hub.subscribe("d1", bad)
        hub.subscribe("d1", good)

        hub.publish_devbox_event("d1", "m", {})

        self.assertEqual(len(good.received), 1)


if __name__ == "__main__":
    unittest.main()
