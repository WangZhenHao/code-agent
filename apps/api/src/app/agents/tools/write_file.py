"""write_file 工具：把内容写进沙箱里的文件（整体覆盖）。

对应上游客户端的 `sandbox.files.write()`。
"""

from __future__ import annotations

import shlex

from langchain_core.tools import BaseTool, tool

from app.agents.tools._common import (
    SandboxLike,
    SandboxToolError,
    run_shell,
    safe_call,
    to_sandbox_path,
)

DESCRIPTION = """把内容写入沙箱工作目录里的文件（整体覆盖已有内容）。

用于：新建文件，或整份替换一个文件的内容。
只想改动其中一小段时用 edit_file，别用本工具重写整个文件。

行为说明：
- 路径相对 /workspace，父目录不存在时会自动创建。
- 已有文件会被**完整覆盖**，不是追加。
- 写入的是 UTF-8 文本；二进制内容请用 bash 工具（base64 等）。"""


def _ensure_parent_dir(sandbox: SandboxLike, rel_path: str) -> None:
    """确保父目录存在。

    为什么不用 SDK 的 API：它没有 mkdir。底层 /upload 走 multipart，
    父目录不存在时行为取决于运行时的实现（可能报错，也可能静默落到别处），
    与其猜，不如先显式建好目录——代价一次往返，换来确定的语义。

    避免给 `a.py` 这种没有父目录的路径白跑一次 mkdir："." 直接跳过。
    """
    parent = rel_path.rsplit("/", 1)[0] if "/" in rel_path else ""
    if not parent or parent == ".":
        return
    result = run_shell(sandbox, f"mkdir -p -- {shlex.quote(parent)}", timeout=30)
    if not result.startswith("错误") and "[exit code:" in result:
        # mkdir 失败会让后续 write 报一个更难懂的错，这里先明说。
        raise SandboxToolError(f"创建父目录失败：{parent}\n{result}")


def write_file(sandbox: SandboxLike, file_path: str, content: str) -> str:
    """写入文件，返回一句确认（含字节数）。"""
    def _write() -> str:
        rel = to_sandbox_path(file_path)
        _ensure_parent_dir(sandbox, rel)
        try:
            sandbox.files.write(rel, content)
        except Exception as exc:  # noqa: BLE001
            raise SandboxToolError(f"写入失败：{rel}（{exc}）") from exc

        size = len(content.encode("utf-8"))
        line_count = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
        return f"已写入 {rel}（{size} 字节，{line_count} 行）"

    return safe_call(_write)


def build_write_file_tool(sandbox: SandboxLike) -> BaseTool:
    """产出绑定了该沙箱实例的 write_file 工具。"""

    @tool("write_file", description=DESCRIPTION)
    def _write_file(file_path: str, content: str) -> str:
        return write_file(sandbox, file_path, content)

    return _write_file
