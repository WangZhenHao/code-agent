"""Agent Streaming Protocol 线格式工具的按职责拆分实现。

纯函数，无状态无 IO。对外只暴露 `protocol.py` 门面，外部代码不要直接
import 这个子包：

    events     通道识别、订阅过滤、lifecycle 判定
    wire       归一化、JSON 序列化、SSE 帧编码
    synthesize 从 values 快照补出 tools 通道事件
    filters    出站事件过滤（快照 / 工具消息 / text 块收尾）
    redaction  工具参数脱敏
    deltas     tool_call_chunk 增量的分片与脱敏
"""

from __future__ import annotations

from app.agents.threading._protocol.deltas import fragment_tool_call_delta
from app.agents.threading._protocol.events import (
    is_after_replay_cursor,
    is_record,
    is_root_lifecycle,
    matches_subscription,
)
from app.agents.threading._protocol.filters import (
    is_message_snapshot,
    is_text_block_finish,
    is_tool_message_event,
)
from app.agents.threading._protocol.redaction import (
    redact_tool_args,
    redact_tool_event,
)
from app.agents.threading._protocol.synthesize import synthesize_tools_events
from app.agents.threading._protocol.wire import (
    PROTOCOL_METHODS,
    encode_sse,
    normalize_event,
    sanitize_event,
    sanitize_for_json,
    unwrap_protocol_data,
)

__all__ = [
    "PROTOCOL_METHODS",
    "encode_sse",
    "fragment_tool_call_delta",
    "is_after_replay_cursor",
    "is_message_snapshot",
    "is_record",
    "is_root_lifecycle",
    "is_text_block_finish",
    "is_tool_message_event",
    "matches_subscription",
    "normalize_event",
    "redact_tool_args",
    "redact_tool_event",
    "sanitize_event",
    "sanitize_for_json",
    "synthesize_tools_events",
    "unwrap_protocol_data",
]
