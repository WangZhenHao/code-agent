"""从 `values` 快照合成 `tools` 通道事件。

Python v3 运行时不一定伴随 `values.messages` 发 `tools` 事件，JS SDK 的
`stream.toolCalls` 投影又只监听 `tools` 通道，删了这里前端工具卡片就不出。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.agents.threading._protocol.events import is_record


def _messages_from_values_event(event: Mapping[str, Any]) -> list[dict[str, Any]]:
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
    event: Mapping[str, Any],
    *,
    announced: set[str],
    finished: set[str],
) -> list[dict[str, Any]]:
    """Python v3 只在 `values` 里露工具活动时，补出 `tools` 通道事件。

    JS SDK 的 `stream.toolCalls` 投影监听的是 `tools` 通道的 `tool-started` /
    `tool-finished`；Python 运行时不一定伴随 `values.messages` 发，这里从权威
    快照里合成。announced / finished 由调用方持有，跨事件去重。

    `tool-finished` **不带 output**：工具结果已由 ToolRecorder 落进 `tool_calls`
    表，前端按 `tool_call_id` 查接口拿。整段输出（最长 30k 字符）不再进 SSE、
    回放缓冲。
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
                        "status": "success",
                    },
                },
            }
        )
    return synthesized
