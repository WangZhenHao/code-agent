"""事件归一化、JSON 序列化与 SSE 帧编码。

**不要改语义**：

- `unwrap_protocol_data` 是 Python v3 流与 JS SDK `MessageAssembler` 之间的
  兼容层，删了前端工具卡片就不出；
- `encode_sse` 的 `id:` 行是重连游标（`since`）的来源，格式不能动。
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any

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
    params["data"] = sanitize_for_json(unwrap_protocol_data(method, params.get("data")))
    if "interrupts" in params:
        params["interrupts"] = sanitize_for_json(params["interrupts"])
    return {**event, "params": params}


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
