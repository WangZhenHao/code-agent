"""codeAgent 节点：按计划读写沙箱内文件。"""

import asyncio

from app.agents.helper.agent_prompt import generate_system_prompt
from app.agents.message_buffer import finalize_partial
from app.agents.helper.middleware import TrackingSummarization
from app.agents.node.state import State
from app.agents.run_registry import get as get_run
from langchain.agents import create_agent
from langchain_core.runnables import RunnableConfig

from app.agents.tools import create_tools
from app.agents.tools._common import WORKSPACE
from app.api.sandbox.client.sandbox import get_sandbox_for_id
from app.models.llm import get_model
from langchain.messages import HumanMessage, RemoveMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES


async def _cancel_all(*tasks) -> None:
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


async def _run_agent(agent, payload: dict, config: RunnableConfig):
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
        await _cancel_all(agent_task, abort_task)
        raise

    # abort_task 只是「等信号」，任何情况下都不需要它的返回值，这里统一收掉。
    # cancel 在任务已结束时是 no-op，不必先判断状态。
    await _cancel_all(abort_task)

    if agent_task in done:
        # 先跑完、或者两个同时完成。**取消已结束的 task 是 no-op**，所以
        # 「abort 赢了但 agent 刚好也跑完了」这条竞态会走到这里：以 agent 的
        # 完整结果为准，不按中止处理——半截内容不如完整内容。
        return agent_task.result(), False

    # abort 赢了：取消内层循环。**不要改成 except CancelledError**——那会连带捕获
    # 「本节点自己被取消」（客户端断连）的情况，把那种场景伪装成一次正常完成。
    await _cancel_all(agent_task)
    return None, True


async def code_agent(state: State, config: RunnableConfig):
    """agent 节点的核心逻辑：按计划读写沙箱内文件。

    签名带 config：LangGraph 会把父运行配置（含回调管理器）注入进来。透传它、
    并且用 ainvoke 而不是 invoke，子 agent 产出的 token 和工具结果才会流到外层
    的 messages 流里——本来它们全被 invoke 憋在节点内部，外层只剩一个最终结果。
    """
    session_id = state['session']['id']
    sandbox = get_sandbox_for_id(session_id)
    tools = create_tools(sandbox, mode=state['mode'])
    model = get_model(state['model'])
    system_prompt = generate_system_prompt(cwd=WORKSPACE, mode=state['mode'], project_context='')

    summarization = TrackingSummarization(
        model=model,
        # Trigger when conversation history reaches 10000 tokens
        trigger=("tokens", 10000),
        # Keep the 20 most recent messages intact after summarizing older ones
        keep=("messages", 10),
    )

    agent = create_agent(
        model=model, 
        tools=tools, 
        system_prompt=system_prompt,
        middleware=[summarization],
    )

    input = state['input']
    messages = state.get('messages', [])
    inputMessage = HumanMessage(content=input)

    # 本轮发出去的全部消息（历史 + 本轮用户输入），进 agent 的同时留作后面提取基准。
    input_messages = messages + [inputMessage]

    # 透传父 config（不要自造只带 thread_id 的 config——那样会丢掉回调，子 agent 的
    # 流式事件就回不到外层）。create_agent 默认无 checkpointer，复用父 thread_id 无副作用。
    # 赛跑与中止判定都在 _run_agent 里。
    result, aborted = await _run_agent(agent, {"messages": input_messages}, config)

    if aborted:
        return _abort_update(state, summarization)

    # 本轮消息（落库 + 前端展示用）从中间件取：它记下了压缩前的完整快照，
    # 详见 TrackingSummarization.current_round_messages。
    currentRoundMessages = summarization.current_round_messages(result["messages"])

    # 外层 messages 走「替换」而不是「追加」。
    #
    # 子 agent 触发压缩时，中间件在**它自己的** add_messages 里把老历史换成
    # [summary, ...最近20条]，那个 RemoveMessage(REMOVE_ALL_MESSAGES) 当次就被消费掉了
    # （reducer 见到它直接 return right[标记之后:]）。所以这里拿到的 result["messages"]
    # 已经不含删除标记，直接返回的话外层会走按 id 合并：老历史 id 都在、一条不删，
    # summary 是新 id 被追加——压缩等于白做，状态反而越滚越大。
    #
    # 这里把删除标记重新带上，让外层的 reducer 也走短路分支，老历史才真正被摘要替换。
    if summarization.triggered:
        messages_update = [RemoveMessage(id=REMOVE_ALL_MESSAGES), *result["messages"]]
    else:
        messages_update = result["messages"]
        
    return {
        "messages": messages_update,
        "currentRoundMessages": currentRoundMessages,
    }


def _abort_update(state: State, summarization: TrackingSummarization) -> dict:
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
