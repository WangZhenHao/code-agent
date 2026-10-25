"""协议层纯函数测试：不连库、不连 Redis、不起图。

覆盖 `fragment_tool_call_delta`：langchain_core v3 兼容桥对 tool_call_chunk 发的
是累积的全量 args（10KB 文件 → 55 帧、累积 250KB+）。这里把它改写成 JS SDK 会
**拼接**的 tool-call-delta，只发新增片段；参数内容仍然实时可见。

跑法：uv run python -m unittest tests.agents.threading.test_protocol
"""

from __future__ import annotations

import unittest

from app.agents.threading.protocol import fragment_tool_call_delta

_NAMESPACE = ["codeAgent:test"]


def _messages_event(payload: dict, *, as_tuple: bool = False) -> dict:
    data = (payload, {}) if as_tuple else payload
    return {
        "type": "event",
        "method": "messages",
        "params": {"namespace": _NAMESPACE, "data": data},
        "seq": 831,
    }


def _tool_call_delta(args: str, *, index: int = 1, block_index: int = 0) -> dict:
    return {
        "event": "content-block-delta",
        "index": index,
        "delta": {
            "type": "block-delta",
            "fields": {
                "type": "tool_call_chunk",
                "id": "call_716e",
                "name": "write_file",
                "args": args,
                "index": block_index,
            },
        },
    }


class FragmentToolCallDeltaTest(unittest.TestCase):
    def test_first_delta_sends_whole_args(self) -> None:
        seen: dict[str, str] = {}
        kept = fragment_tool_call_delta(_messages_event(_tool_call_delta('{"a"')), seen)

        self.assertIsNotNone(kept)
        delta = kept["params"]["data"]["delta"]
        self.assertEqual(delta, {"type": "tool-call-delta", "args": '{"a"'})

    def test_growth_sends_only_suffix(self) -> None:
        seen: dict[str, str] = {}
        fragment_tool_call_delta(_messages_event(_tool_call_delta('{"a"')), seen)
        kept = fragment_tool_call_delta(_messages_event(_tool_call_delta('{"a": 1}')), seen)

        self.assertEqual(
            kept["params"]["data"]["delta"],
            {"type": "tool-call-delta", "args": ": 1}"},
        )

    def test_concat_reassembles_full_args(self) -> None:
        seen: dict[str, str] = {}
        snapshots = ['{"cont', '{"content": "import', '{"content": "import x"}']
        assembled = ""
        for snapshot in snapshots:
            kept = fragment_tool_call_delta(
                _messages_event(_tool_call_delta(snapshot)), seen
            )
            if kept is not None:
                assembled += kept["params"]["data"]["delta"]["args"]
        self.assertEqual(assembled, snapshots[-1])

    def test_identical_snapshot_dropped(self) -> None:
        seen: dict[str, str] = {}
        payload = _tool_call_delta('{"content": "abc"}')
        self.assertIsNotNone(fragment_tool_call_delta(_messages_event(payload), seen))
        self.assertIsNone(fragment_tool_call_delta(_messages_event(payload), seen))

    def test_non_prefix_falls_back_to_full_block(self) -> None:
        seen: dict[str, str] = {}
        fragment_tool_call_delta(_messages_event(_tool_call_delta('{"path": "a"}')), seen)
        replaced = _tool_call_delta('{"path": "b"}')
        kept = fragment_tool_call_delta(_messages_event(replaced), seen)

        # 退回原事件：SDK 对 block-delta 整体覆盖，状态仍然正确。
        self.assertIs(
            kept["params"]["data"]["delta"]["type"], "block-delta"
        )
        self.assertEqual(kept["params"]["data"]["delta"]["fields"]["args"], '{"path": "b"}')

    def test_blocks_are_tracked_independently(self) -> None:
        seen: dict[str, str] = {}
        first = _tool_call_delta('{"a"', index=1, block_index=0)
        second = _tool_call_delta('{"a"', index=1, block_index=0)
        # 同一条消息里连续两个工具调用：payload id/index 都一样，只有 fields.id 不同。
        second["delta"]["fields"]["id"] = "call_other"

        fragment_tool_call_delta(_messages_event(first), seen)
        kept = fragment_tool_call_delta(_messages_event(second), seen)
        # 另一个调用没发过，首帧要发全量而不是空片段。
        self.assertEqual(kept["params"]["data"]["delta"]["args"], '{"a"')

    def test_tuple_payload_supported(self) -> None:
        seen: dict[str, str] = {}
        payload = _tool_call_delta('{"a"')
        self.assertIsNotNone(
            fragment_tool_call_delta(_messages_event(payload, as_tuple=True), seen)
        )
        grown = fragment_tool_call_delta(
            _messages_event(_tool_call_delta('{"a": 1}'), as_tuple=True), seen
        )
        data = grown["params"]["data"]
        self.assertIsInstance(data, tuple)
        self.assertEqual(data[0]["delta"], {"type": "tool-call-delta", "args": ": 1}"})
        self.assertEqual(data[1], {})

    def test_without_seen_untouched(self) -> None:
        event = _messages_event(_tool_call_delta('{"a"'))
        self.assertIs(fragment_tool_call_delta(event), event)

    def test_does_not_mutate_input(self) -> None:
        seen: dict[str, str] = {}
        payload = _tool_call_delta('{"path": "a"}')
        event = _messages_event(payload)
        fragment_tool_call_delta(event, seen)
        self.assertEqual(event["params"]["data"]["delta"]["type"], "block-delta")
        self.assertEqual(
            event["params"]["data"]["delta"]["fields"]["args"], '{"path": "a"}'
        )

    def test_tool_call_finish_untouched(self) -> None:
        payload = {
            "event": "content-block-finish",
            "index": 1,
            "content": {
                "type": "tool_call",
                "id": "call_716e",
                "name": "write_file",
                "args": {"path": "a.tsx"},
            },
        }
        event = _messages_event(payload)
        self.assertIs(fragment_tool_call_delta(event, {}), event)

    def test_text_delta_untouched(self) -> None:
        payload = {
            "event": "content-block-delta",
            "index": 0,
            "delta": {"type": "text-delta", "text": "好的"},
        }
        event = _messages_event(payload)
        self.assertIs(fragment_tool_call_delta(event, {}), event)

    def test_non_messages_event_untouched(self) -> None:
        event = {
            "type": "event",
            "method": "tools",
            "params": {"namespace": [], "data": {"event": "tool-started"}},
            "seq": 72,
        }
        self.assertIs(fragment_tool_call_delta(event, {}), event)


if __name__ == "__main__":
    unittest.main()
