"""落库前的瘦身：`messages.parts` 不该再存工具正文。

正文统一在 `tool_calls` 表里，前端按 `tool_call_id` 查。这里要钉住的是两个容易漏的副本：
ai 消息的 `tool_calls[]` 和 `content[]` 里的 tool_call 块是同一份 args 的两处存法，
只剥一处，另一处仍会把几十 KB 的源码写进 messages 表。

跑法：uv run python -m unittest tests.agents.test_message_persistence
"""

from __future__ import annotations

import unittest

from langchain_core.messages import AIMessage, ToolMessage

from app.agents.message_persistence import _part_for_storage

_CODE = "export default function RootLayout() { return null }\n" * 10


class PartForStorageTest(unittest.TestCase):
    def test_ai_message_tool_call_args_dropped_in_both_copies(self) -> None:
        msg = AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "call_1",
                    "name": "write_file",
                    "args": {
                        "content": _CODE,
                        "file_path": "/workspace/app/layout.tsx",
                    },
                },
                {
                    "id": "call_2",
                    "name": "edit_file",
                    "args": {
                        "old_string": _CODE,
                        "new_string": _CODE + "x",
                        "file_path": "/workspace/app/page.tsx",
                    },
                },
            ],
        )
        msg.content = [dict(call, type="tool_call") for call in msg.tool_calls]

        part = _part_for_storage(msg)
        data = part["data"]

        for call in data["tool_calls"]:
            self.assertNotIn("content", call["args"])
            self.assertNotIn("old_string", call["args"])
            self.assertNotIn("new_string", call["args"])
            self.assertIn("file_path", call["args"])
        for block in data["content"]:
            self.assertNotIn("content", block["args"])
            self.assertNotIn("old_string", block["args"])
            self.assertNotIn("new_string", block["args"])
        self.assertNotIn(_CODE, str(part))

    def test_tool_message_keeps_only_ids(self) -> None:
        msg = ToolMessage(content=_CODE, tool_call_id="call_1", id="tool_1")

        data = _part_for_storage(msg)["data"]

        self.assertEqual(
            data, {"type": "tool", "id": "tool_1", "tool_call_id": "call_1"}
        )


if __name__ == "__main__":
    unittest.main()
