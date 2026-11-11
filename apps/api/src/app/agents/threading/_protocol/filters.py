"""出站事件过滤器：哪些消息不该转发给前端。

都是「形状判定」的纯函数，只看事件的 method / params 形状，不持有状态
（工具消息 id 集合由调用方传入并维护）。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from langchain_core.messages import BaseMessage

from app.agents.threading._protocol.events import is_record


def is_message_snapshot(event: Mapping[str, Any]) -> bool:
    """messages 通道上的「整条消息快照」（不带 `event` 字段），不转发。

    v3 的 astream_events 除了 message-start / content-block-* 增量，还会把
    `messages` 状态里的每条消息各推一份完整快照出来——包括摘要中间件塞进去的
    `HumanMessage("Here is a summary of the conversation to date: ...")` 和
    `RemoveMessage(REMOVE_ALL_MESSAGES)`。它们不是增量，JS SDK 的 MessageAssembler
    也不消费，转发出去只会把模型压缩后的摘要正文漏进前端。

    判定依据是形状：增量事件一定带 `event` 字段；快照要么已经是 `model_dump()`
    的 dict（字段是 content / type / id 这些），要么是还没被 `sanitize_for_json`
    处理过的 `BaseMessage` 对象——两种都要拦，否则漏的就是后者：过滤时它不是
    dict，发出去前才被 dump 成 dict。
    """
    if event.get("method") != "messages":
        return False
    params = event.get("params")
    if not is_record(params):
        return False
    data = params.get("data")
    # v3 下 messages 的 data 可能是 (payload, metadata) 元组，发布前还没 unwrap；
    # 不同版本打包成 list 的也有（JSON 往返后 tuple 就是 list），两种都解。
    if isinstance(data, (tuple, list)):
        data = data[0] if data else None
    if isinstance(data, BaseMessage):
        return True
    if not is_record(data):
        return False
    return "event" not in data


def is_tool_message_event(event: Mapping[str, Any], tool_message_ids: set[str]) -> bool:
    """`messages` 通道上的工具消息（role=tool）事件，不转发。

    工具结果是 `ToolMessage`，它在流里以 `message-start` + 若干
    `content-block-delta` / `content-block-finish` 的形式出现，内容就是整段工具
    输出。输出已落 `tool_calls` 表、前端按 `tool_call_id` 查询，所以这里整套
    丢掉：首个 `message-start` 记下消息 id，之后同 id 的所有事件都判为工具消息。

    只按消息 id 记，不解析后续每个事件的 role——message-start 之后的增量事件
    不一定重复带 role，但一定带 id。
    """
    if event.get("method") != "messages":
        return False
    params = event.get("params")
    if not is_record(params):
        return False
    data = params.get("data")
    # v3 下可能是 (payload, metadata) 元组，还没 unwrap。同 is_message_snapshot。
    if isinstance(data, (tuple, list)):
        data = data[0] if data else None
    if not is_record(data):
        return False

    if data.get("event") == "message-start":
        if data.get("role") == "tool":
            message_id = data.get("id")
            if isinstance(message_id, str):
                tool_message_ids.add(message_id)
            return True
        return False

    message_id = data.get("id")
    return isinstance(message_id, str) and message_id in tool_message_ids


def is_text_block_finish(event: Mapping[str, Any]) -> bool:
    """text 块的 content-block-finish：全文已由 delta 逐段发过，重复且体积大，不转发。

    tool_call 块必须保留——JS SDK 的 Assembler 用它的完整 content 拿可解析的
    工具参数，只靠 delta 的 tool_call_chunk 拼不出来。
    """
    if event.get("method") != "messages":
        return False
    params = event.get("params")
    if not is_record(params):
        return False
    data = params.get("data")
    # v3 下 messages 的 data 可能是 (payload, metadata) 元组，发布前还没 unwrap。
    if isinstance(data, tuple):
        data = data[0] if data else None
    if not is_record(data):
        return False
    if data.get("event") != "content-block-finish":
        return False
    content = data.get("content")
    return is_record(content) and content.get("type") == "text"
