"""finish 节点：所有分支汇聚后的收尾。"""

from app.agents.node.state import State
from app.agents.message_persistence import persist_round
from app.db.models.session import MessageStatus


async def finish(state: State) -> dict:
    """收尾：本轮的对话落库。

    **必须是 async**。persist_round 是 async def，以前这里用同步 def 调它
    却没 await —— 结果是构造了一个 coroutine 立刻丢弃，落库从没发生过（只有一条
    RuntimeWarning 被吞掉，比报错难查得多）。改成 async 节点，LangGraph 会 await
    它；图上不需要额外改动，节点是同步还是异步对 add_node 是透明的。

    为什么单独留一个节点而不是把两条分支直接连 END：这些副作用需要
    发生在所有分支**汇聚之后**，且只发生一次。挂在 planAgent 和 codeAgent
    各自末尾的话，两边都得写一遍，且以后加第三条分支就会漏。

    以后要做的事也放这里——汇总 token 用量、释放该会话的沙箱资源、落审计日志。
    """
    # 被 /agents/abort/{id} 中止的轮次写 interrupted，正常跑完写 complete。
    # state.get 而不是 state["aborted"]：正常路径压根不会设这个字段。
    status = (
        MessageStatus.interrupted
        if state.get("aborted")
        else MessageStatus.complete
    )

    # 先落库，避免后续副作用失败导致消息丢失。
    await persist_round(state, status)

    return {}
