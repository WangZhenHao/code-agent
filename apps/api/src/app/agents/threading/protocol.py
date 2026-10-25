"""Agent Streaming Protocol 的线格式工具：事件归一化、过滤、序列化、SSE 编码。

从参考项目 `streaming-cookbook/python/react-custom-backend/src/app/session.py`
原样移植的纯函数（无状态、无 IO）。**不要改语义**：

- `unwrap_protocol_data` / `synthesize_tools_events` 是 Python v3 流与 JS SDK
  `MessageAssembler` 之间的兼容层，删了前端工具卡片就不出；
- `encode_sse` 的 `id:` 行是重连游标（`since`）的来源，格式不能动。

@see https://github.com/langchain-ai/agent-protocol/tree/main/streaming
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any, TypeGuard

from langchain_core.messages import BaseMessage
from langgraph.types import Command, Send

# v3 流里「原样透传」的方法名。不在此列且不带 `custom:` 前缀的，会被
# normalize_event 包成 custom 事件（兼容 LangGraph JS 的 remote channel 写法）。
PROTOCOL_METHODS = {
    # "values",
    # "checkpoints",
    "updates",
    "messages",
    "tools",
    "custom",
    "lifecycle",
    "input.requested",
    "tasks",
}


def is_record(value: Any) -> TypeGuard[dict[str, Any]]:
    return isinstance(value, dict)


def segment_matches(filter_segment: str, event_segment: str) -> bool:
    if ":" in filter_segment:
        return filter_segment == event_segment
    return event_segment.split(":")[0] == filter_segment


def get_event_channel(event: dict[str, Any]) -> str:
    method = event["method"]
    # Python v3 已经把命名 custom 通道发成 `custom:<name>`。
    if method.startswith("custom:"):
        return method
    if method != "custom":
        return method
    data = event["params"]["data"]
    if is_record(data) and isinstance(data.get("name"), str):
        return f"custom:{data['name']}"
    return "custom"


def matches_subscription(event: dict[str, Any], params: dict[str, Any]) -> bool:
    """订阅过滤器：channels（含 `custom` 通配所有 `custom:*`）+ namespaces/depth。"""
    channel = get_event_channel(event)
    channels = params.get("channels")
    if (
        isinstance(channels, list)
        and channels
        and channel not in channels
        and not (channel.startswith("custom:") and "custom" in channels)
    ):
        return False

    namespaces = params.get("namespaces")
    if not isinstance(namespaces, list) or not namespaces:
        return True

    raw_namespace = event["params"].get("namespace")
    namespace = raw_namespace if isinstance(raw_namespace, list) else []

    depth = params.get("depth")
    for prefix in namespaces:
        if not isinstance(prefix, list):
            continue
        if len(prefix) > len(namespace):
            continue
        prefix_matches = all(
            segment_matches(segment, namespace[index] if index < len(namespace) else "")
            for index, segment in enumerate(prefix)
        )
        if not prefix_matches:
            continue
        if depth is None or len(namespace) - len(prefix) <= depth:
            return True
    return False


def is_after_replay_cursor(event: dict[str, Any], params: dict[str, Any]) -> bool:
    since = params.get("since")
    return not isinstance(since, int) or (event.get("seq") or -1) > since


def normalize_event(event: dict[str, Any]) -> dict[str, Any]:
    method = event["method"]
    if method in PROTOCOL_METHODS:
        return event

    # Python v3 已经把命名 custom 通道发成 `custom:<name>`，直接透传。
    if method.startswith("custom:"):
        return event

    # LangGraph JS 的 StreamChannel.remote("<name>") 发的是裸方法名。
    return {
        **event,
        "method": "custom",
        "params": {
            **event["params"],
            "data": {
                "name": method,
                "payload": event["params"]["data"],
            },
        },
    }


def unwrap_protocol_data(method: str, data: Any) -> Any:
    """把 Python v3 的 ``(payload, metadata)`` 元组解成 JS 端认识的单对象。

    LangGraph Python 的 `messages` / `tools` 事件里 `params.data` 是
    `(payload, metadata)`；JS SDK 的 `MessageAssembler` 只认带 `event` 字段的
    单个 payload。
    """
    if method not in {"messages", "tools"}:
        return data
    if isinstance(data, tuple) and len(data) >= 1:
        return data[0]
    if (
        isinstance(data, list)
        and len(data) >= 1
        and isinstance(data[0], dict)
        and "event" in data[0]
    ):
        return data[0]
    return data


def sanitize_for_json(value: Any) -> Any:
    if isinstance(value, BaseMessage):
        return value.model_dump()
    if isinstance(value, Command):
        return sanitize_for_json(dataclasses.asdict(value))
    if isinstance(value, Send):
        return sanitize_for_json(
            {
                "node": value.node,
                "arg": value.arg,
                "timeout": value.timeout,
            }
        )
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return sanitize_for_json(dataclasses.asdict(value))
    if isinstance(value, dict):
        return {key: sanitize_for_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_for_json(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_for_json(item) for item in value]
    return value


def sanitize_event(event: dict[str, Any]) -> dict[str, Any]:
    params = dict(event["params"])
    method = event.get("method", "")
    params["data"] = sanitize_for_json(
        unwrap_protocol_data(method, params.get("data"))
    )
    if "interrupts" in params:
        params["interrupts"] = sanitize_for_json(params["interrupts"])
    return {**event, "params": params}


def _messages_from_values_event(event: dict[str, Any]) -> list[dict[str, Any]]:
    if event.get("method") != "values":
        return []
    params = event.get("params")
    if not is_record(params):
        return []
    namespace = params.get("namespace")
    if isinstance(namespace, list) and len(namespace) > 0:
        return []
    data = params.get("data")
    if not is_record(data):
        return []
    messages = data.get("messages")
    if not isinstance(messages, list):
        return []
    return [message for message in messages if is_record(message)]


def synthesize_tools_events(
    event: dict[str, Any],
    *,
    announced: set[str],
    finished: set[str],
) -> list[dict[str, Any]]:
    """Python v3 只在 `values` 里露工具活动时，补出 `tools` 通道事件。

    JS SDK 的 `stream.toolCalls` 投影监听的是 `tools` 通道的 `tool-started` /
    `tool-finished`；Python 运行时不一定伴随 `values.messages` 发，这里从权威
    快照里合成。announced / finished 由调用方持有，跨事件去重。
    """
    synthesized: list[dict[str, Any]] = []
    for message in _messages_from_values_event(event):
        message_type = message.get("type")
        if message_type == "ai":
            tool_calls = message.get("tool_calls")
            if not isinstance(tool_calls, list):
                continue
            for tool_call in tool_calls:
                if not is_record(tool_call):
                    continue
                call_id = tool_call.get("id")
                tool_name = tool_call.get("name")
                if not isinstance(call_id, str) or not isinstance(tool_name, str):
                    continue
                if call_id in announced:
                    continue
                announced.add(call_id)
                synthesized.append(
                    {
                        "type": "event",
                        "method": "tools",
                        "params": {
                            "namespace": [],
                            "data": {
                                "event": "tool-started",
                                "tool_call_id": call_id,
                                "tool_name": tool_name,
                                "input": tool_call.get("args") or {},
                            },
                        },
                    }
                )
            continue

        if message_type != "tool":
            continue

        call_id = message.get("tool_call_id")
        if not isinstance(call_id, str) or call_id in finished:
            continue
        finished.add(call_id)
        synthesized.append(
            {
                "type": "event",
                "method": "tools",
                "params": {
                    "namespace": [],
                    "data": {
                        "event": "tool-finished",
                        "tool_call_id": call_id,
                        "output": message.get("content"),
                    },
                },
            }
        )
    return synthesized


def is_root_lifecycle(event: dict[str, Any], name: str) -> bool:
    """判断是否是根命名空间上的某类 lifecycle 事件（running/completed/...）。"""
    if event.get("method") != "lifecycle":
        return False
    params = event.get("params")
    if not is_record(params):
        return False
    namespace = params.get("namespace")
    if not isinstance(namespace, list) or len(namespace) != 0:
        return False
    data = params.get("data")
    if not is_record(data):
        return False
    return data.get("event") == name


def is_text_block_finish(event: dict[str, Any]) -> bool:
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


def encode_sse(event: dict[str, Any]) -> str:
    """一条 ProtocolEvent 编成一个 SSE 帧。

    `id:` 行取 event_id 或 seq——客户端重连时把它当 `since` 传回来做回放。
    `json.dumps` 默认不产生换行，单行 data 是安全的。
    """
    event_id = event.get("event_id")
    seq = event.get("seq")
    frame_id = event_id if event_id else (f"{seq}" if isinstance(seq, int) else "")
    id_line = f"id: {frame_id}\n" if frame_id else ""
    return f"{id_line}event: message\ndata: {json.dumps(event)}\n\n"
