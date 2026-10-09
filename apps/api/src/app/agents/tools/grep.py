"""grep 工具：按正则搜索文件内容。

上游客户端没有搜索能力，所以走沙箱里的 ripgrep（镜像已装，见 Dockerfile），
rg 不可用时退到 GNU grep。
"""

from __future__ import annotations

import shlex

from langchain_core.tools import BaseTool, tool

from app.agents.tools._common import (
    SandboxLike,
    SandboxToolError,
    run_shell_raw,
    safe_call,
    to_sandbox_path,
)

DEFAULT_HEAD_LIMIT = 100
MAX_HEAD_LIMIT = 1000

OUTPUT_MODES = ("content", "files_with_matches", "count")

# 与 glob.py 同一份排除清单，理由见那里的注释：/workspace 不是 git 仓库，
# 光靠 .gitignore 挡不住 node_modules。
EXCLUDED_DIRS = ("node_modules", ".next", ".git", "dist", "build", "coverage", ".venv")

# rg 用 -g '!dir/**'，grep 用 --exclude-dir=dir，两者语法不通，各拼各的。
_RG_SCRIPT = r"""
rg --color=never --no-heading {mode_flags} {filters} -e {pattern} {dir}
"""
_GREP_SCRIPT = r"""
grep -r -I {mode_flags} {filters} -e {pattern} {dir}
"""

DESCRIPTION = """在沙箱工作目录里按正则搜索文件内容。

用于：找某个符号的定义/引用、定位报错文本、看某段配置在哪。

行为说明：
- `pattern` 是 ripgrep 的正则（Rust regex 语法），不是 glob；
  要搜的字面量含特殊字符时记得转义（如 `\\(`、`\\.`）。
- `glob` 限定搜索的文件范围，如 `*.tsx`、`**/*.{ts,tsx}`。
- `output_mode`：`content` 显示匹配行（可配 context_before/after 带上下文）、
  `files_with_matches` 只列含匹配的文件、`count` 只给每个文件的匹配数。
- `line_numbers` 仅对 content 模式有意义（是否带行号）。
- 自动排除 node_modules、.git、.next、dist、build 等目录。"""


def _rg_filters(glob: str | None, case_insensitive: bool) -> list[str]:
    flags = [f"-g '!{d}/**'" for d in EXCLUDED_DIRS]
    if glob:
        # 用户给的 glob 先于排除项无关紧要——rg 的排除项写在后面照样生效。
        flags.append(f"-g {shlex.quote(glob)}")
    if case_insensitive:
        flags.append("-i")
    return flags


def _grep_filters(glob: str | None, case_insensitive: bool) -> list[str]:
    flags = [f"--exclude-dir={d}" for d in EXCLUDED_DIRS]
    if glob:
        flags.append(f"--include={shlex.quote(glob)}")
    if case_insensitive:
        flags.append("-i")
    return flags


def _mode_flags(
    output_mode: str,
    line_numbers: bool,
    context_before: int,
    context_after: int,
    *,
    for_rg: bool,
) -> list[str]:
    """按输出模式拼模式相关参数。rg 与 grep 在这几个开关上写法不同。"""
    if output_mode == "files_with_matches":
        return ["--files-with-matches"] if for_rg else ["-l"]
    if output_mode == "count":
        return ["--count"] if for_rg else ["-c"]

    flags: list[str] = []
    if line_numbers:
        flags.append("--line-number" if for_rg else "-n")
    if context_before:
        flags.append(
            f"--before-context={context_before}" if for_rg else f"-B{context_before}"
        )
    if context_after:
        flags.append(
            f"--after-context={context_after}" if for_rg else f"-A{context_after}"
        )
    return flags


def grep_files(
    sandbox: SandboxLike,
    pattern: str,
    path: str = ".",
    glob: str | None = None,
    output_mode: str = "content",
    case_insensitive: bool = False,
    line_numbers: bool = True,
    context_before: int = 0,
    context_after: int = 0,
    head_limit: int = DEFAULT_HEAD_LIMIT,
) -> str:
    """搜索文件内容，返回拼好的文本。"""
    if not pattern.strip():
        return "错误：pattern 不能为空"
    if output_mode not in OUTPUT_MODES:
        return (
            f"错误：output_mode 只能是 {' / '.join(OUTPUT_MODES)}，"
            f"收到 {output_mode!r}"
        )

    head_limit = min(max(int(head_limit), 1), MAX_HEAD_LIMIT)
    ctx_before = max(int(context_before), 0)
    ctx_after = max(int(context_after), 0)

    def _run() -> str:
        rel = to_sandbox_path(path)
        target = "." if rel == "." else rel
        quoted_pattern = shlex.quote(pattern)

        # rg 与 grep 的开关各拼一套，用 `command -v rg` 在沙箱里二选一。
        # 不用 `a || b` 串联：grep 无匹配时退出码是 1，会把已经成功的 rg 结果
        # 又跑一遍 grep，输出重复。
        rg_cmd = " ".join(
            [
                "rg --color=never --no-heading",
                *_mode_flags(
                    output_mode, line_numbers, ctx_before, ctx_after, for_rg=True
                ),
                *_rg_filters(glob, case_insensitive),
                "-e",
                quoted_pattern,
                shlex.quote(target),
            ]
        )
        grep_cmd = " ".join(
            [
                "grep -r -I",
                *_mode_flags(
                    output_mode, line_numbers, ctx_before, ctx_after, for_rg=False
                ),
                *_grep_filters(glob, case_insensitive),
                "-e",
                quoted_pattern,
                shlex.quote(target),
            ]
        )

        script = (
            f"if command -v rg >/dev/null 2>&1; then\n{rg_cmd}\n"
            f"else\n{grep_cmd}\nfi"
        )

        stdout, stderr, exit_code = run_shell_raw(sandbox, script, timeout=120)

        # rg/grep 的退出码：0=有匹配，1=**没有匹配**（正常结果，不是错误），
        # 2=真出错（正则语法有问题、路径不存在）。把 1 当错误报给模型，
        # 模型会徒劳地去"修"一个其实成功了的搜索。
        if exit_code == 2:
            detail = stderr.strip() or "（无错误详情）"
            raise SandboxToolError(f"搜索失败：{detail}")

        lines = [ln for ln in stdout.splitlines() if ln.strip()]
        if output_mode == "count":
            # rg --count 省略计数为 0 的文件，grep -c 会为每个扫到的文件印一行
            # `file:0`。两种后备路径的"0 匹配文件"表现必须一致，否则同一条指令
            # 在有无 rg 的镜像上给出的结果不一样，模型会据此得出不同结论。
            lines = [ln for ln in lines if not ln.rstrip().endswith(":0")]
            if not lines:
                return f"没有匹配 {pattern!r} 的内容（搜索目录：{target}）"
        elif not lines:
            return f"没有匹配 {pattern!r} 的内容（搜索目录：{target}）"

        shown = lines[:head_limit]
        body = "\n".join(shown)
        if len(lines) > head_limit:
            body += (
                f"\n\n... [共 {len(lines)} 行，仅显示前 {head_limit} 行。"
                "请缩小范围：限定 glob/path，或提高 head_limit]"
            )
        return body

    return safe_call(_run)


def build_grep_tool(sandbox: SandboxLike) -> BaseTool:
    """产出绑定了该沙箱实例的 grep 工具。"""

    @tool("grep", description=DESCRIPTION)
    def _grep(
        pattern: str,
        path: str = ".",
        glob: str | None = None,
        output_mode: str = "content",
        case_insensitive: bool = False,
        line_numbers: bool = True,
        context_before: int = 0,
        context_after: int = 0,
        head_limit: int = DEFAULT_HEAD_LIMIT,
    ) -> str:
        return grep_files(
            sandbox,
            pattern,
            path=path,
            glob=glob,
            output_mode=output_mode,
            case_insensitive=case_insensitive,
            line_numbers=line_numbers,
            context_before=context_before,
            context_after=context_after,
            head_limit=head_limit,
        )

    return _grep
