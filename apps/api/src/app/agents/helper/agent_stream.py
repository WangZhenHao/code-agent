"""Agent 流式执行：把 state + config 跑成一条 SSE 事件流。

从 api/agent/service.py 抽出来，因为「跑图并透传事件」是编排层的事，
和「校验会话、装配 state」这种 HTTP 层的活分开。调用方只管前置校验，
拿到 state/config 后交给 agent_stream() 迭代即可。
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator

from langchain_core.messages import AIMessageChunk, ToolMessage

from app.agents.message_buffer import accumulate
from app.agents.node.state import State
from app.agents.run_registry import register, unregister

logger = logging.getLogger(__name__)

# 视为「改动了沙箱工作区」的工具名。这不是消息里带回来的信号，是按工具名推断——
# write_file/edit_file 直接落盘，bash 里可能有重定向/`sed -i`/`git apply` 等。
# 只读类（read_file/glob/grep）与其它一律 False。若将来某个工具语义变了，改这里。
WORKSPACE_MUTATING_TOOLS = frozenset({"write_file", "edit_file", "bash"})


def sse(event: str, data: dict) -> str:
    """把一条消息编成 SSE 帧。

    必须是 `data: <单行>` + 两个换行。json.dumps 默认会带换行吗？不会——
    ensure_ascii=False 保留中文原样，不转成 \\uXXXX，前端拿到的就是可读文本。
    """
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _node_name(namespace: tuple, metadata: dict) -> str:
    """取事件应归属的节点名。

    subgraphs=True 时每条消息带一个 namespace 元组：
      - 空元组 ()        → 消息由**外层图**的节点直接产出，节点名在
                          metadata["langgraph_node"]（如 classify / planAgent）。
      - 非空 ('codeAgent:<uuid>', ...) → 消息来自**子图内部**。此时 metadata 里的
                          langgraph_node 是子图自己的内部节点名（如 'model'/'tools'），
                          对前端没意义。取 namespace[0] 再砍掉 ":<uuid>"，还原成
                          外层节点名（'codeAgent'），前端才认得出是谁在流。
    """
    if namespace:
        return namespace[0].split(":", 1)[0]
    return metadata.get("langgraph_node", "")


async def _translate(chunk, node: str, pending: dict[int, dict]) -> AsyncIterator[str]:
    """把一条 messages 模式消息翻成 0..n 个 SSE 帧。

    messages 模式每步产出 (message_chunk, metadata)，元数据里 langgraph_node
    是产出该消息的节点名。三类消息各有归宿：

      AIMessageChunk  → text-delta / reasoning-delta（内容）+ tool-call（分片缓冲）
      ToolMessage     → tool-result
      其它（HumanMessage 等）→ 不发（它们是图的输入，前端已知道，重发是噪声）

    pending 是跨调用共享的 tool_call 分片缓冲，由调用方持有。做成 async generator
    是为了让调用方一句 `async for frame in _translate(...)` 统一 yield，
    调用方不必管每条消息产出几帧。
    """
    if isinstance(chunk, ToolMessage):
        data = {
            "node": node,
            "toolName": chunk.name,
            "toolCallId": chunk.tool_call_id,
            "result": chunk.content,
        }
        # status 是 LangChain 对工具执行结果的成功/失败标记。失败把原因也带上，
        # 前端好直接展示，不用去翻 result 文本判断。
        if chunk.status == "error":
            data["error"] = chunk.content if isinstance(chunk.content, str) else str(chunk.content)
        data["workspaceMutated"] = chunk.name in WORKSPACE_MUTATING_TOOLS
        yield sse("tool-result", data)
        return

    if not isinstance(chunk, AIMessageChunk):
        return

    # ── 正文与思考 ──────────────────────────────────────────────────────────
    # content_blocks 是 LangChain 归一化后的块列表，type 区分 text / reasoning。
    # 用归一化块而不是直接读字符串 content：多模态/带思考的 provider 会把内容
    # 拆成块，只读 content 字符串会漏掉 reasoning。
    # emitted_text 用来避免重复：content_blocks 有 text 块时 chunk.text 会返回
    # 同一段文字（实测如此），不加这道闸同一段正文会发两遍。
    emitted_text = False
    for block in chunk.content_blocks:
        btype = block.get("type")
        if btype == "text":
            text = block.get("text")
            if text:
                yield sse("text-delta", {"node": node, "text": text})
                emitted_text = True
        elif btype in ("reasoning", "thinking"):
            text = block.get("reasoning") or block.get("text")
            if text:
                yield sse("reasoning-delta", {"node": node, "text": text})

    # 兜底一：provider 只填了字符串 content、content_blocks 没给出 text 块时，
    # chunk.text 仍能取到纯文本。
    if chunk.text and not emitted_text:
        yield sse("text-delta", {"node": node, "text": chunk.text})

    # 兜底二：DeepSeek/OpenAI 风格把思考放在 additional_kwargs["reasoning_content"]，
    # 不走 content_blocks。
    reasoning = chunk.additional_kwargs.get("reasoning_content")
    if reasoning:
        yield sse("reasoning-delta", {"node": node, "text": reasoning})

    # ── tool call 分片缓冲 ──────────────────────────────────────────────────
    for tc in chunk.tool_call_chunks:
        index = tc.get("index")
        if index is None:
            # 无 index 无法归并分片（极少见）。跳过而不是乱拼。
            continue
        slot = pending.setdefault(index, {"node": node, "name": "", "id": "", "args": ""})
        if tc.get("name"):
            slot["name"] = tc["name"]
        if tc.get("id"):
            slot["id"] = tc["id"]
        if tc.get("args"):
            slot["args"] += tc["args"]

        # 拼到能解析就发一次完整事件，并从缓冲移除——args 类型是 object，前端直接可用。
        try:
            args = json.loads(slot["args"])
        except (json.JSONDecodeError, TypeError):
            continue
        yield sse(
            "tool-call",
            {
                "node": slot["node"],
                "toolName": slot["name"],
                "args": args,
                "toolCallId": slot["id"],
            },
        )
        del pending[index]



async def agent_stream(state: State, config: dict) -> AsyncIterator[str]:
    """跑图，把节点推的 custom 事件透传成 SSE 帧。

    Args:
        state: 图状态（含 mode/session/input，见 app.agents.node.state）。
        config: LangGraph 运行配置，至少含 {"configurable": {"thread_id": ...}}。

    本函数**自己兜异常**：generator 里抛异常会变成半截响应，客户端只能看到连接
    断掉。兜住并转成 error 事件，断在哪一步至少是可见的。
    """
    # 会话 ID 从 state 里取（调用方已保证存在）。start 帧和 done 帧都要带它。
    session_id = state["session"]["id"]

    # 延迟导入：graphs → node → code_agent → agent_prompt 会触发 helper 包的
    # __init__，而本模块又是 __init__ 导出的一员。顶层 import get_graph 会让
    # 这条链绕回还没建好的 graphs，报 partially initialized module。放到运行时
    # 导入，环就断在这里（本模块其余部分不依赖 graphs）。
    from app.agents.graphs import get_graph

    # 登记本次 run，abort 接口据此找到它。必须在第一个 yield 之前登记——start 帧
    # 一发出去前端就可能点「停止」。
    run = register(session_id)

    try:
        # start 帧在 get_graph() 之前发？不——放在之后。get_graph 首次会建连接池、
        # 建表，若它抛异常，此时还没 yield 过，能干净地走 except 分支。
        graph = await get_graph()

        yield sse("start", {"threadId": session_id})

        # tool_call 分片缓冲：messages 模式下 tool_call_chunks 逐片到达，第一个片
        # 带 name/id，args 是一段段拼起来的 JSON 字符串。按 index 累积，拼到能
        # json.loads 了就发一条完整的 tool-call 事件，然后从缓冲删掉。index 是
        # 一条消息内并发多个 tool call 时的区分键（见 content.ToolCallChunk）。
        pending: dict[int, dict] = {}

        # subgraphs=True 是**必须**的，不是可选项。code_agent 内部的 create_agent
        # 本身就是一张编译过的子图；不打开 subgraphs，子图里的模型调用不会冒到
        # 外层这个迭代器上——结果就是一条 token 都收不到，只剩 start/done（这正是
        # 「只输出这两个」的原因）。
        #
        # 代价：产出的元素从 (chunk, metadata) 变成 (namespace, (chunk, metadata))。
        # namespace 是子图路径元组，外层节点自己产的消息则是 ()。
        async for namespace, (chunk, metadata) in graph.astream(
            state, config=config, stream_mode="messages", subgraphs=True
        ):
            node = _node_name(namespace, metadata)
            # 先记账再翻译：翻译里可能 yield（客户端断开就在这里抛 GeneratorExit），
            # 排在 yield 之后的话最后一条 chunk 会漏记。accumulate 不做 IO，
            # 放在热路径上开销只有一次 dict 查找。
            accumulate(run.partial, chunk)
            async for frame in _translate(chunk, node, pending):
                yield frame

        # 兜底：流结束时缓冲里还有没解析成功的 tool call（args JSON 不完整，
        # 少见但可能——比如模型截断）。补发一次，用原始字符串当 args，
        # 免得整条 tool call 事件凭空消失。
        for item in pending.values():
            yield sse(
                "tool-call",
                {
                    "node": item["node"],
                    "toolName": item["name"],
                    "args": item["args"],
                    "toolCallId": item["id"],
                },
            )
        pending.clear()

        # aborted 与 done 二选一，不是并列的两个收尾帧。
        #
        # 为什么要区分：run.partial 里记下的「模型已经流出去、但还没提交」的那半截
        # 内容，不在落库结果里（code_agent 被取消时那段话从未成为消息对象，
        # checkpoint 里也没有——stream_mode="messages" 是回调侧信道，和 checkpoint
        # 无关）。所以前端手里那个气泡和 DB 里即将有的那行**对不上**，收到这一帧
        # 就该把它丢掉、改用落库的结果重绘。
        if run.aborted:
            yield sse("aborted", {"threadId": session_id})
        else:
            yield sse("done", {"threadId": session_id})

    except Exception as exc:
        logger.exception("agent_stream 失败 session_id=%s", session_id)
        yield sse("error", {"code": 500, "detail": str(exc)})

    finally:
        # 现在才有的 finally。以前没有，所以客户端断连（StreamingResponse 取消
        # 这个 ASGI task）时既不注销、也不落库——而 except Exception 兜不住
        # CancelledError（Python 3.8 起它是 BaseException），静默漏掉。
        #
        # 传 run 而不只传 id：同会话的新 run 可能已经顶上来，只按 id 删会把新的
        # 一起删掉，那个 run 从此不响应 abort（见 run_registry.unregister）。
        unregister(session_id, run)
