"""Agent 可调用的沙箱工具集。

七个工具：bash / read_file / write_file / edit_file / glob / grep / read_skill。
其中只读的是 read_file / glob / grep / read_skill，其余三个会改动沙箱。

read_skill 是个例外：它读的是 API 主机上的技能包目录（public/skills/），
不经过沙箱，所以构造时不接收 sandbox 参数——其余六个都绑在同一个沙箱实例上。

## 用法

工具需要绑定到一个**已就绪的沙箱实例**（`SandboxClient.create_sandbox()` 的
返回值），不是客户端本身——客户端持有 port-forward 隧道，只负责创建沙箱。
所以这里用工厂函数而不是模块级常量：

    from app.api.sandbox.client import sandbox_client, SANDBOX_NAMESPACE, WARMPOOL
    from app.agents.tools import create_tools

    sandbox = sandbox_client.create_sandbox(
        warmpool=WARMPOOL, namespace=SANDBOX_NAMESPACE
    )
    try:
        # mode 决定给哪些工具：plan 给只读的一套（含只读 bash），agent 给全部
        model_with_tools = get_model().bind_tools(create_tools(sandbox, mode))
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
from app.agents.tools.skill import build_read_skill_tool
from app.agents.tools.write_file import build_write_file_tool
from app.db.models.session import MessageMode

__all__ = [
    "READ_ONLY_TOOL_NAMES",
    "WORKSPACE",
    "SandboxLike",
    "SandboxToolError",
    "build_bash_tool",
    "build_edit_file_tool",
    "build_glob_tool",
    "build_grep_tool",
    "build_read_file_tool",
    "build_read_skill_tool",
    "build_tools",
    "build_write_file_tool",
    "create_tools",
]

# 只读工具的名字集合。plan 模式下只给它这几个——规划阶段的任务是"看清楚再写计划"，
# 给了写权限就会在用户还没审阅计划时先把代码改了，plan 也就白做了。
#
# read_skill 在里面：它读的是 API 主机上的技能包文档（public/skills/），
# 既不碰沙箱也不写任何东西，而规划阶段正好需要它——先看看有没有相关技能再定方案。
#
# bash 在里面，但它是**收窄过的**（readonly=True，见 guard.py），不是普通 bash。
# 所以 create_tools 不能按名字过滤出一份列表来用——那会把无限制的 bash 交给
# plan。正确的用法是：按这个集合判断某工具在 plan 下要不要给，bash 单独按
# readonly 构造。名字集合与构造方式这两件事必须分开，别把它们合并。
#
# 用名字的集合而不是硬编码一份工具列表：过滤规则靠 name 匹配，不依赖构造顺序，
# 以后往 build_tools 里加新工具时，只要它不在这个集合里就自动只在 agent 模式可见
# （新工具默认带写权限，所以加之前先想清楚它是不是只读的）。
READ_ONLY_TOOL_NAMES = frozenset({"bash", "read_file", "glob", "grep", "read_skill"})


def build_tools(sandbox: SandboxLike) -> list[BaseTool]:
    """把七个工具绑定到同一个沙箱，返回可直接 bind_tools 的列表。

    这里给的是**完整**工具集（agent 模式）。plan 模式要的是 create_tools。
    顺序固定（bash 在前）：模型看到的工具顺序会影响它的选择倾向，
    稳定的顺序也让 prompt 缓存命中更可靠。

    read_skill 建的时候不传 sandbox（它读主机上的技能包，与沙箱无关），
    但顺序照样固定：create_tools 的 plan 分支要取它的同序子序列。
    """
    return [
        build_bash_tool(sandbox),
        build_read_file_tool(sandbox),
        build_write_file_tool(sandbox),
        build_edit_file_tool(sandbox),
        build_glob_tool(sandbox),
        build_grep_tool(sandbox),
        build_read_skill_tool(),
    ]


def create_tools(sandbox: SandboxLike, mode: MessageMode) -> list[BaseTool]:
    """按模式绑定工具：plan 给只读的一套，agent 给全部。

    plan 分支是**显式构造**而不是从 build_tools 里 filter——bash 在两种模式下
    同名但不同物（readonly 开关在构造时决定），filter 只能按名字挑，会把完整版
    bash 挑给 plan。构造顺序与 build_tools 保持一致（同序子序列），
    模型的工具偏好顺序才不会在切模式时翻个儿。

    这里只是**收窄工具清单**，不是权限边界——plan 的 bash 仍跑在同一个沙箱里，
    看的是命令文本（见 guard.py 顶部的说明）。真拦高危操作得靠调用前的确认钩子。

    mode 收 MessageMode 而不是 str：调用方（节点）拿到的本来就是枚举，
    传字符串进来会在这里静默退化成"非 plan 即全部"，枚举能逼出类型错误。
    非法值同理——除 plan 外的任何取值都当 agent 处理，这是有意的：
    agent 是能力最全的一档，退到它身上不会让节点因为一个坏字段而空手。
    """
    if mode == MessageMode.plan:
        return [
            build_bash_tool(sandbox, readonly=True),
            build_read_file_tool(sandbox),
            build_glob_tool(sandbox),
            build_grep_tool(sandbox),
            build_read_skill_tool(),
        ]
    return build_tools(sandbox)

