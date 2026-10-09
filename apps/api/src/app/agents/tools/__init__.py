"""Agent 可调用的沙箱工具集。

六个工具：bash / read_file / write_file / edit_file / glob / grep。

## 用法

工具需要绑定到一个**已就绪的沙箱实例**（`SandboxClient.create_sandbox()` 的
返回值），不是客户端本身——客户端持有 port-forward 隧道，只负责创建沙箱。
所以这里用工厂函数而不是模块级常量：

    from app.agents.client import sandbox_client, SANDBOX_NAMESPACE, WARMPOOL
    from app.agents.tools import build_tools

    sandbox = sandbox_client.create_sandbox(
        warmpool=WARMPOOL, namespace=SANDBOX_NAMESPACE
    )
    try:
        model_with_tools = get_model().bind_tools(build_tools(sandbox))
        ...
    finally:
        sandbox.terminate()

## 为什么是工厂而不是直接导出函数

模块级直接建工具会要求"当前沙箱"这个全局状态，而一个进程里会同时存在多个
会话、各自一个沙箱。工厂把沙箱关进闭包，互不干扰。

## 错误约定

所有工具都**不抛异常**，把失败信息当普通返回值交给模型（见 _common.safe_call）。
LangGraph 会把节点里冒泡的异常当成致命错误终止整张图，而"文件不存在"
"old_string 没匹配上"是 agent 正常工作流的一部分。
"""

from __future__ import annotations

from langchain_core.tools import BaseTool

from app.agents.tools._common import (
    SandboxLike,
    SandboxToolError,
    WORKSPACE,
)
from app.agents.tools.bash import build_bash_tool
from app.agents.tools.edit_file import build_edit_file_tool
from app.agents.tools.glob import build_glob_tool
from app.agents.tools.grep import build_grep_tool
from app.agents.tools.read_file import build_read_file_tool
from app.agents.tools.write_file import build_write_file_tool

__all__ = [
    "WORKSPACE",
    "SandboxLike",
    "SandboxToolError",
    "build_bash_tool",
    "build_edit_file_tool",
    "build_glob_tool",
    "build_grep_tool",
    "build_read_file_tool",
    "build_tools",
    "build_write_file_tool",
]


def build_tools(sandbox: SandboxLike) -> list[BaseTool]:
    """把六个工具绑定到同一个沙箱，返回可直接 bind_tools 的列表。

    顺序固定（bash 在前）：模型看到的工具顺序会影响它的选择倾向，
    稳定的顺序也让 prompt 缓存命中更可靠。
    """
    return [
        build_bash_tool(sandbox),
        build_read_file_tool(sandbox),
        build_write_file_tool(sandbox),
        build_edit_file_tool(sandbox),
        build_glob_tool(sandbox),
        build_grep_tool(sandbox),
    ]
