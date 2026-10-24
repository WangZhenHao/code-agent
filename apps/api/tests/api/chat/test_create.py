"""`create_chat` 的离线测试：新建会话后立刻跑第一轮。

这个函数把「建会话」和「跑第一轮」串在一起，最容易出错的点是**两步的事务
边界**：会话行必须先 commit 拿到 id，agent_command 才有 session_id 可用。
写成"和消息同一个事务"的话，agent_command 里那半截失败会把会话行一起回滚，
前端拿到 500 且什么都没建成。

`agent_command` 在这里用假函数替换——它自己的用例在 test_agent_service.py。

跑法：uv run python -m unittest tests.api.chat.test_create
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime
from unittest import mock

from app.api.chat import service
from app.api.chat.schemas import ChatCreateRequest
from app.db.models.session import MessageMode, Session, SessionStatus

PARTS = [{"type": "text", "text": "帮我写个快排"}]


class FakeSession:
    def __init__(self):
        self.added: list = []
        self.commits = 0
        self.flushed = 0
        self.refreshed: list = []

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flushed += 1
        # 复刻 ORM 的 Python 端默认值：flush 之后主键就有了。
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = "chat-1"

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        self.refreshed.append(obj)
        # server_default / TimestampMixin 的列在 refresh 之后才有值。
        if getattr(obj, "created_at", None) is None:
            obj.created_at = datetime.now(UTC)
        if getattr(obj, "updated_at", None) is None:
            obj.updated_at = datetime.now(UTC)


class CreateChatTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.cmd = mock.AsyncMock(return_value={"result": {"run_id": "r1"}})
        # create_chat 里是延迟 import；patch 到模块对象上，函数内 import 会取到它。
        patcher = mock.patch("app.api.agent.service.agent_command", self.cmd)
        patcher.start()
        self.addCleanup(patcher.stop)

    async def test_persists_session_before_running_first_round(self):
        session = FakeSession()
        req = ChatCreateRequest(model="m1", mode=MessageMode.agent, parts=PARTS)

        resp = await service.create_chat(req, user_id=7, session=session)

        self.assertEqual(resp.id, "chat-1")
        self.assertEqual(session.commits, 1)
        self.assertEqual(session.flushed, 1, "flush 后才能拿到 id 去起 run")
        self.assertEqual(session.refreshed[0].id, "chat-1")

        # 会话行本身的默认值
        saved = session.added[0]
        self.assertIsInstance(saved, Session)
        self.assertEqual(saved.user_id, 7)
        self.assertEqual(saved.status, SessionStatus.running)

        # 第一轮交给 agent_command，且用的是刚拿到的 id
        kwargs = self.cmd.await_args.kwargs
        self.assertEqual(kwargs["session_id"], "chat-1")
        self.assertEqual(kwargs["user_id"], 7)
        self.assertIs(kwargs["req"], req)
        self.assertIs(kwargs["session"], session)

    async def test_response_shape(self):
        resp = await service.create_chat(
            ChatCreateRequest(parts=PARTS), user_id=1, session=FakeSession()
        )
        # ChatCreateResponse 必填 created_at；description 可空但要存在
        self.assertEqual(resp.title, "")
        self.assertIsNotNone(resp.created_at)
        self.assertIsNone(resp.description)

    async def test_run_failure_keeps_session(self):
        # 会话已经 commit，run 失败也不回滚——前端刷新能看到会话，再发一条即可。
        self.cmd.side_effect = RuntimeError("sandbox down")
        session = FakeSession()

        with self.assertRaises(RuntimeError):
            await service.create_chat(
                ChatCreateRequest(parts=PARTS), user_id=1, session=session
            )

        self.assertEqual(session.commits, 1, "会话行必须已经提交")
        self.assertEqual(len(session.added), 1)

    async def test_empty_parts_is_rejected_by_agent_command(self):
        # 空输入由 agent_command 统一判 422（它同时服务「继续发消息」那条路径）。
        # 这里只要确认 create_chat 不自己另做一套判断：命令确实被调用了。
        from fastapi import HTTPException

        self.cmd.side_effect = HTTPException(status_code=422, detail="parts 不能为空")
        with self.assertRaises(HTTPException):
            await service.create_chat(
                ChatCreateRequest(parts=[]), user_id=1, session=FakeSession()
            )
        self.cmd.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
