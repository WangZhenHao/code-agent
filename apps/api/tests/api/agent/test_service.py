"""`api/agent/service.py` 的离线测试：不连库、不连沙箱、不连 Redis。

这层是「commands / stream / abort」三个接口的业务编排，最容易静默出错的地方
是**副作用顺序**和**分支选择**：

  - 归属校验必须先于任何写操作：拿别人的 id 也能触发 start_sandbox / 落库的话，
    这就是个越权写入面。
  - 空的 parts 直接 422，不能落到 start_run——空输入跑一轮图只会产出一条
    莫名其妙的空回复。
  - `start_agent_run` 必须先把沙箱和预览服务拉起来再起 run，否则模型第一个
    bash 工具就会砸在"沙箱未就绪"上。
  - `agent_command` 只返回 run_id、不 await 整轮。

外部依赖（DB session / start_sandbox / ThreadSession）都用假对象替换，断言落在
"调了什么、带什么参数、什么顺序"上。

跑法：uv run python -m unittest tests.api.agent.test_service
"""

from __future__ import annotations

import unittest
from unittest import mock

from fastapi import HTTPException

from app.api.agent import service
from app.api.chat.schemas import ChatCreateRequest
from app.db.models.session import MessageMode, MessageStatus, Role

PARTS = [{"type": "text", "text": "帮我写个快排"}]


class FakeSession:
    """只复刻 service 用到的 AsyncSession 行为。

    scalar() 按调用顺序依次吐预置结果——`_require_owned_session` 用 `select(id)`
    查归属，是这层唯一的一次 scalar 调用。用队列比解析 SQL 更稳：这里要测的是
    分支与顺序，不是 SQL 构造。
    """

    def __init__(self, *results):
        self._results = list(results)
        self.added: list = []
        self.commits = 0
        self.scalar_calls = 0

    async def scalar(self, _stmt):
        self.scalar_calls += 1
        if not self._results:
            raise AssertionError("scalar() 调用次数超出预置结果")
        return self._results.pop(0)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1


class FakeSandbox:
    def __init__(self):
        self.commands = self
        self.commands_run: list[str] = []

    def run(self, command, timeout=60):
        self.commands_run.append(command)
        return None


class FakeThreadSession:
    """替换 ThreadSession：记录 start_run 的 state 和 cancel 的调用。"""

    instances: list["FakeThreadSession"] = []
    run_id = "run-123"
    cancelled_return = True

    def __init__(self, thread_id):
        self.thread_id = thread_id
        self.started: list = []
        self.stream_params = None
        FakeThreadSession.instances.append(self)

    async def start_run(self, state):
        self.started.append(state)
        return FakeThreadSession.run_id

    async def cancel(self):
        return FakeThreadSession.cancelled_return

    async def stream(self, params):
        self.stream_params = params
        for frame in ("frame-1", "frame-2"):
            yield frame


def patched(**targets):
    """批量 patch service 里的外部依赖，用例结束后自动还原。"""
    stack = []
    for name, value in targets.items():
        p = mock.patch.object(service, name, value)
        p.start()
        stack.append(p)
    return stack


def stop_all(stack):
    for p in stack:
        p.stop()


def _state(session_id="s1", user_id=1):
    return {
        "mode": MessageMode.agent,
        "session": {"id": session_id, "user_id": user_id},
        "input": PARTS,
        "model": "m1",
    }


class RequireOwnedSessionTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_missing_session_is_404(self):
        with self.assertRaises(HTTPException) as ctx:
            await service._require_owned_session(FakeSession(None), "s1", 1)
        self.assertEqual(ctx.exception.status_code, 404)

    async def test_wrong_owner_looks_like_missing(self):
        # 查询带 user_id 条件，归属别人的会话拿到的就是 None——不能是 403，
        # 那等于告诉探测者"这个 id 存在"。
        with self.assertRaises(HTTPException) as ctx:
            await service._require_owned_session(FakeSession(None), "s1", 2)
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(ctx.exception.detail, "会话不存在")

    async def test_owned_session_passes(self):
        session = FakeSession("s1")
        await service._require_owned_session(session, "s1", 1)
        self.assertEqual(session.scalar_calls, 1)


class NewMessageStateTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_persists_user_message_before_running(self):
        session = FakeSession()
        req = ChatCreateRequest(model="m1", mode=MessageMode.plan, parts=PARTS)

        state = await service._new_message_state(session, "s1", 3, req)

        self.assertEqual(session.commits, 1)
        self.assertEqual(len(session.added), 1)
        saved = session.added[0]
        self.assertEqual(saved.session_id, "s1")
        self.assertEqual(saved.role, Role.user)
        self.assertEqual(saved.status, MessageStatus.complete)
        self.assertEqual(saved.mode, MessageMode.plan)
        self.assertEqual(saved.model, "m1")
        self.assertEqual(saved.parts, PARTS)

        self.assertEqual(state["input"], PARTS)
        self.assertEqual(state["session"], {"id": "s1", "user_id": 3})
        self.assertEqual(state["mode"], MessageMode.plan)
        self.assertEqual(state["model"], "m1")


class StartAgentRunTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.sandbox = FakeSandbox()
        FakeThreadSession.instances.clear()
        self._stack = patched(
            start_sandbox=mock.AsyncMock(return_value=self.sandbox),
            ThreadSession=FakeThreadSession,
        )
        self.addCleanup(stop_all, self._stack)

    async def test_returns_run_id_from_thread_session(self):
        run_id = await service.start_agent_run(_state())
        self.assertEqual(run_id, "run-123")

    async def test_starts_sandbox_and_preview_before_run(self):
        await service.start_agent_run(_state())
        service.start_sandbox.assert_awaited_once_with("s1")
        # 预览服务每次 run 都重跑：命令幂等，沙箱被回收重建后预览仍然可用。
        self.assertEqual(self.sandbox.commands_run, [service._PREVIEW_COMMAND])

        run = FakeThreadSession.instances[-1]
        self.assertEqual(run.thread_id, "s1")
        self.assertEqual(run.started[0]["session"]["id"], "s1")

    async def test_sandbox_failure_prevents_run(self):
        # 沙箱起不来时不能登记 run：那会跑出一轮"工具全失败"的对话并落库。
        service.start_sandbox = mock.AsyncMock(side_effect=RuntimeError("no sandbox"))
        with self.assertRaises(RuntimeError):
            await service.start_agent_run(_state())
        self.assertEqual(FakeThreadSession.instances, [])


class AgentCommandTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.sandbox = FakeSandbox()
        FakeThreadSession.instances.clear()
        self._stack = patched(
            start_sandbox=mock.AsyncMock(return_value=self.sandbox),
            ThreadSession=FakeThreadSession,
        )
        self.addCleanup(stop_all, self._stack)

    def _req(self, parts=PARTS):
        return ChatCreateRequest(model="m1", mode=MessageMode.agent, parts=parts)

    async def test_checks_ownership_before_everything(self):
        # 越权请求不能走到 start_sandbox / 落库——那是可观测的副作用。
        session = FakeSession(None)
        with self.assertRaises(HTTPException) as ctx:
            await service.agent_command("s1", 1, self._req(), session)
        self.assertEqual(ctx.exception.status_code, 404)

        service.start_sandbox.assert_not_awaited()
        self.assertEqual(session.added, [])
        self.assertEqual(FakeThreadSession.instances, [])

    async def test_empty_parts_is_422_and_has_no_side_effects(self):
        # 空输入没有可跑的内容。这里必须在校验之后就返回，不能落库、不能起 run。
        session = FakeSession("s1")
        with self.assertRaises(HTTPException) as ctx:
            await service.agent_command("s1", 1, self._req(parts=[]), session)
        self.assertEqual(ctx.exception.status_code, 422)

        self.assertEqual(session.added, [])
        self.assertEqual(session.commits, 0)
        service.start_sandbox.assert_not_awaited()
        self.assertEqual(FakeThreadSession.instances, [])

    async def test_persists_message_then_starts_run(self):
        session = FakeSession("s1")
        req = self._req()

        result = await service.agent_command("s1", 1, req, session)

        self.assertEqual(
            result, {"type": "success", "id": None, "result": {"run_id": "run-123"}}
        )
        self.assertEqual(len(session.added), 1)
        self.assertEqual(session.commits, 1)

        run = FakeThreadSession.instances[-1]
        self.assertEqual(run.thread_id, "s1")
        self.assertEqual(run.started[0]["input"], PARTS)
        self.assertEqual(run.started[0]["model"], "m1")

    async def test_returns_without_waiting_for_run(self):
        # start_run 返回 run_id 就够；接口绝不 await 整轮。
        session = FakeSession("s1")
        result = await service.agent_command("s1", 1, self._req(), session)
        self.assertIsInstance(result["result"]["run_id"], str)


class AgentAbortTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        FakeThreadSession.instances.clear()
        self._stack = patched(ThreadSession=FakeThreadSession)
        self.addCleanup(stop_all, self._stack)

    async def test_returns_false_without_error_when_nothing_running(self):
        # 前端重复点「停止」、或点在 run 刚结束之后，都不是错误，不该弹窗。
        FakeThreadSession.cancelled_return = False
        out = await service.agent_abort("s1", 1, FakeSession("s1"))
        self.assertEqual(out, {"aborted": False})

    async def test_returns_true_when_run_cancelled(self):
        FakeThreadSession.cancelled_return = True
        out = await service.agent_abort("s1", 1, FakeSession("s1"))
        self.assertEqual(out, {"aborted": True})

    async def test_ownership_checked_first(self):
        with self.assertRaises(HTTPException) as ctx:
            await service.agent_abort("s1", 1, FakeSession(None))
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(FakeThreadSession.instances, [])


class AgentStreamEventsTestCase(unittest.IsolatedAsyncioTestCase):
    """SSE 的错误路径与参数透传。成功路径的真订阅需要 Redis，不在这里。"""

    class _FakeSessionLocal:
        def __init__(self, session):
            self._session = session

        def __call__(self):
            session = self._session

            class _Ctx:
                async def __aenter__(_self):
                    return session

                async def __aexit__(_self, *exc):
                    return False

            return _Ctx()

    async def _collect(self, ownership_result, thread_session=FakeThreadSession):
        FakeThreadSession.instances.clear()
        stack = patched(
            SessionLocal=self._FakeSessionLocal(FakeSession(ownership_result)),
            ThreadSession=thread_session,
        )
        try:
            return [
                frame
                async for frame in service.agent_stream_events(
                    "s1", 1, service.SubscribeParams(since=3)
                )
            ], stack
        finally:
            stop_all(stack)

    async def test_not_owned_yields_error_frame_and_stops(self):
        frames, _ = await self._collect(None)

        self.assertEqual(len(frames), 1, "归属校验失败后必须立刻收尾，不能继续订阅")
        self.assertIn('"code": 404', frames[0])
        self.assertIn('"error": "not_found"', frames[0])
        # 形状对齐命令接口：type/error/message 三件套
        self.assertIn('"type": "error"', frames[0])
        self.assertEqual(FakeThreadSession.instances, [], "不能为越权请求开订阅")

    async def test_owned_session_subscribes_with_params(self):
        frames, _ = await self._collect("s1")

        self.assertEqual(frames, ["frame-1", "frame-2"])
        run = FakeThreadSession.instances[-1]
        # SubscribeParams 要 model_dump 成 dict 交给 ThreadSession（since 游标透传）
        self.assertEqual(run.stream_params["since"], 3)

    async def test_unexpected_error_becomes_sse_frame(self):
        # stream() 里抛异常时，响应头已经发出去了，只能再包一个 error 帧。
        class _Boom(FakeThreadSession):
            async def stream(self, params):
                raise RuntimeError("boom")
                yield  # pragma: no cover

        with mock.patch.object(service.logger, "exception") as log_exc:
            frames, _ = await self._collect("s1", thread_session=_Boom)

        self.assertEqual(len(frames), 1)
        self.assertIn('"code": 500', frames[0])
        self.assertIn("boom", frames[0])
        # 这行日志是排查线上 500 流时唯一的线索；同时把 traceback 挡在测试输出外。
        log_exc.assert_called_once()


if __name__ == "__main__":
    unittest.main()
