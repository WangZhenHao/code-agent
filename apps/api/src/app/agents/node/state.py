"""图的共享状态定义。

单独成模块的原因：节点函数在 node/ 下、图组装在 graphs.py，两边都要用 State。
放在任一边的任一侧都会造成循环导入（nodes 导入 graphs 的 State，
graphs 又导入 nodes 的函数）。State 作为最底层的类型定义，谁都可以依赖它，
它不依赖任何人，就没有环。
"""

from typing import Annotated, NotRequired, TypedDict

from langgraph.graph.message import add_messages

from app.db.models.session import MessageMode
from langchain.messages import ContentBlock
class Session: 
    id: str
    user_id: int



class State(TypedDict):
    """贯穿全图的共享状态。

    注意：TypedDict 的类体里**不能写默认值**（`mode: str = 'plan'` 会抛 TypeError），
    默认值由节点函数返回时给出。所以第一轮进入图之前 mode 是缺失的，
    读取方要用 state.get("mode") 而不是 state["mode"]。

    currentRoundMessages 是**普通字段**，返回即覆盖：它的语义是「仅本轮」，覆盖正是
    想要的。因此它没有挂 add_messages —— 挂上反而会变成跨轮累积的通道，需要每个写入方
    额外带一个 RemoveMessage(REMOVE_ALL_MESSAGES) 去手动复位（那正是 history 的坑）。

    messages 不同：它要跨轮累积，所以挂了 add_messages，返回是追加。
    """

    # 仅本轮：普通字段，返回即覆盖。不要挂 add_messages。
    currentRoundMessages: NotRequired[list]

    messages:  NotRequired[Annotated[list, add_messages]]

    # 本轮是否被 /agents/abort/{id} 中止。收尾方（finish）据此决定落库时写
    # MessageStatus.interrupted 还是 complete。
    #
    # 必须在这里声明，不能"随手返回一个没声明的 key"：LangGraph 的通道由 schema
    # 决定，节点返回未声明的字段会直接抛 InvalidUpdateError。没有 reducer 的字段
    # 是 LastValue 通道，写即覆盖——和 currentRoundMessages 同款语义。
    # 读取一律用 state.get("aborted")：第一轮进图时它不存在，同 mode 的坑。
    aborted: NotRequired[bool]

    # classify 判定出的走向，同时也是路由函数读的依据。
    mode: MessageMode

    model: str

    session: Session

    input: list[ContentBlock]
