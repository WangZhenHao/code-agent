"""Agent 主图：classify → (planAgent | codeAgent) → finish。

命名约定：本模块暴露 build_graph()，返回已编译的图。
节点实现在 app/agents/node/ 下，本模块只负责连边。

    START → classify ─┬─(plan)─→ planAgent ─┐
                      └─(agent)→ codeAgent ─┴→ finish → END

运行时入口是 get_graph()（async，已挂 Postgres checkpointer）；build_graph()
是不带持久化的裸图，给调试和离线场景用。
"""

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents.memory.checkpointer import get_checkpointer
from app.agents.node import classify, code_agent, finish, plan_agent
from app.agents.node.state import Branch, State


def route_after_classify(state: State) -> Branch:
    """条件边：决定 classify 之后走哪个节点。

    只做一次查表，不重复 classify 的判定逻辑——判定归 classify，路由只负责
    把结论翻译成分支名。两处都写一遍的话，改动时漏改一处就会出现
    "判定说 plan、实际走 code" 这种极难排查的错。

    用 .get 而不是 state["mode"]：第一轮进图时该字段可能还不存在
    （TypedDict 无法声明默认值，见 node/state.py），一旦缺失就是 KeyError。
    """
    if state.get("mode") == "agent":
        return "agent"
    return "plan"


def build_graph(checkpointer: BaseCheckpointSaver | None = None):
    """组装并编译主图。

    返回已编译的图，可直接 .invoke()/.ainvoke()。
    需要多轮会话记忆时传 config={"configurable": {"thread_id": ...}}。

    checkpointer 不传则编译出一张**无持久化**的图（跑完即丢），只适合一次性
    调试或离线测试；线上要持久化请用 get_graph()，它会挂上 Postgres checkpointer。

    参数是显式注入而不是在这里 get_checkpointer()：后者现在是 async 的，而本
    函数是同步的。把异步依赖留在调用方，也顺带让本函数能在没起数据库的环境里用。
    """
    builder = StateGraph(State)

    builder.add_node("classify", classify)
    builder.add_node("planAgent", plan_agent)
    builder.add_node("codeAgent", code_agent)
    builder.add_node("finish", finish)

    builder.add_edge(START, "classify")

    # classify 之后是二选一，必须用条件边。
    # 用两条普通边（add_edge('classify', 两个节点)）的后果是两步**都会执行**，
    # 且两边并发写入 messages 时顺序不确定——那是扇出（fan-out），不是路由。
    # 映射表的值域必须与 Branch 逐字一致。
    builder.add_conditional_edges(
        "classify",
        route_after_classify,
        {"plan": "planAgent", "agent": "codeAgent"},
    )

    # 两条分支在这里汇聚。
    builder.add_edge("planAgent", "finish")
    builder.add_edge("codeAgent", "finish")
    builder.add_edge("finish", END)

    return builder.compile(checkpointer=checkpointer)


# 懒编译的单例图。
#
# **不要**退回成模块级的 `graph = build_graph()`：那样编译发生在 import 期，
# 而拿 checkpointer 是 async 的（要建连接池、建表），import 期做不到。真写成
# 那样，结果只能是不带 checkpointer 的图——静默丢历史，比报错难查得多。
_graph: CompiledStateGraph | None = None


async def get_graph() -> CompiledStateGraph:
    """取挂了 Postgres checkpointer 的图，只编译一次。

    第一次调用会建连接池并建表（见 app.agents.memory.checkpointer）。正常情况
    下这个代价发生在启动阶段——main.py 的 lifespan 已经先调过一次，这里命中缓存。
    """
    global _graph
    if _graph is None:
        _graph = build_graph(await get_checkpointer())
    return _graph
