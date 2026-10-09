"""glob 工具：按文件名模式查找文件。

上游客户端只有 `files.list()`，它列的是**单层目录**，没法递归按模式找。
所以这里不套 SDK，而是把检索交给沙箱里的 ripgrep（镜像已装，见 Dockerfile）。
"""

from __future__ import annotations

import re
import shlex

from langchain_core.tools import BaseTool, tool

from app.agents.tools._common import (
    SandboxLike,
    run_shell_raw,
    safe_call,
    to_sandbox_path,
)

DEFAULT_MAX_RESULTS = 200

# 永远排除的目录。**必须显式写**：本项目的工作区 /workspace 里有 .gitignore
# （模板自带，排除 node_modules/.next），但它不是 git 仓库——ripgrep 默认只在
# git 仓库内才应用 .gitignore，不排的话 `rg --files` 会把几万个
# node_modules 文件一起列出来，一条工具结果直接撑爆上下文。
EXCLUDED_DIRS = ("node_modules", ".next", ".git", "dist", "build", "coverage", ".venv")

DESCRIPTION = """按文件名模式在沙箱工作目录里查找文件，返回匹配的路径列表。

用于：按扩展名或文件名定位文件，例如 `**/*.tsx`、`app/**/*.ts`、`*.json`。

行为说明：
- `pattern` 是 glob 语法：`*` 匹配任意多层路径，`?` 匹配单个字符，
  `{a,b}` 匹配多个候选（如 `**/*.{ts,tsx}`）。
- 结果按路径字典序排列（数量稳定，便于你对比两次结果）。
- 会自动排除 node_modules、.git、.next、dist、build 等目录。
- 超出上限时只返回前 N 条并提示，请用更精确的模式缩小范围。"""


def _exclude_flags() -> str:
    return " ".join(f"-g '!{d}/**'" for d in EXCLUDED_DIRS)


def _find_excludes() -> str:
    return " ".join(f"-not -path '*/{d}/*'" for d in EXCLUDED_DIRS)


def _find_name_expr(basename: str) -> str:
    """把 basename 通配翻成 find 的 -name 表达式，支持 `{a,b}` 花括号展开。

    find 不认花括号，`*.{ts,tsx}` 原样传进去永远匹配不到。展开成
    `\\( -name '*.ts' -o -name '*.tsx' \\)` 才能等价。
    """
    match = re.fullmatch(r"(.*)\{([^{}]*)\}", basename)
    if not match:
        return f"-name {shlex.quote(basename)}"

    prefix, alternatives = match.group(1), match.group(2)
    parts = [
        f"-name {shlex.quote(prefix + alt)}"
        for alt in alternatives.split(",")
        if alt
    ]
    if not parts:
        return f"-name {shlex.quote(basename)}"
    if len(parts) == 1:
        return parts[0]
    return "\\( " + " -o ".join(parts) + " \\)"


def _find_path_expr(pattern: str) -> str:
    """把模式里的**字面量**目录前缀翻成 find 的 -path 过滤。

    rg 的 `app/**/*.py` 只在 app/ 下找；find 只拿到 basename 就会全树乱找。
    这里取第一个含通配符的段之前的字面量目录作为过滤条件，尽量对齐语义。
    含通配符的目录段无法简单翻译（find 的 -path 需配合 shell 展开），
    所以遇到就停——这是降级路径下的已知近似。
    """
    head = pattern.rsplit("/", 1)[0] if "/" in pattern else ""
    literal: list[str] = []
    for seg in head.split("/"):
        if not seg or seg == "." or seg == "**":
            continue
        if any(ch in seg for ch in "*?["):
            break
        literal.append(seg)
    if not literal:
        return ""
    return f"-path {shlex.quote('*/' + '/'.join(literal) + '/*')}"


def glob_files(
    sandbox: SandboxLike,
    pattern: str,
    path: str = ".",
    max_results: int = DEFAULT_MAX_RESULTS,
) -> str:
    """按模式列出文件路径。"""
    if not pattern.strip():
        return "错误：pattern 不能为空"
    max_results = min(max(int(max_results), 1), 2000)

    def _run() -> str:
        rel = to_sandbox_path(path)
        target = "." if rel == "." else rel

        basename = pattern.rsplit("/", 1)[-1] or "*"
        find_expr = " ".join(
            part
            for part in (
                _find_name_expr(basename),
                _find_path_expr(pattern),
                _find_excludes(),
            )
            if part
        )

        # rg / find 二选一。不能用 `rg || find` 串联：rg 无匹配时退出码是 1，
        # 会再跑一遍 find，输出重复。
        script = (
            "if command -v rg >/dev/null 2>&1; then\n"
            f"  rg --files -g {shlex.quote(pattern)} {_exclude_flags()} "
            f"{shlex.quote(target)}\n"
            "else\n"
            f"  find {shlex.quote(target)} -type f {find_expr}\n"
            "fi"
        )

        # 用 raw 而不是 run_shell：run_shell 会把空输出格式化成 "(无输出)"，
        # 那是给人看的占位符，混进结果里会让下面"是否匹配到"的判断失灵
        # （"(无输出)" 非空，会被当成一条文件名返回给模型）。
        stdout, stderr, exit_code = run_shell_raw(sandbox, script, timeout=120)

        lines = [ln.strip() for ln in stdout.splitlines() if ln.strip()]
        # find 在某些平台会输出 "./x" 前缀，统一掉，便于模型直接拿去用。
        lines = [ln[2:] if ln.startswith("./") else ln for ln in lines]

        if not lines:
            if exit_code not in (0, 1):
                detail = stderr.strip() or f"exit code {exit_code}"
                return f"错误：查找失败：{detail}。请检查 pattern 与 path。"
            return (
                f"没有匹配 {pattern!r} 的文件（搜索目录：{target}；"
                f"已排除 {', '.join(EXCLUDED_DIRS)}）"
            )

        body = "\n".join(lines[:max_results])
        if len(lines) > max_results:
            body += (
                f"\n\n... [共 {len(lines)} 个文件，仅显示前 {max_results} 个。"
                "请用更精确的 pattern 或指定 path 缩小范围]"
            )
        return body

    return safe_call(_run)


def build_glob_tool(sandbox: SandboxLike) -> BaseTool:
    """产出绑定了该沙箱实例的 glob 工具。"""

    @tool("glob", description=DESCRIPTION)
    def _glob(
        pattern: str,
        path: str = ".",
        max_results: int = DEFAULT_MAX_RESULTS,
    ) -> str:
        return glob_files(sandbox, pattern, path, max_results)

    return _glob
