"""Agent 主图：classify → (planAgent | codeAgent) → finish。

命名约定：本模块暴露 build_graph()，返回已编译的图。
节点实现在 app/agents/node/ 下，本模块只负责连边。

    START → classify ─┬─(plan)─→ planAgent ─┐
                      └─(agent)→ codeAgent ─┴→ finish → END
"""

from langgraph.graph import END, START, StateGraph

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


def build_graph():
    """组装并编译主图。

    返回已编译的图，可直接 .invoke()/.ainvoke()。
    需要多轮会话记忆时传 config={"configurable": {"thread_id": ...}}，
    并在 compile 时挂上 checkpointer（见 app.agents.memory.get_checkpointer）。
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

    return builder.compile()


graph = build_graph()
