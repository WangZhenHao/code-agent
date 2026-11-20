"""`file.read` / `file.stat`：前端文件树 + 编辑器的读文件接口。

⚠️ 这两个方法**故意不带 `web.` 前缀**：名字沿用 Coze IDE 的线上协议（抓包见
`docs/test.md`），前端（或现成的 Coze 客户端）直接按原名字调用。加新方法时
别把它们迁到 `web.` 下，那等于改前端代码。

形状对照 `docs/test.md`：

    file.read  {"path": ".gitignore"}
               → {content, encoding, size, mtime, ctime, totalLine}
    file.stat  {"path": "src"}
               → {path, size, mtime, ctime, isDirectory, isFile,
                  isSymbolicLink, permissions, children?}

约定：
- `path` 相对 `/workspace`；`""` 表示根目录（`file.stat` 回显原样的 `""`）。
- `mtime` / `ctime` 是**毫秒**时间戳（`docs/test.md` 抓的就是毫秒），
  `stat -c %Y/%Z` 给的是秒，这里乘 1000。
- `permissions` 是八进制权限位字符串（`"755"`），不带前导 0。
- `file.stat` 展开目录时，`children` 按项目 `.gitignore` 过滤（git 判定，见
  `_ignored_paths`）；`.git` 永远不列出。注意这是**展示过滤**：直接 stat / read
  被忽略的路径仍然可以成功——树里本来就不会给出它们，但别指望这层是访问控制。

为什么用 shell 而不是 SDK：`files` API 只有 read/write/list，没有 stat，拿不到
`ctime` / `permissions`；`find -printf` / `stat -c` 一次往返就全有了。镜像基于
Debian（GNU coreutils，见 deploy/api/sandbox-image），`-c` 可用。

错误一律走 `JsonRpcError`：文件不存在 / 是目录 / 路径越界 → -32001，参数错 → -32602，
沙箱起不来 → -32603。别让 `WsAuthError` / `SandboxToolError` 冒到 dispatcher，
那边会统一吞成 "服务器内部错误"。
"""

from __future__ import annotations

import asyncio
import shlex
from typing import TYPE_CHECKING, cast

from pydantic import BaseModel, ConfigDict, Field

from app.api.ws import schemas
from app.api.ws.core.registry import rpc_method

if TYPE_CHECKING:
    from app.agents.tools._common import SandboxLike
    from app.api.ws.core.connection import ConnectionContext


class FileReadParams(BaseModel):
    """路径与 `file.stat` 同义。将来若加 offset/limit 直接在这里补。"""

    model_config = ConfigDict(extra="forbid")
    path: str = ""


class FileStatParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = ""


class FileReadResult(BaseModel):
    content: str
    encoding: str
    size: int
    mtime: int
    ctime: int
    # Python 侧 snake_case，线上是 camelCase（对齐 Coze 抓包）。dispatcher 用
    # `model_dump(mode="json", by_alias=True)` 落地，前端看到的就是 totalLine。
    total_line: int = Field(serialization_alias="totalLine")


class FileChild(BaseModel):
    """目录直接子项。不带 path——前端自己拼（`docs/test.md` 的抓包也没有）。"""

    name: str
    isDirectory: bool
    size: int
    mtime: int


class FileStatResult(BaseModel):
    path: str
    size: int
    mtime: int
    ctime: int
    isDirectory: bool
    isFile: bool
    isSymbolicLink: bool
    permissions: str
    # 只有目录才有 children；文件为 None（JSON 里是 null）。
    children: list[FileChild] | None = None


# ---------------------------------------------------------------------------
# 沙箱侧
# ---------------------------------------------------------------------------


class _Stat(BaseModel):
    """handler 内部用的 stat 解析结果，不是线上形状。"""

    size: int
    mtime: int
    ctime: int
    permissions: str
    isDirectory: bool
    isFile: bool
    isSymbolicLink: bool


def _deny(message: str) -> schemas.JsonRpcError:
    """文件不存在 / 不是文件 / 路径越界——对前端都是「拿不到这个路径」。"""
    return schemas.JsonRpcError(schemas.RESOURCE_NOT_FOUND, message)


async def _sandbox(ctx: ConnectionContext) -> SandboxLike:
    """归属校验 + 拿到可用的沙箱句柄。两个 handler 的前置都走这里。"""
    # 延迟 import：sandbox / k8s SDK / DB 一大串，别在注册表 import 期拉进来。
    from app.api.sandbox.preview import resolve_devbox
    from app.api.sandbox.service import start_sandbox
    from app.api.ws.core.auth import WsAuthError

    try:
        await resolve_devbox(ctx.session_id, ctx.user.id)
    except WsAuthError as exc:
        # WsAuthError 是握手期的关闭码异常，handler 里没有 WS 可关，转成错误码。
        raise _deny("devbox 不存在") from exc

    try:
        # SDK 的 Sandbox 结构上就是 SandboxLike（tools 层也是这么用的），
        # 类型标注对不上读写属性，收窄一次即可。
        return cast("SandboxLike", await start_sandbox(ctx.session_id))
    except Exception as exc:  # noqa: BLE001 - HTTPException / SDK 异常都到这里
        # 异常原文只进日志：里面可能带连接串、内部地址。
        import logging

        logging.getLogger(__name__).exception(
            "file.* 取沙箱失败 session_id=%s", ctx.session_id
        )
        raise schemas.JsonRpcError(
            schemas.INTERNAL_ERROR, "沙箱不可用，请稍后重试"
        ) from exc


async def _run_script(sandbox: SandboxLike, script: str) -> tuple[str, str, int]:
    """把脚本丢进线程跑。SDK 是同步 requests，直接在事件循环里 await 会卡住整个进程。"""
    from app.agents.tools._common import run_shell_raw

    return await asyncio.to_thread(run_shell_raw, sandbox, script)


def _rel_path(raw: str) -> str:
    """模型/前端给的路径 → 沙箱相对路径；越界、控制字符都转成 -32001。"""
    from app.agents.tools._common import SandboxToolError, to_sandbox_path

    # `""` 是「工作根」的写法（抓包里根目录就是空串），to_sandbox_path 会判它为空路径。
    if not raw.strip():
        return "."

    try:
        return to_sandbox_path(raw)
    except SandboxToolError as exc:
        raise _deny(str(exc)) from exc


def _parse_stat(stdout: str) -> _Stat:
    """解析 `stat` 打出的 `K=V` 行。缺字段说明沙箱里 stat 的行为变了，按内部错误处理。"""
    fields: dict[str, str] = {}
    for line in stdout.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            fields[key] = value

    kind = fields.get("kind", "")
    try:
        return _Stat(
            size=int(fields["size"]),
            # GNU stat 的 %Y/%Z 是秒（整型），线上要毫秒。
            mtime=int(fields["mtime"]) * 1000,
            ctime=int(fields["ctime"]) * 1000,
            permissions=fields["perm"],
            # 符号链接已用 -L 跟到目标，所以 kind 反映的是目标的类型；
            # 断链时 stat -L 直接失败，这里到不了。
            isDirectory=kind == "directory",
            isFile=kind == "regular file",
            isSymbolicLink=fields.get("link") == "1",
        )
    except (KeyError, ValueError) as exc:
        raise schemas.JsonRpcError(schemas.INTERNAL_ERROR, "无法读取文件状态") from exc


def _stat_script(rel: str) -> str:
    """目标本身的元数据，一次往返。

    `-L` 跟随符号链接：前端点符号链接要能打开目标，所以类型与权限都按目标算；
    断链时 `stat -L` 直接失败，前端拿到 -32001。
    类型用 `%F` 的 human 可读串（`directory` / `regular file`），比 `%f` 的 hex 好读。
    子项不走这里——用 SDK 的 `files.list()`，省得自己拼 find/stat。
    不放在 set -e 下：只有目标那次 stat 的退出码有意义（3 = 不存在）。
    """
    quoted = shlex.quote(rel)
    return f"""
p={quoted}
stat -L -c 'size=%s
mtime=%Y
ctime=%Z
perm=%a
kind=%F' -- "$p" || exit 3
if [ -L "$p" ]; then echo 'link=1'; else echo 'link=0'; fi
"""


# 文件树里永远不列出的名字：`.git` 不是项目内容，且不受 .gitignore 管辖
# （git 自己不会「忽略」它），不显式挡的话根目录下会冒出来。
_PRUNED_NAMES = frozenset({".git"})


def _child_path(rel: str, name: str) -> str:
    """子项仓库根相对路径。`rel` 是 `.` 时直接给名字，别让 gitignore 匹配到 `./x`。"""
    return name if rel in ("", ".") else f"{rel}/{name}"


def _ignore_script(paths: list[str]) -> str:
    """把子项路径喂给 `git check-ignore`，stdout 是被忽略的那些（NUL 分隔）。

    用 git 而不是自己解析 .gitignore：嵌套的 .gitignore、否定规则、`/` 锚定这些
    细节 git 自己最清楚。`--no-index` 让已被跟踪的文件也参与判断——文件树要的是
    "按规则该不该隐藏"，不是"git 会不会提交它"。

    沙箱的工作区常常不是 git 仓库（模板直接铺开，没 init）。check-ignore 只要求
    有 work tree 和 GIT_DIR，于是借 /tmp 下一个固定目录当仓库：不往 /workspace
    写任何一个字节，二次展开也复用同一个。仓库里没有 index，`--no-index` 本来
    也不需要它。
    """
    feed = " ".join(shlex.quote(p) for p in paths)
    return f"""
git_args=()
if ! git rev-parse --git-dir >/dev/null 2>&1; then
  scratch="${{TMPDIR:-/tmp}}/code-agent-file-tree.git"
  if [ ! -f "$scratch/config" ]; then
    git --git-dir="$scratch" --work-tree=. init -q >/dev/null 2>&1 || exit 4
  fi
  git_args=(--git-dir="$scratch" --work-tree=.)
fi
printf '%s\\0' {feed} | git "${{git_args[@]}}" check-ignore --no-index -z --stdin
"""


def _ignored_paths(sandbox: SandboxLike, paths: list[str]) -> set[str]:
    """`paths` 里被 .gitignore 命中的子集。调用方已在线程里，直接同步跑。

    失败（git 缺失、仓库建不起来）时退化成"什么都没忽略"并留日志：文件树宁可
    多显示几个目录，也不该因为过滤坏了打不开。
    """
    if not paths:
        return set()

    from app.agents.tools._common import run_shell_raw

    # 0 = 有被忽略的，1 = 一个都没有，两者都是正常结果。
    stdout, stderr, code = run_shell_raw(sandbox, _ignore_script(paths))
    if code not in (0, 1):
        import logging

        logging.getLogger(__name__).warning(
            "git check-ignore 失败（exit=%s）：%s", code, stderr.strip()
        )
        return set()
    return {p for p in stdout.split("\0") if p}


def _list_children(sandbox: SandboxLike, rel: str) -> list[FileChild]:
    """目录的直接子项。SDK 的 `list()` 只给一层，正好是树的一次展开。

    子项按项目 .gitignore 过滤（`_ignored_paths` 一次往返），`.git` 一律不返回——
    它不是项目内容，也不受 .gitignore 管辖。

    同步调用——调用方用 `asyncio.to_thread` 包起来。
    """
    entries = [e for e in sandbox.files.list(rel) if e.name not in _PRUNED_NAMES]
    paths = [_child_path(rel, e.name) for e in entries]
    ignored = _ignored_paths(sandbox, paths)
    return [
        FileChild(
            name=entry.name,
            isDirectory=entry.type == "directory",
            size=entry.size,
            # SDK 已是 timezone-aware datetime，毫秒对齐线上契约。
            mtime=int(entry.modified.timestamp() * 1000),
        )
        for entry, path in zip(entries, paths, strict=True)
        if path not in ignored
    ]


async def _stat(sandbox: SandboxLike, rel: str) -> tuple[_Stat, list[FileChild] | None]:
    stdout, stderr, code = await _run_script(sandbox, _stat_script(rel))
    if code != 0:
        raise _deny(
            f"文件不存在：{rel}" if code == 3 else f"读取状态失败：{stderr.strip()}"
        )
    stat = _parse_stat(stdout)
    if not stat.isDirectory:
        return stat, None
    try:
        children = await asyncio.to_thread(_list_children, sandbox, rel)
    except Exception as exc:  # noqa: BLE001 - SDK 异常类型太杂
        raise schemas.JsonRpcError(schemas.INTERNAL_ERROR, "读取目录失败") from exc
    return stat, children


# ---------------------------------------------------------------------------
# handlers
# ---------------------------------------------------------------------------


@rpc_method("file.stat", params_model=FileStatParams, result_model=FileStatResult)
async def file_stat(ctx: ConnectionContext, params: FileStatParams) -> FileStatResult:
    sandbox = await _sandbox(ctx)
    rel = _rel_path(params.path)
    stat, children = await _stat(sandbox, rel)
    return FileStatResult(
        # 回显请求原文（抓包中 `""` → `""`），前端拿它做树的 key。
        path=params.path,
        size=stat.size,
        mtime=stat.mtime,
        ctime=stat.ctime,
        isDirectory=stat.isDirectory,
        isFile=stat.isFile,
        isSymbolicLink=stat.isSymbolicLink,
        permissions=stat.permissions,
        children=children,
    )


@rpc_method("file.read", params_model=FileReadParams, result_model=FileReadResult)
async def file_read(ctx: ConnectionContext, params: FileReadParams) -> FileReadResult:
    sandbox = await _sandbox(ctx)
    rel = _rel_path(params.path)
    stat, _ = await _stat(sandbox, rel)
    if stat.isDirectory:
        raise _deny(f"不是文件：{params.path}")

    # 不走 read_text_file：那是给模型用的（5 MiB 上限、二进制探测、replace 解码），
    # IDE 要的是原文 + 明确的失败信号。
    try:
        raw = await asyncio.to_thread(sandbox.files.read, rel)
    except Exception as exc:  # noqa: BLE001
        raise _deny(f"读取失败：{params.path}") from exc

    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _deny(f"不是 UTF-8 文本文件：{params.path}") from exc

    # 编辑器要的是行数：末尾没有换行时 count 会少一行，补上。
    total_line = content.count("\n")
    if content and not content.endswith("\n"):
        total_line += 1

    return FileReadResult(
        content=content,
        encoding="utf-8",
        size=stat.size,
        mtime=stat.mtime,
        ctime=stat.ctime,
        total_line=total_line,
    )
