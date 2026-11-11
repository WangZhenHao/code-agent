"""Agent Streaming Protocol 的线格式工具：事件归一化、过滤、序列化、SSE 编码。

从参考项目 `streaming-cookbook/python/react-custom-backend/src/app/session.py`
原样移植的纯函数（无状态、无 IO），实现按职责拆在 `_protocol/` 子包里，
本文件只做统一门面。**不要改语义**：

- `unwrap_protocol_data` / `synthesize_tools_events` 是 Python v3 流与 JS SDK
  `MessageAssembler` 之间的兼容层，删了前端工具卡片就不出；
- `encode_sse` 的 `id:` 行是重连游标（`since`）的来源，格式不能动。

@see https://github.com/langchain-ai/agent-protocol/tree/main/streaming
"""

from __future__ import annotations

from app.agents.threading._protocol import (
    PROTOCOL_METHODS,
    encode_sse,
    fragment_tool_call_delta,
    is_after_replay_cursor,
    is_message_snapshot,
    is_record,
    is_root_lifecycle,
    is_text_block_finish,
    is_tool_message_event,
    matches_subscription,
    normalize_event,
    redact_tool_args,
    redact_tool_event,
    sanitize_event,
    sanitize_for_json,
    synthesize_tools_events,
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
