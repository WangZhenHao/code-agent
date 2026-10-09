"""read_file 工具：读沙箱里的文本文件，带行号。

对应上游客户端的 `sandbox.files.read()`。
"""

from __future__ import annotations

from langchain_core.tools import BaseTool, tool

from app.agents.tools._common import SandboxLike, read_text_file, safe_call

# 默认行数上限。与 Claude Code 的 Read 对齐：一次 2000 行，够看完整文件，
# 又不会让超大文件的输出撑爆上下文。
DEFAULT_LIMIT = 2000
MAX_LIMIT = 10000

DESCRIPTION = """读取沙箱工作目录里的文本文件，返回内容并带行号。

用于：查看源码、配置、日志等文本文件。
不要用于二进制文件或超大文件——请用 bash 工具配合 head/tail/sed 处理。

行为说明：
- 路径相对 /workspace。传 `/workspace/a.py`、`a.py`、`/a.py` 都可以，会归一处理。
- 默认最多返回 2000 行，超出部分请用 offset/limit 分段读。
- 行号是 1 起的，与返回内容里的数字前缀一致。"""


def read_file(
    sandbox: SandboxLike,
    file_path: str,
    offset: int = 1,
    limit: int = DEFAULT_LIMIT,
) -> str:
    """读文件并按 Claude Code 的风格加行号返回。"""
    if limit <= 0:
        return "错误：limit 必须大于 0"
    limit = min(int(limit), MAX_LIMIT)
    start = max(int(offset), 1)

    def _read() -> str:
        content = read_text_file(sandbox, file_path)
        lines = content.splitlines()

        if not lines:
            return f"({file_path} 是空文件)"

        total = len(lines)
        if start > total:
            return (
                f"错误：offset={start} 超出文件末尾"
                f"（{file_path} 共 {total} 行）"
            )

        window = lines[start - 1 : start - 1 + limit]
        # 行号宽度按窗口内最大行号算，窄文件不会出现难看的一堆空格。
        width = len(str(start - 1 + len(window)))
        numbered = "\n".join(
            f"{i:>{width}}\t{text}" for i, text in enumerate(window, start=start)
        )

        shown_end = start - 1 + len(window)
        if shown_end < total:
            numbered += (
                f"\n\n... [仅显示第 {start}-{shown_end} 行，共 {total} 行。"
                f"继续读请用 offset={shown_end + 1}]"
            )
        return numbered

    return safe_call(_read)


def build_read_file_tool(sandbox: SandboxLike) -> BaseTool:
    """产出绑定了该沙箱实例的 read_file 工具。"""

    @tool("read_file", description=DESCRIPTION)
    def _read_file(
        file_path: str,
        offset: int = 1,
        limit: int = DEFAULT_LIMIT,
    ) -> str:
        return read_file(sandbox, file_path, offset, limit)

    return _read_file
