"""edit_file 工具：在文件里做精确的字符串替换。

对应上游客户端的 `sandbox.files.read()` + `write()` 组合——SDK 没有"编辑"原语，
所以这里读全文、替换、写回。行尾（LF/CRLF）与 BOM 原样保留。
"""

from __future__ import annotations

from langchain_core.tools import BaseTool, tool

from app.agents.tools._common import (
    SandboxLike,
    SandboxToolError,
    safe_call,
    to_sandbox_path,
)

DESCRIPTION = """在沙箱工作目录的文件里替换一段文本。

用于：修改已存在文件的一小部分内容。新建文件用 write_file。

行为说明：
- `old_string` 必须在文件中**唯一出现**，否则报错并在错误里给出出现次数——
  把上下文放宽一些（多带几行）即可定位到唯一一处。
- `replace_all=true` 时替换所有出现，用于重命名变量这类批量改动。
- 路径相对 /workspace，文件必须已存在。
- 缩进、换行必须与文件里完全一致，建议先用 read_file 看清原文再改。"""


def edit_file(
    sandbox: SandboxLike,
    file_path: str,
    old_string: str,
    new_string: str,
    replace_all: bool = False,
) -> str:
    """读-替换-写回。匹配不到就报错，让模型自己修正而不是静默改坏文件。"""
    if not old_string:
        return "错误：old_string 不能为空；要整体覆盖请用 write_file"
    if old_string == new_string:
        return "错误：old_string 与 new_string 相同，无需修改"

    def _edit() -> str:
        rel = to_sandbox_path(file_path)
        try:
            raw = sandbox.files.read(rel)
        except Exception as exc:  # noqa: BLE001
            raise SandboxToolError(f"读取失败：{rel}（{exc}）——文件不存在？") from exc

        if b"\x00" in raw[:8192]:
            raise SandboxToolError(f"{rel} 像是二进制文件，无法用字符串替换编辑。")

        # strict 解码：这是编辑而非阅读，用 errors="replace" 会把解不开的字节
        # 变成 U+FFFD，写回去就把原文件毁了。
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SandboxToolError(
                f"{rel} 不是 UTF-8 文本（{exc.reason} 位置 {exc.start}），"
                "拒绝编辑以免损坏文件。"
            ) from exc

        count = content.count(old_string)
        if count == 0:
            raise SandboxToolError(
                f"在 {rel} 中找不到 old_string。注意缩进和换行要完全一致，"
                "建议先用 read_file 查看原文。"
            )
        if count > 1 and not replace_all:
            raise SandboxToolError(
                f"old_string 在 {rel} 中出现了 {count} 次，无法确定改哪一处。"
                "请扩大上下文使其唯一，或设置 replace_all=true 全部替换。"
            )

        updated = content.replace(old_string, new_string)
        try:
            sandbox.files.write(rel, updated)
        except Exception as exc:  # noqa: BLE001
            raise SandboxToolError(f"写回失败：{rel}（{exc}）") from exc

        replaced = count if replace_all else 1
        return f"已编辑 {rel}（替换 {replaced} 处）"

    return safe_call(_edit)


def build_edit_file_tool(sandbox: SandboxLike) -> BaseTool:
    """产出绑定了该沙箱实例的 edit_file 工具。"""

    @tool("edit_file", description=DESCRIPTION)
    def _edit_file(
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> str:
        return edit_file(sandbox, file_path, old_string, new_string, replace_all)

    return _edit_file
