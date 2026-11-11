"""流式消息的合并与收尾。

解决的问题：模型按 token 流出来的内容，在 LangGraph 里是**一堆不完整的片**
（AIMessageChunk），而落库 / 回灌需要的是**完整的消息对象**。这两步转换放在这里。

为什么单独成模块（而不是放进 helper/agent_stream.py 或 run_registry.py）：
两边都要用它——agent_stream 往里累积，code_agent 在中止时把结果取出来收尾——
而 agent_stream 和 node/code_agent 之间**本来就是个环**
（agent_stream 顶层 import node.state → node/__init__ → code_agent → helper.agent_stream）。
放进任何一边都会把这个环变成硬 import 错误。本模块只依赖 langchain_core，
谁都能依赖它，它不依赖任何人，和 state.py 是同一个理由。
"""

from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage


def accumulate(partial: dict, chunk) -> None:
    """把一条流出来的消息并进本次 run 的 partial 缓冲（就地修改）。

    分两类：

    - AIMessageChunk：**同一个 id 的多条片要相加**，不是覆盖。模型按 token 吐，
      每条片只带增量（content 是 "he" / "llo"），覆盖的话最后只剩最后一个 token。
      `__add__` 会把 content 块、additional_kwargs、tool_call_chunks 一起拼，拼完的
      `tool_calls` 属性就是可用的完整调用（已实测）。
    - ToolMessage：工具结果是整条到达的，不切片，按 `tool_call_id` 存即可。

    id 为 None 的 chunk（极少见）就地丢弃：没有 id 无法归并，硬存只会得到一堆
    互不相干的半截消息，比丢掉更难查。
    """
    if isinstance(chunk, AIMessageChunk):
        if not chunk.id:
            return
        prev = partial.get(chunk.id)
        partial[chunk.id] = chunk if prev is None else prev + chunk
        return
    if isinstance(chunk, ToolMessage):
        key = chunk.tool_call_id or chunk.id
        if key:
            partial.setdefault(key, chunk)


def finalize_partial(partial: dict) -> list:
    """把 partial 缓冲转成可以落库 / 可回灌的**真消息**列表。

    AIMessageChunk 必须转一手：

    - `message_to_dict` 给它的 type 是 "AIMessageChunk"，而 `messages_from_dict` 按
      type 查类，认不出这个值（实测 ValidationError）。
    - 也不能 `AIMessage.model_validate(chunk.model_dump())` —— dump 出来的 type 字段
      同样是 "AIMessageChunk"，会被 AIMessage 的 Literal["ai"] 拒绝（同样实测过）。

    所以直接构造 AIMessage，只搬 content / additional_kwargs / tool_calls（+= 拼好
    的 tool_calls 就是成品）。这样出来的对象 `message_to_dict` → `messages_from_dict`
    能原样往返（已实测）。

    中止常发生在 args 只拼了一半的时候（模型正吐 `{"cmd": "ls` 就被掐掉）。此时
    `tool_calls` **仍然会有一条**，但 args 解析失败、退化成 `{}`——实测如此，不是
    空列表。转出来的 AIMessage 因此带着一个 args 为空的 tool_call。

    这个「有调用、没结果」的残缺状态照原样保留，不做补全：add_messages 不校验配对，
    落库和前端展示都不受影响。代价是将来把这段历史回灌给严格的 provider（OpenAI 系）
    会因为 tool_call 没有对应的 ToolMessage 而 400——那属于 retalk 语义要一起处理的事。
    """
    out: list = []
    for item in partial.values():
        if isinstance(item, AIMessageChunk):
            out.append(
                AIMessage(
                    content=item.content,
                    additional_kwargs=item.additional_kwargs,
                    tool_calls=item.tool_calls,
                    id=item.id,
                )
            )
        else:
            out.append(item)
    return out
