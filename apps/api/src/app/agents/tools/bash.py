"""bash 工具：在沙箱里执行 shell 命令。

对应上游客户端的 `sandbox.commands.run()`（见 agentic-sandbox-client 的 Usage
Examples）。没有直接透传，原因见 _common.shell_command：运行时的 /execute 不经
shell，透传过去连 `&&` 都用不了。

两种形态：默认是完整 bash（agent 模式）；`build_bash_tool(sandbox, readonly=True)`
产出只读版本（plan 模式），执行前先过 guard.check_readonly_command。
"""

from __future__ import annotations

from langchain_core.tools import BaseTool, tool

from app.agents.tools._common import SandboxLike, run_shell, safe_call
from app.agents.tools.guard import check_readonly_command

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

# 只读版本的描述。与 guard 的白名单逐条对齐——描述了做不到的事，
# 模型就会反复试然后卡在拒因里。
READ_ONLY_DESCRIPTION = """在沙箱的 /workspace 目录下执行**只读** bash 命令，用于查看项目。

允许：ls / cat / head / tail / nl / wc / file / stat / tree / du / pwd /
diff / sort / uniq / cut / tr / jq / xxd / od / strings / which / date，
以及 git 的查询子命令（status / log / diff / show / blame / grep 等）。
可以用管道 `|` 和 `&&` 串联这些命令。

不允许（会被拦下并把原因返回给你）：任何写文件的命令（rm / mv / cp / touch /
mkdir / tee ...）、`sed -i`、重定向（`>` / `>>`）、命令替换（`$()`）、子 shell、
`;` 串联，以及 bash / python 这类能把命令藏进参数的转发器。

行为说明：
- 命令在 /workspace 下执行，退出码非 0 不会报错，会附在输出末尾。
- 单次输出超过 30000 字符会被截断，请用 head/tail 或更精确的命令缩小范围。
- 被拒绝时不要换等价写法重试：本模式确实不给写权限，需要改动请在计划里写清楚。"""

# 拒因提示。模型看不到系统提示里可能缺白名单，所以拒因里补一句去哪看。
REJECT_HINT = "（plan 模式只放行查看类命令；按条件找文件请用 glob / grep 工具）"


def run_bash(sandbox: SandboxLike, command: str, timeout: int = DEFAULT_TIMEOUT) -> str:
    """执行命令，返回 stdout/stderr/退出码拼成的文本。"""
    if not command.strip():
        return "错误：命令不能为空"

    # 夹一道上限：模型偶尔会传 timeout=99999，那会一直占着沙箱连接不放。
    if timeout <= 0:
        timeout = DEFAULT_TIMEOUT
    timeout = min(int(timeout), MAX_TIMEOUT)

    return safe_call(lambda: run_shell(sandbox, command, timeout=timeout))


def build_bash_tool(sandbox: SandboxLike, readonly: bool = False) -> BaseTool:
    """产出绑定了该沙箱实例的 bash 工具。

    用闭包而不是 functools.partial 绑参数：partial 会让 Pydantic 的 schema 推断
    失败（认不出被包装的函数）。闭包则保留真实签名，工具参数的 JSON Schema
    能被正确生成，模型看到的参数列表才是对的。

    readonly=True 时多一道 guard 校验。拒因是**普通返回值**而不是异常，
    理由同整个工具集：异常会冒泡出节点，被 LangGraph 当成致命错误终止整张图。
    """
    description = READ_ONLY_DESCRIPTION if readonly else DESCRIPTION

    @tool("bash", description=description)
    def bash(command: str, timeout: int = DEFAULT_TIMEOUT) -> str:
        if readonly:
            rejection = check_readonly_command(command)
            if rejection is not None:
                return f"{rejection}\n{REJECT_HINT}"
        return run_bash(sandbox, command, timeout)

    return bash
