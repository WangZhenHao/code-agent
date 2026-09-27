"""finish 节点：所有分支汇聚后的收尾。"""

from app.agents.node.state import State


def finish(state: State) -> dict:
    """收尾。

    占位实现：什么都不改（返回空 dict，表示没有字段要更新）。

    以后要做的事都放这里——汇总 token 用量、释放该会话的沙箱资源、
    落审计日志。

    为什么单独留一个节点而不是把两条分支直接连 END：这些副作用需要
    发生在所有分支**汇聚之后**，且只发生一次。挂在 planAgent 和 codeAgent
    各自末尾的话，两边都得写一遍，且以后加第三条分支就会漏。
    """
    return {}
