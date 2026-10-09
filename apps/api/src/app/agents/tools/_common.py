"""六个沙箱工具的共用底座。

每个工具都要做同样三件事：拼 shell 命令、把模型给的路径翻译成文件 API 认的相对路径、
裁剪过长的输出。写六遍必然漂移，所以集中在这里。

## 为什么工具函数是**同步**的

k8s-agent-sandbox 的客户端基于 requests，全套同步 API。本项目的图跑在 asyncio 里
（FastAPI + LangGraph），但 LangChain 的 `ainvoke` 对同步工具会自动丢进线程池执行，
不会阻塞事件循环。所以这里保持同步——把它改成 async 只是给阻塞调用套一层
`async def`，反而会让事件循环真的卡住。
"""

from __future__ import annotations

import shlex
from typing import Any, Protocol, runtime_checkable


# 沙箱内的工作根目录。必须与镜像的 SANDBOX_BASE_DIR 一致（见
# deploy/api/sandbox-image/Dockerfile），它同时决定两件事：
#   - /execute 执行命令时的 cwd
#   - 文件 API（upload/download/list）的根目录
# 两者是同一个值，所以文件 API 的"相对路径"和 shell 里的"相对路径"指向同一处。
WORKSPACE = "/workspace"

# 单次工具调用的输出上限（字符数）。工具结果会原样进模型上下文，
# 一条 `cat` 大文件或 `find /` 的输出能轻易吃掉几万 token，且后续每轮都要重付。
# 截断并显式提示，模型可以改用更精确的命令重试。
MAX_OUTPUT_CHARS = 30_000

# 文件内容读取上限（字节）。read() 会把整个文件读进内存，这里设一道闸，
# 超了就让模型改用 bash + sed/head 分段看。
MAX_READ_BYTES = 5 * 1024 * 1024


# ---------------------------------------------------------------------------
# 沙箱接口的结构化描述
# ---------------------------------------------------------------------------
# 只用 SDK 真正用到的那几个方法，而不是 import Sandbox 做具体类型标注。两个好处：
#   - 单元测试可以传一个十几行的假对象，不需要起集群、不需要 port-forward；
#   - 换连接模式（Tunnel / Gateway / In-Cluster）或换运行时，只要方法还在就兼容。
# runtime_checkable 让 isinstance 检查成为可能，便于在工厂里尽早报错。


class CommandResult(Protocol):
    """commands.run() 的返回值（对应 SDK 的 ExecutionResult）。"""

    stdout: str
    stderr: str
    exit_code: int


class CommandAPI(Protocol):
    def run(self, command: str, timeout: int = ...) -> CommandResult: ...


class FilesAPI(Protocol):
    def read(self, path: str, timeout: int = ...) -> bytes: ...

    def write(
        self,
        path: str,
        content: bytes | str,
        timeout: int = ...,
    ) -> Any: ...


@runtime_checkable
class SandboxLike(Protocol):
    """一个已就绪的沙箱句柄——即 SandboxClient.create_sandbox() 的返回值。

    注意不是 SandboxClient 本身：客户端持有 port-forward 隧道，用于**创建**沙箱；
    工具要操作的是被创建出来的那一个沙箱实例。
    """

    commands: CommandAPI
    files: FilesAPI


class SandboxToolError(Exception):
    """工具层的可预期错误。

    单独一个类型是为了让上层能区分"模型用错了工具"（路径写错、old_string 没匹配上）
    和"沙箱基础设施坏了"（连不上、隧道断了）。前者应该把错误回灌给模型让它自己改，
    后者要冒泡上去报错。
    """


def shell_command(script: str) -> str:
    """把一段 shell 脚本包成单条可直接交给 /execute 的命令。

    官方运行时的 /execute 用 `shlex.split` 拆参数后**直接 exec，不经 shell**，
    所以 `npm install && npm run dev` 会被当成一个叫 "npm install && npm run dev"
    的可执行文件——注释里那句"已知限制"就是指这个。

    统一套一层 `bash -c` 就绕开了：脚本里的管道、&&、通配符、变量展开全部可用。
    用单引号包裹，内部的 `'` 换成 `'"'"'`（关引号 → 插入字面单引号 → 重开引号）。
    这样无论运行端是 shlex.split 后 exec，还是 shell=True，结果都一样。
    """
    quoted = "'" + script.replace("'", "'\"'\"'") + "'"
    return f"bash -c {quoted}"


def to_sandbox_path(path: str) -> str:
    """把模型给的路径归一成文件 API 认的相对路径。

    **这是最容易踩的坑**：文件 API 内部会对路径做 `normpath(path).lstrip("/")`，
    然后拼到 /workspace 下。于是 `/workspace/src/a.py` 被剥成 `workspace/src/a.py`，
    最终落到 `/workspace/workspace/src/a.py` —— 路径凭空多一层，报"文件不存在"。

    模型看过 bash 的输出后天然倾向写绝对路径，所以这里主动把 `/workspace/` 前缀
    吃掉，同时接受带前缀、不带前缀、前导斜杠三种写法，都归到同一个相对路径。

    同时拒绝 `..`：文件 API 本就会拦（抛 ValueError），但它的报错文案对模型不友好，
    这里换成一句能看懂的。控制字符一并拦掉，理由同 SDK 里的注释（NUL 会在
    syscall 层截断文件名，是种绕过）。
    """
    p = (path or "").strip().replace("\\", "/")
    if not p:
        raise SandboxToolError("路径不能为空")

    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in p):
        raise SandboxToolError(f"路径含控制字符，拒绝处理：{path!r}")

    # 吃掉 /workspace 前缀（含只写 "/workspace" 或 "workspace" 的情况）。
    if p == WORKSPACE or p == WORKSPACE.lstrip("/"):
        return "."
    for prefix in (WORKSPACE + "/", WORKSPACE.lstrip("/") + "/"):
        if p.startswith(prefix):
            p = p[len(prefix):]
            break

    # 剩下的前导斜杠直接当成"相对根的绝对路径"（`/src/a.py` 等价 `src/a.py`）。
    segments: list[str] = []
    for seg in p.lstrip("/").split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            raise SandboxToolError(
                f"路径不能跳出工作目录：{path!r}。工作根是 {WORKSPACE}，"
                "如需访问其外请用 bash 工具。"
            )
        segments.append(seg)

    if not segments:
        return "."
    return "/".join(segments)


def truncate(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    """裁到上限，并明确标注被裁了多少。

    必须留痕：静默截断会让模型以为自己看全了，然后基于残缺内容下结论。
    """
    if len(text) <= limit:
        return text
    dropped = len(text) - limit
    return f"{text[:limit]}\n\n... [输出被截断，省略 {dropped} 字符。请缩小范围后重试]"


def run_shell_raw(
    sandbox: SandboxLike, script: str, timeout: int = 120
) -> tuple[str, str, int]:
    """在沙箱里跑一段 shell 脚本，返回 (stdout, stderr, exit_code)。

    命令的 cwd 固定在 WORKSPACE：显式 `cd` 而不是依赖运行时的默认值，
    这样即使镜像换了 base dir 的行为，文件工具和 bash 工具看到的仍是同一棵树。

    退出码不为 0 **不抛异常**——命令失败是常态（grep 没匹配、命令不存在），
    抛出会被 LangGraph 当成节点异常终止整张图。要不要把非零退出码当错误，
    由调用方按语义决定：grep 的 1 是"没匹配"，bash 的 1 是"命令失败"。
    """
    full = f"cd {shlex.quote(WORKSPACE)} && {script}"
    try:
        result = sandbox.commands.run(shell_command(full), timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - 沙箱侧异常类型太杂，统一转成工具层错误
        raise SandboxToolError(f"命令执行失败：{exc}") from exc

    return (
        (getattr(result, "stdout", "") or ""),
        (getattr(result, "stderr", "") or ""),
        int(getattr(result, "exit_code", -1)),
    )


def run_shell(sandbox: SandboxLike, script: str, timeout: int = 120) -> str:
    """跑脚本并把结果拼成给模型看的文本（吞掉退出码语义，一律附在末尾）。"""
    return _format_result(*run_shell_raw(sandbox, script, timeout=timeout))


def _format_result(stdout: str, stderr: str, exit_code: int) -> str:
    """把一次执行的结果拼成模型易读的一段文本。"""
    stdout = stdout.rstrip()
    stderr = stderr.rstrip()

    parts: list[str] = []
    if stdout:
        parts.append(stdout)
    if stderr:
        parts.append(f"[stderr]\n{stderr}")
    if not parts:
        parts.append("(无输出)")
    if exit_code != 0:
        parts.append(f"[exit code: {exit_code}]")

    return truncate("\n".join(parts))


def read_text_file(sandbox: SandboxLike, path: str, timeout: int = 60) -> str:
    """读一个沙箱内的文本文件，返回解码后的内容。

    read() 返回 bytes 且必须一次读完，所以先卡体积上限再解；二进制文件用
    NUL 字节探测——不拦的话 decode(replace) 会吐出一堆 U+FFFD，白烧 token。
    """
    rel = to_sandbox_path(path)
    try:
        raw = sandbox.files.read(rel, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        raise SandboxToolError(f"读取文件失败：{path}（{exc}）") from exc

    if len(raw) > MAX_READ_BYTES:
        raise SandboxToolError(
            f"文件过大（{len(raw)} 字节 > {MAX_READ_BYTES}）。"
            "请用 bash 工具配合 sed -n '1,200p'、head、tail 分段查看。"
        )
    if b"\x00" in raw[:8192]:
        raise SandboxToolError(f"{path} 像是二进制文件，无法按文本读取。")

    return raw.decode("utf-8", errors="replace")


def safe_call(fn):
    """执行工具主体，把可预期错误转成给模型看的文本。

    工具内部**不抛异常**是刻意的（见 code_agent.py 的注释）：LangGraph 会把节点里
    冒泡的异常当成致命错误终止整张图，而"文件不存在""old_string 没匹配上"是
    agent 正常工作流里的一环，应该让模型看到原因并自己纠正。

    传的是零参可调用对象（通常是 lambda），这样不必碰被包装函数的签名——
    早先试过 functools.partial 做工厂，Pydantic 的 schema 推断认不出来，
    报 "functools.partial(...) is not a module, class, method, or function"。
    """
    try:
        return fn()
    except SandboxToolError as exc:
        return f"错误：{exc}"
    except Exception as exc:  # noqa: BLE001 - 兜底，保证任何异常都变成可读文本
        return f"错误：{type(exc).__name__}: {exc}"
