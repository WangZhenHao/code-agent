"""图的组装与路由的离线测试：用不带 checkpointer 的裸图。

`build_graph()` 刻意不碰数据库（checkpointer 由调用方注入），所以这里能直接
编译、直接跑。要验的是三件容易"看起来对、其实没接上"的事：

  1. `route_after_classify` —— 判定和路由是两个函数，改一处漏一处就会出现
     "判定说 plan、实际走 codeAgent"；
  2. 条件边真的**二选一**，而不是两条普通边那种扇出（两边都跑、写入顺序不定）；
  3. finish 是汇聚点，被中止的轮次落库时写 interrupted。

真正跑图的部分用假的 checkpointer 之外什么都不需要——planAgent / classify 都是
不调模型的占位实现。codeAgent 会拉沙箱，所以路由用例只走到分支名，不真的进节点。

跑法：uv run python -m unittest tests.agents.test_graphs
"""

from __future__ import annotations

import unittest
from unittest import mock

from app.agents import graphs
from app.agents.graphs import build_graph, route_after_classify
from app.agents.node.finish import finish
from app.db.models.session import MessageMode, MessageStatus


class RouteAfterClassifyTestCase(unittest.TestCase):
    def test_agent_mode_routes_to_agent(self):
        self.assertEqual(
            route_after_classify({"mode": MessageMode.agent}), MessageMode.agent
        )

    def test_plan_mode_routes_to_plan(self):
        self.assertEqual(
            route_after_classify({"mode": MessageMode.plan}), MessageMode.plan
        )

    def test_missing_mode_defaults_to_plan(self):
        # 第一轮进图前 mode 可能不存在（TypedDict 不能声明默认值）。这里必须
        # 用 state.get——写成 state["mode"] 会直接 KeyError。
        self.assertEqual(route_after_classify({}), MessageMode.plan)

    def test_unknown_mode_defaults_to_plan(self):
        # 模型瞎编的字符串不能被当成 agent 放行：默认走只读的 plan 更安全。
        self.assertEqual(route_after_classify({"mode": "bogus"}), MessageMode.plan)

    def test_returns_exact_branch_names(self):
        # 返回值必须和 add_conditional_edges 的映射表逐字一致（"plan"/"agent"，
        # 不是枚举的 str 形式之外的东西）。
        for mode, branch in ((MessageMode.plan, "plan"), (MessageMode.agent, "agent")):
            self.assertEqual(str(route_after_classify({"mode": mode})), branch)


class GraphShapeTestCase(unittest.TestCase):
    def setUp(self):
        self.graph = build_graph()

    def test_all_nodes_present(self):
        names = set(self.graph.get_graph().nodes)
        self.assertTrue(
            {"__start__", "classify", "planAgent", "codeAgent", "finish", "__end__"}
            <= names
        )

    def test_both_branches_converge_on_finish(self):
        # 只从 finish 往回看：两条分支的出口都必须是 finish，否则其中一条
        # 跑完就不落库了。
        edges = {(e.source, e.target) for e in self.graph.get_graph().edges}
        self.assertIn(("planAgent", "finish"), edges)
        self.assertIn(("codeAgent", "finish"), edges)
        self.assertIn(("finish", "__end__"), edges)

    def test_classify_edges_are_conditional(self):
        # 条件边在 get_graph() 的视图里也是一条边，但 `conditional=True` 且带
        # 分支名。有普通边（conditional=False）的话就是扇出（两节点都执行），
        # 不是路由。
        for edge in self.graph.get_graph().edges:
            if edge.source == "classify":
                self.assertTrue(edge.conditional, f"classify → {edge.target} 必须是条件边")

        branch_names = sorted(
            str(e.data) for e in self.graph.get_graph().edges
            if e.source == "classify" and e.conditional
        )
        self.assertEqual(branch_names, ["agent", "plan"])


class PlanBranchRunTestCase(unittest.IsolatedAsyncioTestCase):
    """plan 分支端到端跑一遍裸图：不调模型、不碰沙箱、不连库。"""

    async def test_plan_branch_produces_assistant_message_and_persists(self):
        graph = build_graph()

        persisted: dict = {}

        async def fake_persist(state, status):
            persisted["status"] = status
            persisted["currentRoundMessages"] = state.get("currentRoundMessages")

        with mock.patch("app.agents.node.finish.persist_round", fake_persist):
            result = await graph.ainvoke(
                {
                    "mode": MessageMode.plan,
                    "model": "m1",
                    "session": {"id": "s1", "user_id": 1},
                    "input": [{"type": "text", "text": "规划一下"}],
                },
                # 裸图没有 checkpointer，但 thread_id 仍要传：节点里会读它。
                {"configurable": {"thread_id": "s1"}},
            )

        # 走了 planAgent，没走 codeAgent（codeAgent 会拉沙箱，跑通说明没进去）
        contents = [m.content for m in result["messages"]]
        self.assertTrue(any("planAgent" in str(c) for c in contents), contents)
        self.assertEqual(result["mode"], MessageMode.plan)

        # finish 落库，且正常跑完写 complete
        self.assertEqual(persisted["status"], MessageStatus.complete)


class FinishStatusTestCase(unittest.IsolatedAsyncioTestCase):
    """finish 的 status 分支：中止写 interrupted，正常写 complete。"""

    async def _finish_with(self, aborted):
        recorded = {}

        async def fake_persist(state, status):
            recorded["status"] = status

        state = {
            "mode": MessageMode.agent,
            "model": "m1",
            "session": {"id": "s1", "user_id": 1},
            "input": [],
        }
        if aborted is not None:
            state["aborted"] = aborted

        with mock.patch("app.agents.node.finish.persist_round", fake_persist):
            await finish(state)
        return recorded["status"]

    async def test_aborted_round_is_interrupted(self):
        self.assertEqual(await self._finish_with(True), MessageStatus.interrupted)

    async def test_normal_round_is_complete(self):
        self.assertEqual(await self._finish_with(False), MessageStatus.complete)

    async def test_missing_flag_is_complete(self):
        # 正常路径压根不会设 aborted——不能拿 state["aborted"] 读，否则 KeyError。
        self.assertEqual(await self._finish_with(None), MessageStatus.complete)


class GetGraphTestCase(unittest.IsolatedAsyncioTestCase):
    """get_graph 的懒编译与缓存：编译只发生一次（启动时 lifespan 先调过）。"""

    def setUp(self):
        # 模块级单例，用例之间要还原，否则会串。
        self._original = graphs._graph
        graphs._graph = None
        self.addCleanup(self._restore)

    def _restore(self):
        graphs._graph = self._original

    async def test_compiles_once_and_caches(self):
        # 必须给真的 saver 类型：compile() 会校验实例，Mock 直接 TypeError。
        from langgraph.checkpoint.memory import InMemorySaver

        getter = mock.AsyncMock(return_value=InMemorySaver())
        with mock.patch.object(graphs, "get_checkpointer", getter):
            first = await graphs.get_graph()
            second = await graphs.get_graph()

        self.assertIs(first, second)
        self.assertIsNotNone(first)
        # 只取一次：第二次命中缓存，不该再建连接池。
        getter.assert_awaited_once()

    async def test_import_does_not_compile_graph(self):
        # 编译发生在 import 期的话只能拿到无 checkpointer 的图——静默丢历史。
        # 这里断言的是"没用模块级 graph 常量"：graphs 模块里不应有这个属性。
        self.assertFalse(hasattr(graphs, "graph"))


if __name__ == "__main__":
    unittest.main()
