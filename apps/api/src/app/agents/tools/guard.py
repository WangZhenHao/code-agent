"""plan 模式下 bash 的只读校验。

## 这个模块解决什么

plan 模式原本不给 bash，调研时不够用：`git log` 看提交历史、`wc -l` 估规模、
`ls` 看目录全貌，只读工具（read_file/glob/grep）都覆盖不到。但直接把 bash
给过去，模型就有机会在用户还没审阅计划时把代码改了——plan 也就白做了。

所以这里做一道**命令白名单**：把一条命令按 `|` / `&&` / `||` 切段，每段的
首个命令必须在这张表里；表里没有的一律拒，并把拒因当普通文本回给模型。
用白名单而不是黑名单，是因为黑名单的漏面太大——`python -c "open('a','w')"`、
`tar -xf`、`git stash`、`curl -o` 每一个都要单独想，漏一个就是一次真实的破坏。

## ⚠️ 这不是安全边界

这是**防误触**，不是沙箱。判定完全基于命令行文本，绕过的路子是存在的：
白名单里的 `git` 配 `--output=` 之类的选项、`date -s` 改系统时间、
藏在参数里的写操作，静态检查都看不穿。真正的边界得靠沙箱侧的权限
（降权用户 / 只读挂载），本项目当前**没有**这一层。

因此：不要依赖这里来防一个刻意破坏的 agent，它的职责只是让 plan 模式下的
模型够用、且不会顺手改掉文件。上游的确认钩子仍是高危操作的兜底。

## 为什么分词用 shlex 而不是正则

`grep "a|b" f.py` 里的 `|` 在引号内，正则硬切会把这条合法命令切坏；
`shlex.split` 认得引号，切出来就是一个词。反过来，`shlex` 解析失败
（引号没闭合）本身就是坏命令，直接拒。
"""

from __future__ import annotations

import shlex

__all__ = [
    "DENIED_COMMANDS",
    "GIT_READ_ONLY_SUBCOMMANDS",
    "READ_ONLY_COMMANDS",
    "check_readonly_command",
]


# 只读白名单。表里的命令都只是"看"，不改文件也不改仓库状态。
#
# 刻意**不**收录的几类（不是遗漏，是决定）：
#   - 转发器：bash/sh/env/xargs/command —— 它们能把任意命令藏在参数里，
#     校验第一段等于没校验；
#   - 解释器：python/node/uv/npm/pip/make —— 一行 `-c` 就能写文件；
#   - 改状态的：rm/mv/cp/dd/tee/truncate/install/ln/tar/curl/wget...
#   - `find`：`-exec` / `-delete` 就在它自己的参数里，而按条件找文件
#     本来就是 glob 工具的活。
READ_ONLY_COMMANDS: frozenset[str] = frozenset(
    {
        "ls",
        "cat",
        "head",
        "tail",
        "nl",
        "wc",
        "file",
        "stat",
        "tree",
        "du",
        "pwd",
        "echo",
        "printf",
        "diff",
        "sort",
        "uniq",
        "cut",
        "tr",
        "basename",
        "dirname",
        "realpath",
        "readlink",
        "which",
        "date",
        "xxd",
        "od",
        "strings",
        "less",
        "more",
        "jq",
        "git",  # 只在子命令也命中 GIT_READ_ONLY_SUBCOMMANDS 时放行
    }
)

# git 只放行查询类子命令。
#
# 不留 `branch` / `remote` / `stash` / `config`：它们不带参数时确实是查询，
# 但一句 `git config user.name x` 就是写操作，而模型写这类命令时通常是顺手
# 打出来的——分不清"想查"还是"想改"的，就不要放进来。
GIT_READ_ONLY_SUBCOMMANDS: frozenset[str] = frozenset(
    {
        "status",
        "log",
        "diff",
        "show",
        "blame",
        "grep",
        "shortlog",
        "rev-parse",
        "describe",
        "cat-file",
        "ls-files",
        "ls-tree",
        "show-ref",
    }
)

# 黑名单只用于**给出更清楚的报错**：命中它说明这是个明确写操作，
# 可以直接说"这是写操作"，而不是笼统地说"不在白名单里"。
# 判定逻辑不依赖这张表——不在 READ_ONLY_COMMANDS 里的一律拒。
DENIED_COMMANDS: frozenset[str] = frozenset(
    {
        "rm",
        "mv",
        "cp",
        "dd",
        "chmod",
        "chown",
        "chgrp",
        "mkdir",
        "rmdir",
        "touch",
        "ln",
        "tee",
        "truncate",
        "install",
        "rsync",
        "tar",
        "zip",
        "unzip",
        "gzip",
        "gunzip",
        "curl",
        "wget",
        "scp",
        "ssh",
        "git",
        "npm",
        "npx",
        "pnpm",
        "yarn",
        "pip",
        "uv",
        "make",
        "python",
        "python3",
        "node",
        "deno",
        "bun",
        "perl",
        "ruby",
        "php",
        "tee",
        "bash",
        "sh",
        "zsh",
        "dash",
        "env",
        "xargs",
        "sudo",
        "su",
        "doas",
        "find",
        "command",
        "exec",
        "eval",
        "source",
        "setpriv",
        "nohup",
        "crontab",
        "systemctl",
        "service",
        "kill",
        "pkill",
    }
)

# 参数里出现就拒的开关。整条命令扫一遍，不限位置——`sed -i` 的 `-i` 可能在
# 任何一段里，按"第一个命令的参数"去挑位置反而容易漏。
GUARDED_FLAGS: frozenset[str] = frozenset(
    {
        "-i",
        "--in-place",
        "-exec",
        "-execdir",
        "-ok",
        "-okdir",
        "--delete",
        "-delete",
    }
)

# 直接拒的 shell 元字符。分两种：
#   - 结构类 `& ; ( ) { }` —— 子 shell、后台、命令串联，能让校验看到的分段
#     和实际执行的不是一回事；
#   - 展开类 `> < ` $` —— 重定向和命令替换（`$()`、`${}`）本身就是写入口。
#
# 管道 `|` 和逻辑连接 `&&` / `||` **不在这里**，它们是分段用的，各自单独处理。
_DENY_CHARS = frozenset("&;(){}><`$")

# 赋值前缀。`FOO=1 ls` 里 `ls` 才是要校验的命令，跳过这些词往后找。
# 注意 `export FOO=1` 被 shlex 拆成两个词，所以这里既有"含 = 的词"这一条，
# 也有 `export` 这个关键字本身；否则 `export` 会被当成命令名直接拒掉。
_ASSIGNMENT_PREFIXES = ("export", "declare")


def check_readonly_command(command: str) -> str | None:
    """校验一条命令是否只读。

    返回 `None` 表示放行；否则返回一句给模型看的中文拒因。返回值而不是抛异常，
    因为调用方（bash 工具）要把拒因当普通工具结果交给模型——工具层约定不抛异常。

    多段（`a && b | c`）是**逐段**校验的，一段不合格整条拒。
    """
    text = (command or "").strip()
    if not text:
        return "错误：命令不能为空"

    try:
        tokens = shlex.split(text, posix=True)
    except ValueError:
        # 引号没闭合这类。交给 shell 也是报错，不如在这里说清楚。
        return "错误：命令引号不闭合，无法解析。请检查引号是否配对。"

    if not tokens:
        return "错误：命令不能为空"

    # 先扫元字符。放在分段之前：元字符会改变分段结果，必须先确认它不存在，
    # 分段才有意义。
    for token in tokens:
        for ch in token:
            if ch in _DENY_CHARS:
                return _reject_char(ch)

    for segment in _split_segments(tokens):
        if not segment:
            return "错误：命令中有空的分段（多余的 | 或 &&）。"

        command_name = _first_command_name(segment)
        if command_name is None:
            # 整段都是赋值，没有实际命令。没有副作用，放行。
            continue

        guarded = _guarded_flag(segment)
        if guarded is not None:
            return _reject_flag(command_name, guarded)

        reason = _check_one(command_name, segment)
        if reason is not None:
            return reason

    return None


# ---------------------------------------------------------------------------
# 内部实现
# ---------------------------------------------------------------------------


def _split_segments(tokens: list[str]) -> list[list[str]]:
    """按 `|` / `&&` / `||` 把词序列切成命令段。

    元字符已经在调用方筛过，所以这里遇到的连接符就只有这三种。
    """
    segments: list[list[str]] = [[]]
    for token in tokens:
        if token in ("|", "&&", "||"):
            segments.append([])
            continue
        segments[-1].append(token)
    return segments


def _first_command_name(segment: list[str]) -> str | None:
    """取一段里真正的命令名，跳过 `FOO=bar` 这类赋值前缀。

    返回 None 表示整段都是赋值，没有要执行的命令。
    """
    for token in segment:
        if token in _ASSIGNMENT_PREFIXES or _is_assignment(token):
            continue
        return token
    return None


def _is_assignment(token: str) -> bool:
    """是不是 `FOO=bar` 这种赋值词。

    逐个字符找 `=` 而不是 `split("=")`：`a=b=c` 和 `a[0]=1` 都要认出来，
    而以 `=` 开头（`=x`）或整段就是 `=` 的不算合法赋值词，交给白名单拒掉。
    """
    head = token.split("=", 1)[0]
    return bool(head) and all(
        ch.isalnum() or ch == "_" or ch == "[" or ch == "]" for ch in head
    )


def _guarded_flag(segment: list[str]) -> str | None:
    """段内是否出现被禁的参数开关，命中则返回它。"""
    for token in segment:
        if token in GUARDED_FLAGS:
            return token
    return None


def _check_one(command_name: str, segment: list[str]) -> str | None:
    """校验单个命令（已跳过赋值前缀的那一段）。"""
    if command_name in READ_ONLY_COMMANDS:
        if command_name == "git":
            return _check_git(segment)
        return None

    if command_name in DENIED_COMMANDS:
        return (
            f"错误：plan 模式不允许「{command_name}」（这是写操作）。"
            "plan 模式只能用查看类命令，先把计划写出来交给用户审阅。"
        )

    return (
        f"错误：plan 模式不允许「{command_name}」（不在只读白名单里）。"
        "只读命令见系统提示；按条件找文件请改用 glob / grep 工具。"
    )


def _check_git(segment: list[str]) -> str | None:
    """校验 git 子命令。`git` 后面的第一个非 `-` 开头的词就是子命令。"""
    for token in segment[1:]:
        if token.startswith("-"):
            # 全局选项（`-C`、`--no-pager` 等）跳过，继续找子命令。
            continue
        if token in GIT_READ_ONLY_SUBCOMMANDS:
            return None
        return (
            f"错误：plan 模式不允许「git {token}」。"
            "git 只放行了状态/历史/差异这类查询子命令"
            "（status/log/diff/show/blame/grep 等）。"
        )

    # `git` 后面全是选项，或者干脆没跟子命令——都会打出用法说明，没有副作用。
    return None


def _reject_char(ch: str) -> str:
    hints = {
        ">": "输出重定向会把内容写进文件",
        "<": "输入重定向",
        "&": "后台执行 / 命令串联",
        ";": "命令串联",
        "(": "子 shell",
        ")": "子 shell",
        "{": "花括号展开",
        "}": "花括号展开",
        "`": "命令替换",
        "$": "命令替换 / 变量展开",
    }
    return (
        f"错误：plan 模式不允许 shell 元字符「{ch}」"
        f"（{hints.get(ch, '会改变命令的解析方式')}）。"
        "只能执行直白的只读命令，管道与 && 之外不要用其他 shell 语法。"
    )


def _reject_flag(command_name: str, flag: str) -> str:
    return (
        f"错误：plan 模式不允许「{command_name}」带 {flag} 参数"
        "（这会原地修改文件或执行子进程）。"
    )
