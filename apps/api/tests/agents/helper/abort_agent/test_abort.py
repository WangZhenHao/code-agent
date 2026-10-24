"""中止链路与消息缓冲的离线测试：不连库、不连沙箱、不起图。

覆盖三块，都是纯逻辑：

  1. run_registry —— 登记 / 注销 / 按信号中止。重点有两个边界：注销必须比对对象
     身份（否则同会话的**新** run 会被旧 run 迟到的 finally 静默删掉），以及
     没在跑的 run 要返回 False 而不是抛异常。
  2. message_buffer —— 流式片段的合并（按 id 相加，不是覆盖）与收尾（chunk 转
     AIMessage 后能 message_to_dict/messages_from_dict 往返）。
  3. run_agent_with_abort —— 赛跑本身。用假 agent 模拟「跑得慢」和「瞬间返回」，验证
     中止时返回 (None, True)、正常时返回 (result, False)，且两种情况都不留下
     未收集的 task。

跑法：uv run python -m unittest tests.agents.helper.abort_agent.test_abort
"""

from __future__ import annotations

import asyncio
import unittest

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    RemoveMessage,
    ToolMessage,
    message_to_dict,
    messages_from_dict,
)

from app.agents.helper.abort_agent import (
    abort_update,
    run_agent_with_abort,
    run_registry,
)
from app.agents.helper.abort_agent.message_buffer import accumulate, finalize_partial


class RunRegistryTestCase(unittest.TestCase):
    def tearDown(self):
        # 用例间互不干扰：注册表是模块级全局。
        run_registry._runs.clear()

    def test_register_and_get(self):
        ctx = run_registry.register("s1")
        self.assertIs(run_registry.get("s1"), ctx)
        self.assertFalse(ctx.aborted)
        self.assertFalse(ctx.abort.is_set())

    def test_signal_abort_marks_and_sets_event(self):
        ctx = run_registry.register("s1")

        self.assertTrue(run_registry.signal_abort("s1"))
        # 两个都要看：abort 是给节点停下来用的，aborted 是给 finish 判断写
        # interrupted 用的，少一个就有半边失灵。
        self.assertTrue(ctx.aborted)
        self.assertTrue(ctx.abort.is_set())

    def test_signal_abort_without_run_returns_false(self):
        # 已经跑完、或请求落到别的副本。返回 False 而不是抛异常，前端才不会
        # 因为重复点「停止」弹错误。
        self.assertFalse(run_registry.signal_abort("nobody"))

    def test_unregister_only_removes_own_context(self):
        old = run_registry.register("s1")
        new = run_registry.register("s1")  # 上一次的 run 没清干净，新 run 顶上来

        run_registry.unregister("s1", old)  # 旧 run 迟到的 finally

        # 只按 id 删的话这里会变成 None，新 run 从此静默地不响应中止。
        self.assertIs(run_registry.get("s1"), new)

    def test_unregister_then_signal_is_false(self):
        ctx = run_registry.register("s1")
        run_registry.unregister("s1", ctx)
        self.assertIsNone(run_registry.get("s1"))
        self.assertFalse(run_registry.signal_abort("s1"))


class MessageBufferTestCase(unittest.TestCase):
    def test_chunks_with_same_id_are_summed_not_overwritten(self):
        partial: dict = {}
        # 模型按 token 吐：每条片只带增量。覆盖的话最后只剩 "llo"。
        accumulate(partial, AIMessageChunk(content="he", id="m1"))
        accumulate(partial, AIMessageChunk(content="llo", id="m1"))

        self.assertEqual(len(partial), 1)
        self.assertEqual(partial["m1"].content, "hello")

    def test_tool_call_chunks_are_joined_into_callable_tool_calls(self):
        partial: dict = {}
        accumulate(partial, AIMessageChunk(content="", id="m1", tool_call_chunks=[
            {"name": "bash", "args": '{"cmd"', "id": "call_1", "index": 0, "type": "tool_call_chunk"},
        ]))
        accumulate(partial, AIMessageChunk(content="", id="m1", tool_call_chunks=[
            {"name": None, "args": ': "ls"}', "id": None, "index": 0, "type": "tool_call_chunk"},
        ]))

        # args 拼成完整 JSON 后，tool_calls 就是可直接用的对象（这正是中止时
        # 要落库的内容）。
        self.assertEqual(partial["m1"].tool_calls, [
            {"name": "bash", "args": {"cmd": "ls"}, "id": "call_1", "type": "tool_call"},
        ])

    def test_idless_chunk_is_dropped(self):
        partial: dict = {}
        accumulate(partial, AIMessageChunk(content="orphan"))  # id 为 None
        self.assertEqual(partial, {})

    def test_tool_message_keyed_by_tool_call_id(self):
        partial: dict = {}
        accumulate(partial, ToolMessage(content="ok", tool_call_id="call_1", name="bash"))
        self.assertEqual(list(partial), ["call_1"])

    def test_finalize_yields_roundtrippable_aimessage(self):
        partial: dict = {}
        accumulate(partial, AIMessageChunk(content="hi", id="m1"))
        accumulate(partial, ToolMessage(content="ok", tool_call_id="call_1", name="bash"))

        out = finalize_partial(partial)

        self.assertEqual([type(m).__name__ for m in out], ["AIMessage", "ToolMessage"])
        # chunk 直接 message_to_dict 的 type 是 "AIMessageChunk"，messages_from_dict
        # 认不出会抛。转成 AIMessage 之后必须原样往返——这是落库/回灌的前提。
        self.assertEqual(messages_from_dict([message_to_dict(m) for m in out]), out)

    def test_finalize_keeps_truncated_tool_call_with_empty_args(self):
        # 中止常发生在 args 只拼了一半的时候（模型正吐 `{"cmd": "ls` 就被掐掉）。
        # 此时 tool_calls **仍是有一条**，但 args 解析失败退化成 {}——实测如此，
        # 不是空列表。文本部分照常保留。
        partial: dict = {}
        accumulate(partial, AIMessageChunk(
            content="让我看看",
            id="m1",
            tool_call_chunks=[{"name": "bash", "args": '{"cmd"', "id": "call_1", "index": 0, "type": "tool_call_chunk"}],
        ))

        out = finalize_partial(partial)

        self.assertEqual(out[0].content, "让我看看")
        self.assertEqual(out[0].tool_calls, [
            {"name": "bash", "args": {}, "id": "call_1", "type": "tool_call"},
        ])
        # 残缺但可往返：不补全、不丢弃。
        self.assertEqual(messages_from_dict([message_to_dict(out[0])])[0], out[0])


class _SlowAgent:
    """跑不完就被取消的假 agent。"""

    def __init__(self):
        self.cancelled = False

    async def ainvoke(self, payload, config=None, **kwargs):
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            self.cancelled = True
            raise


class _FastAgent:
    """瞬间跑完，用来验「中止和中止信号同时到达」那条竞态。"""

    async def ainvoke(self, payload, config=None, **kwargs):
        return {"messages": [AIMessage(content="done", id="m1")]}


class RunAgentRaceTestCase(unittest.IsolatedAsyncioTestCase):
    """run_agent_with_abort：只取消内层 agent，不取消本节点。

    这是整个中止方案的支点——节点不被取消，return 才执行得了，LangGraph 才会
    沿 codeAgent → finish 走下一步把库落了。
    """

    def tearDown(self):
        run_registry._runs.clear()

    @staticmethod
    def _config(session_id: str) -> dict:
        return {"configurable": {"thread_id": session_id}}

    async def test_abort_wins_and_returns_aborted_true(self):
        agent = _SlowAgent()
        ctx = run_registry.register("s1")
        task = asyncio.create_task(
            run_agent_with_abort(agent, {"messages": []}, self._config("s1"))
        )

        # 让赛跑先起跑，再按中止。
        await asyncio.sleep(0)
        run_registry.signal_abort("s1")
        result, aborted = await asyncio.wait_for(task, timeout=5)

        self.assertIsNone(result)
        self.assertTrue(aborted)
        # 内层确实被取消了 —— 模型/工具在那一刻停下，而不是继续跑完。
        self.assertTrue(agent.cancelled)
        self.assertTrue(ctx.aborted)

    async def test_completes_normally_when_not_aborted(self):
        agent = _FastAgent()
        run_registry.register("s1")

        result, aborted = await asyncio.wait_for(
            run_agent_with_abort(agent, {"messages": []}, self._config("s1")), timeout=5
        )

        self.assertFalse(aborted)
        self.assertEqual(result["messages"][0].content, "done")

    async def test_agent_finishing_first_wins_over_abort(self):
        # 竞态：agent 已经跑完，abort 才到。必须按完整结果处理——半截内容不如
        # 完整内容，取消一个已结束的 task 本来就是 no-op。
        agent = _FastAgent()
        run_registry.register("s1")
        ctx = run_registry.register("s1")

        result, aborted = await asyncio.wait_for(
            run_agent_with_abort(agent, {"messages": []}, self._config("s1")), timeout=5
        )
        ctx.abort.set()

        self.assertFalse(aborted)
        self.assertIsNotNone(result)

    async def test_no_registered_run_falls_back_to_plain_await(self):
        # 离线跑图（build_graph() 裸图）没有注册表条目：中止不可用，但这一轮
        # 必须照常跑完，不能因为「找不到 run」就失败。
        agent = _FastAgent()
        result, aborted = await asyncio.wait_for(
            run_agent_with_abort(agent, {"messages": []}, self._config("unregistered")), timeout=5
        )

        self.assertFalse(aborted)
        self.assertEqual(result["messages"][0].content, "done")

    async def test_node_cancellation_cleans_up_inner_agent(self):
        # 客户端断连：StreamingResponse 取消的是**本节点所在的整个 task**，
        # 不是中止接口那种「按信号收手」。两者必须分开——这条路径没有 finish、
        # 不落库，但内层 agent 绝不能没人持有却还在跑模型。
        agent = _SlowAgent()
        run_registry.register("s1")

        task = asyncio.create_task(
            run_agent_with_abort(agent, {"messages": []}, self._config("s1"))
        )
        await asyncio.sleep(0)  # 让它跑到 asyncio.wait 上
        task.cancel()

        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=5)

        # 给被取消的内层一点时间完成收尾
        await asyncio.sleep(0)
        self.assertTrue(agent.cancelled, "内层 agent 必须被取消，不能留下悬空的模型调用")


class AbortUpdateTestCase(unittest.TestCase):
    """abort_update：已提交的（中间件记账）与半截的（流式缓冲）合并成落库内容。

    直接调它而不跑整张图：这里的正确性全在合并规则上，跑真图只会把
    「中间件记了什么」这个不确定变量混进来。
    """

    class _FakeSummarization:
        """复刻真实中间件在 abort 时的行为：传空列表，返回已提交的完整消息。

        真实实现 `current_round_messages([])` 就是取 _seen 过滤后的内容
        （final_messages 为空时第二个循环不执行）。
        """

        def current_round_messages(self, final_messages):
            # abort 分支没有 result["messages"] 可用，必须传空列表；传了别的东西
            # 说明 abort_update 又被改回正常路径的写法了，这里直接炸出来。
            assert final_messages == [], "abort 分支必须传空列表"
            return [
                AIMessage(content="已提交的一步", id="done-1"),
                ToolMessage(content="ok", tool_call_id="c1", name="bash"),
            ]

    def setUp(self):
        run_registry._runs.clear()

    def _state(self, session_id="s1"):
        return {"session": {"id": session_id, "user_id": 1}, "model": "m", "mode": "agent", "input": []}

    def test_committed_wins_over_partial_for_same_id(self):
        run = run_registry.register("s1")
        accumulate(run.partial, AIMessageChunk(content="半截", id="half-1"))
        # 同 id 在两边都有：以已提交的为准（partial 里那条只是流式解析出的中间态）
        accumulate(run.partial, AIMessageChunk(content="partial 版本", id="done-1"))

        out = abort_update(self._state(), self._FakeSummarization())

        self.assertTrue(out["aborted"])
        self.assertEqual([m.id for m in out["currentRoundMessages"] if m.id], ["done-1", "half-1"])
        self.assertEqual(out["currentRoundMessages"][0].content, "已提交的一步")

    def test_partial_chunks_are_merged_before_appending(self):
        run = run_registry.register("s1")
        accumulate(run.partial, AIMessageChunk(content="半", id="half-1"))
        accumulate(run.partial, AIMessageChunk(content="截", id="half-1"))

        out = abort_update(self._state(), self._FakeSummarization())

        half = [m for m in out["currentRoundMessages"] if m.id == "half-1"]
        self.assertEqual(len(half), 1)
        self.assertEqual(half[0].content, "半截")

    def test_never_carries_remove_all_messages(self):
        # 正常路径靠 RemoveMessage(REMOVE_ALL_MESSAGES) 让外层替换老历史；abort 分支
        # 绝不能带——那会把父图的全部历史砍成这一轮（压缩过的摘要消息压根不在
        # currentRoundMessages 里，它被中间件按 lc_source 过滤掉了）。
        run_registry.register("s1")
        out = abort_update(self._state(), self._FakeSummarization())

        self.assertFalse(any(isinstance(m, RemoveMessage) for m in out["messages"]))

    def test_works_without_registered_run(self):
        # 没登记（离线跑图）时不能炸：拿已提交的那部分就行。
        out = abort_update(self._state("nobody"), self._FakeSummarization())

        self.assertTrue(out["aborted"])
        self.assertEqual([m.id for m in out["currentRoundMessages"] if m.id], ["done-1"])


if __name__ == "__main__":
    unittest.main()
