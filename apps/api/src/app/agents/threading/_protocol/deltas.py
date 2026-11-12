"""tool_call_chunk 增量的分片与脱敏。

langchain_core 的 v3 兼容桥对 `tool_call_chunk` 类型的 block-delta 发的是
**已累积的整块**：写一个 10KB 的文件会变成 55 帧，每帧都从头再发一遍，累计
250KB 以上。这里改写成 JS SDK 会**拼接**的 `tool-call-delta`，只发新增片段。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.agents.threading._protocol.events import is_record
from app.agents.threading._protocol.redaction import REDACT_LIMIT

# 参数流里 content 值的起始标记。只认这个精确形状：模型输出的 args 由 JSON
# 序列化器逐段拼出，分隔符稳定；认不出来就不脱敏（宁可漏，不误吞）。
_CONTENT_DELTA_KEY = '"content": "'
# 增量帧里内容超限后替换成的占位符（finish 帧会整体覆盖成带字符数的版本）。
_CONTENT_DELTA_MARKER = "…（内容未在流式输出中传输，完整内容请展开工具卡片查看）"


def _content_close_index(args: str, start: int) -> int | None:
    """从 start 起找 content 字符串的收尾引号（跳过 `\\` 转义），没有则 None。"""
    index = start
    while index < len(args):
        char = args[index]
        if char == "\\":
            index += 2
            continue
        if char == '"':
            return index
        index += 1
    return None


def _redacted_delta(  # noqa: F401 —— 调用点在下方注释块里，恢复输出时用
    raw: str, previous: str, key: str, suppressed: dict[str, bool]
) -> str | None:
    """算出（已脱敏视角的）新增片段；None 表示这一帧不发。

    `suppressed` 按块记「content 已超限、正在吞」：超限时先发到上限为止再发
    一个占位符，之后到收尾引号前的所有增量都丢弃，收尾后从引号开始恢复。
    客户端拼出来的 args 里 content 是「前 200 字 + 占位符」的一段合法字符串，
    不会被截断成非法 JSON。
    """
    start = raw.find(_CONTENT_DELTA_KEY)
    if start < 0:
        if not raw.startswith(previous):
            return None
        return raw[len(previous) :]
    start += len(_CONTENT_DELTA_KEY)

    close = _content_close_index(raw, start)
    if suppressed.get(key):
        if close is None:
            return None
        suppressed[key] = False
        return raw[close:]

    if not raw.startswith(previous):
        return None
    # 值已收尾且没超限：正常发（短 content 原样可见）。
    if close is not None and close - start <= REDACT_LIMIT:
        return raw[len(previous) :]
    if close is None and len(raw) - start <= REDACT_LIMIT:
        return raw[len(previous) :]

    cutoff = start + REDACT_LIMIT
    suppressed[key] = True
    return raw[len(previous) : cutoff] + _CONTENT_DELTA_MARKER


def fragment_tool_call_delta(
    event: Mapping[str, Any],
    seen: dict[str, str] | None = None,
    suppressed: dict[str, bool] | None = None,
) -> Mapping[str, Any] | None:
    """把累积型的 tool_call_chunk 增量改成只发新增的那一段。

    langchain_core 的 v3 兼容桥（`_compat_bridge.chunks_to_events`）对
    `tool_call_chunk` 类型的 block-delta 发的是**已累积的整块**：写一个 10KB
    的文件会变成 55 帧，每帧都从头再发一遍，累计 250KB 以上，Redis 回放缓冲
    也按同样大小存。

    这里把 `block-delta`（JS SDK 对它整体覆盖，所以必须全量）改写成
    `tool-call-delta`：SDK 对后者是**拼接**（`args: current.args + delta.args`），
    正好只需要新增部分。参数内容照样实时可见，只是不再重复。

    content 长字段特殊处理：值超过 `REDACT_LIMIT` 后只发前 200 字 + 占位符，
    其余增量丢弃（见 `_redacted_delta`），整段文件正文因此不进流。

    按「消息 id + 块 index」记住上次发出的全量 args 当基线：
    - 与上次相同 → 返回 None，调用方跳过；
    - 是上次的前缀延伸 → 只发多出来的后缀；
    - 不是前缀（理论上不该发生）→ 退回原样的全量 block-delta，SDK 会整体覆盖，
      状态仍然正确。
    """
    if event.get("method") != "messages":
        return event
    params = event.get("params")
    if not is_record(params):
        return event
    data = params.get("data")
    # v3 下 messages 的 data 可能是 (payload, metadata) 元组，发布前还没 unwrap。
    if isinstance(data, tuple):  # noqa: SIM108 —— 保留分支形状，方便恢复被注释的行
        # is_tuple = True
        payload = data[0] if data else None
        # rest = tuple(data[1:])
    else:
        # is_tuple = False
        payload = data
        # rest = ()
    if not is_record(payload) or payload.get("event") != "content-block-delta":
        return event
    delta = payload.get("delta")
    if not is_record(delta):
        return event
    # langchain_core 1.7.6 的兼容桥原生就发 tool-call-delta（只带 args 增量），
    # 不走 block-delta，所以上面那段改写碰不到它；要关掉输出就拦在这里。
    if delta.get("type") == "tool-call-delta":
        return None
    if delta.get("type") != "block-delta":
        return event
    fields = delta.get("fields")
    if not is_record(fields) or fields.get("type") != "tool_call_chunk":
        return event
    if seen is None:
        return event

    args = fields.get("args") or ""
    # 块身份优先用 fields.id（每个工具调用唯一的 call_xxx）：同一条消息里连续
    # 多个工具调用时，payload 的 id 是 None、index 还都是同一个，只按它们分会
    # 把后一个调用当成「同一个块的续片」整段跳过。
    block_key = f"{fields.get('id') or payload.get('id') or ''}#{payload.get('index')}"
    previous = seen.get(block_key, "")
    if args == previous:
        return None
    if not args.startswith(previous):
        # 退回全量 block-delta（SDK 整体覆盖）。基线也重置成新值，否则后续
        # 增量永远判不过前缀检查、每帧都退全量。
        seen[block_key] = args
        return event

    # state = suppressed if suppressed is not None else {}
    # suffix = _redacted_delta(args, previous, block_key, state)
    seen[block_key] = args
    # if suffix is None:
    #     return None

    # 暂不向前端输出 tool-call-delta 帧（只保留基线推进，避免每帧退回全量）。
    # 恢复时把下面三行取消注释即可。
    # fragment = {
    #     **payload,
    #     "delta": {"type": "tool-call-delta", "args": suffix},
    # }
    # fragment_data = (fragment, *rest) if is_tuple else fragment
    # return {**event, "params": {**params, "data": fragment_data}}
    return None
