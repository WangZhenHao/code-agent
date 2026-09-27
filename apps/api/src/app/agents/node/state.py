"""图的共享状态定义。

单独成模块的原因：节点函数在 node/ 下、图组装在 graphs.py，两边都要用 State。
放在任一边的任一侧都会造成循环导入（nodes 导入 graphs 的 State，
graphs 又导入 nodes 的函数）。State 作为最底层的类型定义，谁都可以依赖它，
它不依赖任何人，就没有环。
"""

from typing import Annotated, Literal, TypedDict

from langgraph.graph.message import add_messages

# 分类结果。
#
# 注意与节点名的错位：mode == "plan" 走的是 planAgent 节点，
# mode == "agent" 走的是 codeAgent 节点。"agent" 这个词描述的是
# "直接动手改代码"这一档，而不是"进入某个 agent"——所有节点都是 agent。
# 值域必须与 graphs.py 里 add_conditional_edges 的映射表逐字一致。
Branch = Literal["plan", "agent"]


class State(TypedDict):
    """贯穿全图的共享状态。

    注意：TypedDict 的类体里**不能写默认值**（`mode: str = 'plan'` 会抛 TypeError），
    默认值由节点函数返回时给出。所以第一轮进入图之前 mode 是缺失的，
    读取方要用 state.get("mode") 而不是 state["mode"]。

    messages 用 add_messages 收敛：节点返回 {"messages": [...]} 时是**追加**，
    不是覆盖。其余字段是普通字段，返回即覆盖。
    """

    messages: Annotated[list, add_messages]
    # classify 判定出的走向，同时也是路由函数读的依据。
    mode: Branch
    # planAgent 产出的步骤清单，供 codeAgent 消费。占位阶段为空。
    plan: list[str]
