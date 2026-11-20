"""`file.read` / `file.stat` 的 handler 单测：不连 k8s、不碰 DB。

沙箱用假对象顶上（`commands.run` 回预置的 stat 输出、`files.read/list` 回内存数据），
`_sandbox()` 用 patch 换掉，只测 handler 自己的逻辑：路径归一、秒 → 毫秒、
目录/文件判定、错误码。

跑法：uv run python -m unittest tests.api.ws.test_file_methods
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest import mock

import app.api.ws.methods  # noqa: F401  触发方法注册
from app.api.ws import schemas
from app.api.ws.core.registry import get_method
from app.api.ws.methods import file as file_methods
from app.api.ws.methods.file import (
    FileReadParams,
    FileStatParams,
    file_read,
    file_stat,
)

CTX = SimpleNamespace(session_id="s-1", user=SimpleNamespace(id=1))


class ExecResult:
    def __init__(self, stdout: str, stderr: str = "", exit_code: int = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code


class FakeCommands:
    """按预置脚本返回输出；不真的跑 shell（宿主机是 BSD stat，没 -c）。

    `file.stat` 展开目录时会多发一条 `git check-ignore`，按脚本内容分流：
    `ignore` 缺省表示「什么都没被忽略」（git 的退出码 1）。
    """

    def __init__(self, result: ExecResult, ignore: ExecResult | None = None) -> None:
        self.result = result
        self.ignore = ignore or ExecResult("", "", 1)
        self.scripts: list[str] = []

    def run(self, command: str, timeout: int = 60) -> ExecResult:
        self.scripts.append(command)
        if "check-ignore" in command:
            return self.ignore
        return self.result


class FakeFiles:
    def __init__(self, content: bytes = b"", entries: list | None = None) -> None:
        self.content = content
        self.entries = entries or []
        self.read_paths: list[str] = []
        self.list_paths: list[str] = []

    def read(self, path: str, timeout: int = 60) -> bytes:
        self.read_paths.append(path)
        return self.content

    def list(self, path: str, timeout: int = 60) -> list:
        self.list_paths.append(path)
        return self.entries


def stat_output(
    *,
    size=1664,
    sec=1783492844,
    csec=1794882020,
    perm="644",
    kind="regular file",
    link=0,
) -> str:
    return f"size={size}\nmtime={sec}\nctime={csec}\nperm={perm}\nkind={kind}\nlink={link}\n"


def fake_sandbox(commands: FakeCommands, files: FakeFiles):
    return SimpleNamespace(commands=commands, files=files)


class _Base(unittest.IsolatedAsyncioTestCase):
    def use(self, sandbox) -> None:
        patcher = mock.patch.object(
            file_methods, "_sandbox", mock.AsyncMock(return_value=sandbox)
        )
        patcher.start()
        self.addCleanup(patcher.stop)


class TestRegistration(unittest.TestCase):
    def test_methods_registered(self):
        # methods/__init__.py 漏 import 的表现就是这里为 None，线上回 -32601。
        self.assertIsNotNone(get_method("file.read"))
        self.assertIsNotNone(get_method("file.stat"))


class TestFileStat(_Base):
    async def test_file(self):
        self.use(fake_sandbox(FakeCommands(ExecResult(stat_output())), FakeFiles()))

        result = await file_stat(CTX, FileStatParams(path=".gitignore"))

        self.assertEqual(result.path, ".gitignore")
        self.assertEqual(result.size, 1664)
        # stat 给秒，线上要毫秒。
        self.assertEqual(result.mtime, 1783492844000)
        self.assertEqual(result.ctime, 1794882020000)
        self.assertEqual(result.permissions, "644")
        self.assertTrue(result.isFile)
        self.assertFalse(result.isDirectory)
        self.assertFalse(result.isSymbolicLink)
        self.assertIsNone(result.children)

    async def test_serializes_camel_case_path_echo(self):
        # dispatcher 直接 model_dump，字段名就是前端看到的；path 要原样回显。
        self.use(fake_sandbox(FakeCommands(ExecResult(stat_output())), FakeFiles()))
        result = await file_stat(CTX, FileStatParams(path=""))
        self.assertEqual(result.model_dump()["path"], "")

    async def test_directory_children(self):
        entry_file = SimpleNamespace(
            name="server.ts",
            size=978,
            type="file",
            modified=datetime(2026, 8, 8, 12, 0, tzinfo=UTC),
        )
        entry_dir = SimpleNamespace(
            name="lib",
            size=4096,
            type="directory",
            modified=datetime(2026, 8, 8, 13, 0, tzinfo=UTC),
        )
        files = FakeFiles(entries=[entry_dir, entry_file])
        self.use(
            fake_sandbox(
                FakeCommands(ExecResult(stat_output(size=4096, kind="directory"))),
                files,
            )
        )

        result = await file_stat(CTX, FileStatParams(path="src"))

        self.assertTrue(result.isDirectory)
        self.assertEqual(files.list_paths, ["src"])
        self.assertEqual([c.name for c in result.children], ["lib", "server.ts"])
        self.assertTrue(result.children[0].isDirectory)
        self.assertFalse(result.children[1].isDirectory)
        self.assertEqual(result.children[1].mtime, 1786190400000)  # 2026-08-08T12:00Z

    async def test_ignored_children_hidden(self):
        entries = [
            SimpleNamespace(
                name="node_modules",
                size=4096,
                type="directory",
                modified=datetime(2026, 8, 8, 12, 0, tzinfo=UTC),
            ),
            SimpleNamespace(
                name="a.log",
                size=10,
                type="file",
                modified=datetime(2026, 8, 8, 12, 0, tzinfo=UTC),
            ),
            SimpleNamespace(
                name="src",
                size=4096,
                type="directory",
                modified=datetime(2026, 8, 8, 12, 0, tzinfo=UTC),
            ),
        ]
        commands = FakeCommands(
            ExecResult(stat_output(size=4096, kind="directory")),
            # `git check-ignore -z` 的输出：NUL 分隔的被忽略路径，原样回显入参。
            ignore=ExecResult("node_modules\0a.log\0", "", 0),
        )
        self.use(fake_sandbox(commands, FakeFiles(entries=entries)))

        result = await file_stat(CTX, FileStatParams(path=""))

        self.assertEqual([c.name for c in result.children], ["src"])
        ignore_script = next(s for s in commands.scripts if "check-ignore" in s)
        # 根目录的子项直接给名字，不带 "./" 前缀——check-ignore 按仓库根相对路径匹配。
        self.assertIn(" node_modules a.log src | git", ignore_script)

    async def test_gitignore_subdir_paths(self):
        entry = SimpleNamespace(
            name="dist",
            size=4096,
            type="directory",
            modified=datetime(2026, 8, 8, 12, 0, tzinfo=UTC),
        )
        commands = FakeCommands(
            ExecResult(stat_output(size=4096, kind="directory")),
            ignore=ExecResult("src/dist\0", "", 0),
        )
        self.use(fake_sandbox(commands, FakeFiles(entries=[entry])))

        result = await file_stat(CTX, FileStatParams(path="src"))

        self.assertEqual(result.children, [])
        ignore_script = next(s for s in commands.scripts if "check-ignore" in s)
        self.assertIn(" src/dist | git", ignore_script)

    async def test_dot_git_hidden(self):
        entries = [
            SimpleNamespace(
                name=".git",
                size=4096,
                type="directory",
                modified=datetime(2026, 8, 8, 12, 0, tzinfo=UTC),
            ),
            SimpleNamespace(
                name="README.md",
                size=20,
                type="file",
                modified=datetime(2026, 8, 8, 12, 0, tzinfo=UTC),
            ),
        ]
        commands = FakeCommands(ExecResult(stat_output(size=4096, kind="directory")))
        self.use(fake_sandbox(commands, FakeFiles(entries=entries)))

        result = await file_stat(CTX, FileStatParams(path=""))

        self.assertEqual([c.name for c in result.children], ["README.md"])
        # 只剩一个子项，还是发一次 check-ignore（README 可能被 *.md 之类忽略）。
        ignore_script = next(s for s in commands.scripts if "check-ignore" in s)
        self.assertIn(" README.md | git", ignore_script)
        self.assertNotIn(" .git |", ignore_script)

    async def test_gitignore_failure_degrades_to_unfiltered(self):
        # git 缺失 / 仓库建不起来时不拦树：宁可多显示，也不让文件树打不开。
        entries = [
            SimpleNamespace(
                name="node_modules",
                size=4096,
                type="directory",
                modified=datetime(2026, 8, 8, 12, 0, tzinfo=UTC),
            ),
        ]
        commands = FakeCommands(
            ExecResult(stat_output(size=4096, kind="directory")),
            ignore=ExecResult("", "fatal: not a git repository", 128),
        )
        self.use(fake_sandbox(commands, FakeFiles(entries=entries)))

        result = await file_stat(CTX, FileStatParams(path=""))

        self.assertEqual([c.name for c in result.children], ["node_modules"])

    async def test_file_does_not_check_ignore(self):
        commands = FakeCommands(ExecResult(stat_output()))
        self.use(fake_sandbox(commands, FakeFiles()))

        await file_stat(CTX, FileStatParams(path="a.py"))

        self.assertEqual(len(commands.scripts), 1)  # 只有 stat，没有 check-ignore

    async def test_missing_returns_32001(self):
        self.use(
            fake_sandbox(
                FakeCommands(ExecResult("", "No such file", exit_code=3)), FakeFiles()
            )
        )
        with self.assertRaises(schemas.JsonRpcError) as ctx:
            await file_stat(CTX, FileStatParams(path="nope"))
        self.assertEqual(ctx.exception.code, schemas.RESOURCE_NOT_FOUND)

    async def test_path_escape_rejected(self):
        self.use(fake_sandbox(FakeCommands(ExecResult(stat_output())), FakeFiles()))
        with self.assertRaises(schemas.JsonRpcError) as ctx:
            await file_stat(CTX, FileStatParams(path="../etc/passwd"))
        self.assertEqual(ctx.exception.code, schemas.RESOURCE_NOT_FOUND)


class TestPathNormalization(_Base):
    async def test_workspace_prefix_stripped(self):
        commands = FakeCommands(ExecResult(stat_output()))
        self.use(fake_sandbox(commands, FakeFiles()))

        await file_stat(CTX, FileStatParams(path="/workspace/src/a.py"))

        # 脚本里的 p= 必须是文件 API 认的相对路径，不能多一层 workspace/。
        self.assertIn("p=src/a.py", commands.scripts[0])

    async def test_root_becomes_dot(self):
        commands = FakeCommands(ExecResult(stat_output(kind="directory", size=4096)))
        self.use(fake_sandbox(commands, FakeFiles()))

        await file_stat(CTX, FileStatParams(path=""))
        self.assertIn("p=.", commands.scripts[0])


class TestFileRead(_Base):
    async def test_content(self):
        body = b"a\nb\nc\n"
        files = FakeFiles(content=body)
        self.use(
            fake_sandbox(FakeCommands(ExecResult(stat_output(size=len(body)))), files)
        )

        result = await file_read(CTX, FileReadParams(path="README.md"))

        self.assertEqual(result.content, "a\nb\nc\n")
        self.assertEqual(result.encoding, "utf-8")
        self.assertEqual(result.size, len(body))
        self.assertEqual(result.total_line, 3)
        self.assertEqual(files.read_paths, ["README.md"])
        # 线上字段名是 camelCase（dispatcher 用 by_alias=True 落地）。
        self.assertEqual(result.model_dump(mode="json", by_alias=True)["totalLine"], 3)

    async def test_total_line_without_trailing_newline(self):
        self.use(
            fake_sandbox(
                FakeCommands(ExecResult(stat_output())), FakeFiles(content=b"a\nb")
            )
        )
        result = await file_read(CTX, FileReadParams(path="x"))
        self.assertEqual(result.total_line, 2)

    async def test_empty_file(self):
        self.use(
            fake_sandbox(
                FakeCommands(ExecResult(stat_output())), FakeFiles(content=b"")
            )
        )
        result = await file_read(CTX, FileReadParams(path="x"))
        self.assertEqual(result.content, "")
        self.assertEqual(result.total_line, 0)

    async def test_directory_rejected(self):
        files = FakeFiles()
        self.use(
            fake_sandbox(
                FakeCommands(ExecResult(stat_output(kind="directory", size=4096))),
                files,
            )
        )
        with self.assertRaises(schemas.JsonRpcError) as ctx:
            await file_read(CTX, FileReadParams(path="src"))
        self.assertEqual(ctx.exception.code, schemas.RESOURCE_NOT_FOUND)
        self.assertEqual(files.read_paths, [])  # 没白读

    async def test_binary_rejected(self):
        self.use(
            fake_sandbox(
                FakeCommands(ExecResult(stat_output())),
                FakeFiles(content=b"\xff\xfe\x00"),
            )
        )
        with self.assertRaises(schemas.JsonRpcError) as ctx:
            await file_read(CTX, FileReadParams(path="a.bin"))
        self.assertEqual(ctx.exception.code, schemas.RESOURCE_NOT_FOUND)


if __name__ == "__main__":
    unittest.main()
