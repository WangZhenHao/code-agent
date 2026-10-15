"""Agent 中止处理核心逻辑。

包含取消任务、运行带中止监听的 agent、以及生成中止时的状态更新等功能。
"""

import asyncio
from typing import TYPE_CHECKING

from langchain_core.runnables import RunnableConfig

from .message_buffer import finalize_partial
from .run_registry import get as get_run

if TYPE_CHECKING:
    from app.agents.node.state import State
    from app.agents.helper.middleware import TrackingSummarization


async def cancel_all(*tasks) -> None:
    """取消这些 task，并等它们真的结束。

    为什么必须 await 到结束，不能只 cancel() 就走：

    - 只 cancel 不 await 会留下 "Task was destroyed but it is pending"，而且
      **被取消不等于已经停下**——底层 HTTP 连接要等 CancelledError 真的传播到
      它那里才释放。不等的话，中止之后模型请求可能还在跑一会儿。
    - gather(return_exceptions=True) 把 CancelledError 收成结果值而不是往外抛，
      本节点因此不会带着异常退出。

    内层那个 try 是给「本协程自己正在被取消」准备的：那种情况下这里的 await 会
    立刻再抛一次 CancelledError。取消动作已经发出去了，清理目的达成，
    异常继续往上传播即可（客户端断连必须让取消一路传到 ASGI 层）。
    """
    for task in tasks:
        task.cancel()
    try:
        await asyncio.gather(*tasks, return_exceptions=True)
    except BaseException:
        pass


async def run_agent_with_abort(agent, payload: dict, config: RunnableConfig):
    """跑子 agent，同时盯着中止信号。返回 (result, aborted)。

    **为什么要把 `await agent.ainvoke(...)` 换成 create_task + 赛跑**：中止必须
    只取消内层这次模型循环，不能取消本节点。节点被取消的话 return 永不执行，
    LangGraph 就不会沿 codeAgent → finish 走下一步，finish 永远到不了，
    这一轮既落不了库、checkpoint 也停在 codeAgent 之前的脏状态。

    取消内层 task 则是干净的：本节点照常 return，父图把这次执行当成一次正常完成，
    该走的边一步不少，只是 state 里多了 aborted 标记。

    3.12 的 asyncio.wait **只收 Task**，传 coroutine 直接 TypeError
    （"Passing coroutines is forbidden, use tasks explicitly"），所以两个都要
    create_task 包一层。
    """
    # thread_id 即 session_id（graphs.py / service.py 的约定）。config 可能没有
    # configurable（离线跑图），取不到就当没登记，走下面的纯 await 分支。
    run = get_run((config.get("configurable") or {}).get("thread_id", ""))

    agent_task = asyncio.create_task(agent.ainvoke(payload, config=config, version="v2"))
    if run is None:
        # 没登记（离线直接跑图，或测试里的裸图），退化成原来的纯 await。
        # 中止功能不可用，但这一轮照常跑完。
        return await agent_task, False

    abort_task = asyncio.create_task(run.abort.wait())
    try:
        done, _ = await asyncio.wait(
            {agent_task, abort_task}, return_when=asyncio.FIRST_COMPLETED
        )
    except BaseException:
        # 本节点自己被取消了（客户端断连、服务关闭）。这条**不是**中止路径：
        # 没有 finish 会跑，也不会落库。但 agent_task 绝不能就这么留下——它没人
        # 持有了却还在跑模型。两个一起收掉，然后让取消继续往上传播。
        await cancel_all(agent_task, abort_task)
        raise

    # abort_task 只是「等信号」，任何情况下都不需要它的返回值，这里统一收掉。
    # cancel 在任务已结束时是 no-op，不必先判断状态。
    await cancel_all(abort_task)

    if agent_task in done:
        # 先跑完、或者两个同时完成。**取消已结束的 task 是 no-op**，所以
        # 「abort 赢了但 agent 刚好也跑完了」这条竞态会走到这里：以 agent 的
        # 完整结果为准，不按中止处理——半截内容不如完整内容。
        return agent_task.result(), False

    # abort 赢了：取消内层循环。**不要改成 except CancelledError**——那会连带捕获
    # 「本节点自己被取消」（客户端断连）的情况，把那种场景伪装成一次正常完成。
    await cancel_all(agent_task)
    return None, True


def abort_update(state: "State", summarization: "TrackingSummarization") -> dict:
    """被中止时返回的状态更新。

    内容有两个来源，缺一不可：

    1. `current_round_messages([])` —— **已经跑完整轮**的消息（上一轮的完整
       AIMessage、工具结果等）。传空列表是有意的：正常路径传的是
       result["messages"]（子 agent 循环结束的快照），中止时根本没有这个快照。
       已验证中间件的 _remember 挂在 before_model 这个独立节点上，只在超步边界
       快照，所以走到这里时 1..k-1 轮的消息都躺在 _seen 里，能完整取回。

    2. `finalize_partial(...)` —— 模型正在流、还没提交的那条半截消息。它只存在于
       agent_stream 的 partial 缓冲里（stream_mode="messages" 是回调侧信道，
       和 checkpoint 无关，所以别处都没有）。

    合并按 id 去重，**已提交的优先**：同一条 id 两处都有时，说明它是被流式解析
    出来的完整消息，比 partial 里那些尚未收尾的片更可信，直接跳过后者。
    """
    run = get_run(state["session"]["id"])
    committed = summarization.current_round_messages([])
    round_messages = list(committed)
    seen_ids = {m.id for m in committed}
    if run is not None:
        for m in finalize_partial(run.partial):
            if m.id not in seen_ids:
                seen_ids.add(m.id)
                round_messages.append(m)

    # messages 走**追加**，不能像正常路径那样带 RemoveMessage(REMOVE_ALL_MESSAGES)。
    #
    # 那条标记的作用是把外层老历史整体替换成「标记之后的内容」。中止时这个前提不成立：
    # 子 agent 内部若压缩过，含老历史的摘要消息只在它自己的 state 里，而中间件恰恰把
    # lc_source="summarization" 的合成摘要过滤掉了——所以带标记替换等于把父图的全部
    # 历史砍成这一轮，直接丢上下文。宁可父图历史长一点，也不能丢。
    return {
        # 走 add_messages 按 id 合并，新 id 追加。
        "messages": round_messages,
        # 覆盖语义（普通字段），落库用的就是这一份。
        "currentRoundMessages": round_messages,
        "aborted": True,
    }
