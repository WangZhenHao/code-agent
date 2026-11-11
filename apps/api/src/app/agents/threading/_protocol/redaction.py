"""工具参数脱敏：长 `content` 字段不进流。

完整参数由 `GET /agents/{session_id}/tools/{tool_call_id}` 返回，前端展开卡片
时以接口值为准；SSE 里只带摘要字段和占位提示。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.agents.threading._protocol.events import is_record

# 工具参数里允许原样进流的最大长度（字符）。`content` 是唯一会超的字段：
# write_file / edit_file 的正文动辄几 KB，结果已经落库，参数再完整流一遍等于
# 把同样的内容又发了一次。file_path / command 这类摘要字段远小于它。
_REDACT_FIELD = "content"
REDACT_LIMIT = 200


def redact_tool_args(args: Any) -> Any:
    """把工具参数里的长 `content` 换成占位提示。

    完整参数由 `GET /agents/{session_id}/tools/{tool_call_id}` 返回，前端展开
    卡片时以接口值为准。非 dict、非字符串、短内容一律原样返回，不做深拷贝。
    """
    if not is_record(args):
        return args
    value = args.get(_REDACT_FIELD)
    if not isinstance(value, str) or len(value) <= REDACT_LIMIT:
        return args
    return {
        **args,
        _REDACT_FIELD: (
            f"…（内容共 {len(value)} 字符，未在流式输出中传输；"
            "完整参数请展开工具卡片查看）"
        ),
    }


def redact_tool_event(event: Mapping[str, Any]) -> Mapping[str, Any]:
    """脱敏出站事件里的工具参数：tool-started 的 input、tool_call 块的 args。

    放在 `_emit` 的入口处（`sanitize_event` 之前），一处覆盖所有来源——从
    `values` 合成的、ToolRecorder 自己发的、messages 通道的 content-block-finish。

    `_emit` 里此时 `messages` 的 `data` 还是 v3 的 `(payload, metadata)` 元组
    （`sanitize_event` 之后才 unwrap），所以这里两种形态都要处理并原样保持。
    """
    method = event.get("method")
    params = event.get("params")
    if not is_record(params):
        return event
    raw = params.get("data")
    wrapper: type[tuple[Any, ...]] | type[list[Any]] | None = None
    if isinstance(raw, tuple):
        wrapper = tuple
        data = raw[0] if raw else None
        rest: tuple[Any, ...] | list[Any] = raw[1:]
    elif isinstance(raw, list):
        wrapper = list
        data = raw[0] if raw else None
        rest = raw[1:]
    else:
        data = raw
        rest = ()
    if not is_record(data):
        return event

    redacted: Any = None
    if method == "tools" and data.get("event") == "tool-started":
        input = data.get("input")
        new_input = redact_tool_args(input)
        if new_input is not input:
            redacted = {**data, "input": new_input}
    elif method == "messages" and data.get("event") == "content-block-finish":
        content = data.get("content")
        if is_record(content) and content.get("type") == "tool_call":
            args = content.get("args")
            new_args = redact_tool_args(args)
            if new_args is not args:
                redacted = {**data, "content": {**content, "args": new_args}}

    if redacted is None:
        return event

    if wrapper is tuple:
        new_data: Any = (redacted, *rest)
    elif wrapper is list:
        new_data = [redacted, *rest]
    else:
        new_data = redacted
    return {**event, "params": {**params, "data": new_data}}
