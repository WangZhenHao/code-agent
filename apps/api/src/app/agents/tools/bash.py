"""bash 工具：在沙箱里执行 shell 命令。

对应上游客户端的 `sandbox.commands.run()`（见 agentic-sandbox-client 的 Usage
Examples）。没有直接透传，原因见 _common.shell_command：运行时的 /execute 不经
shell，透传过去连 `&&` 都用不了。
"""

from __future__ import annotations

from langchain_core.tools import BaseTool, tool

from app.agents.tools._common import SandboxLike, run_shell, safe_call

DEFAULT_TIMEOUT = 120
MAX_TIMEOUT = 600

DESCRIPTION = """在沙箱的 /workspace 目录下执行 bash 命令。

用于：跑构建/测试/lint、安装依赖、git 操作、查看目录结构，
以及任何需要管道、重定向、通配符的场景。

行为说明：
- 命令在 /workspace 下执行，完整 shell 语法可用（管道、&&、$VAR、通配符）。
- 退出码非 0 不会报错，会把它附在输出末尾，你据此判断下一步。
- 单次输出超过 30000 字符会被截断，请用更精确的命令或 head/tail 缩小范围。
- 需要交互的命令（vim、npm init 的问答）会挂起直到超时，请改用非交互参数。"""


def run_bash(sandbox: SandboxLike, command: str, timeout: int = DEFAULT_TIMEOUT) -> str:
    """执行命令，返回 stdout/stderr/退出码拼成的文本。"""
    if not command.strip():
        return "错误：命令不能为空"

    # 夹一道上限：模型偶尔会传 timeout=99999，那会一直占着沙箱连接不放。
    if timeout <= 0:
        timeout = DEFAULT_TIMEOUT
    timeout = min(int(timeout), MAX_TIMEOUT)

    return safe_call(lambda: run_shell(sandbox, command, timeout=timeout))


def build_bash_tool(sandbox: SandboxLike) -> BaseTool:
    """产出绑定了该沙箱实例的 bash 工具。

    用闭包而不是 functools.partial 绑参数：partial 会让 Pydantic 的 schema 推断
    失败（认不出被包装的函数）。闭包则保留真实签名，工具参数的 JSON Schema
    能被正确生成，模型看到的参数列表才是对的。
    """

    @tool("bash", description=DESCRIPTION)
    def bash(command: str, timeout: int = DEFAULT_TIMEOUT) -> str:
        return run_bash(sandbox, command, timeout)

    return bash
