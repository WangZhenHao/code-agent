"""tools/ 的离线测试：用假的沙箱对象，不需要集群、不需要 port-forward。

假对象（FakeSandbox）刻意复刻官方 python-runtime 的两个行为，因为工具的正确性
几乎全押在它们上：
  1. /execute 用 shlex.split 拆参后直接 exec —— 不经 shell，
     所以工具必须自己套 `bash -c`，否则 `&&`、管道、通配符全废；
  2. 文件 API 把路径 normpath 后 lstrip('/') 再拼到 base dir，
     所以 `files.read("/workspace/a.py")` 会落到 `<base>/workspace/a.py` —— 多一层。
     工具里的 to_sandbox_path 就是为了消掉这个前缀。

跑法：uv run pytest tests/ -q
"""

from __future__ import annotations

import os
import posixpath
import shlex
import shutil
import subprocess
import tempfile
import unittest
from dataclasses import dataclass

from app.agents.tools import build_tools
from app.agents.tools._common import shell_command, to_sandbox_path
from app.agents.tools.glob import _find_name_expr, _find_path_expr


@dataclass
class ExecResult:
    stdout: str = ""
    stderr: str = ""
    exit_code: int = -1


class FakeCommands:
    def __init__(self, base: str):
        self.base = base

    def run(self, command: str, timeout: int = 60) -> ExecResult:
        # 真实运行时就是 shlex.split 之后直接 exec，这里照做——正是这个行为
        # 让"不套 bash -c"的实现无法通过测试。
        script = command.replace("/workspace", self.base)
        argv = shlex.split(script)
        try:
            done = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return ExecResult("", "timeout", 124)
        except FileNotFoundError as exc:
            return ExecResult("", str(exc), 127)
        return ExecResult(done.stdout, done.stderr, done.returncode)


class FakeFiles:
    def __init__(self, base: str):
        self.base = base

    def _resolve(self, path: str) -> str:
        # 复刻 SDK 的 _safe_upload_path：normpath + lstrip("/")
        return os.path.join(self.base, posixpath.normpath(path).lstrip("/"))

    def write(self, path: str, content: bytes | str, timeout: int = 60):
        target = self._resolve(path)
        parent = os.path.dirname(target)
        if parent:
            os.makedirs(parent, exist_ok=True)
        data = content.encode("utf-8") if isinstance(content, str) else content
        with open(target, "wb") as handle:
            handle.write(data)

    def read(self, path: str, timeout: int = 60) -> bytes:
        with open(self._resolve(path), "rb") as handle:
            return handle.read()


class FakeSandbox:
    def __init__(self, base: str):
        self.commands = FakeCommands(base)
        self.files = FakeFiles(base)


class ToolTestCase(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp(prefix="sandbox-test-")
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)

        os.makedirs(f"{self.base}/app")
        self._write("app/main.py", "def hello():\n    return 'hi'\n\n\ndef other():\n    return 1\n")
        self._write("README.md", "# demo\nhello world\n")
        self._write("app/page.tsx", "export default () => null\n")
        os.makedirs(f"{self.base}/node_modules/junk")
        self._write("node_modules/junk/big.js", "hello\n")

        self.tools = {t.name: t for t in build_tools(FakeSandbox(self.base))}

    def _write(self, rel: str, content: str) -> None:
        path = os.path.join(self.base, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)

    # --- 路径归一化 -------------------------------------------------------

    def test_to_sandbox_path_strips_workspace_prefix(self):
        # 这是最关键的断言：不消前缀，文件就会落在 /workspace/workspace/ 下。
        for given in ("/workspace/src/a.py", "workspace/src/a.py", "/src/a.py", "src/a.py"):
            self.assertEqual(to_sandbox_path(given), "src/a.py", given)
        self.assertEqual(to_sandbox_path("/workspace"), ".")
        self.assertEqual(to_sandbox_path("./a.py"), "a.py")

    def test_to_sandbox_path_rejects_escape(self):
        with self.assertRaises(Exception):
            to_sandbox_path("../../etc/passwd")

    def test_shell_command_survives_single_quotes(self):
        # /execute 经 shlex.split，所以转义后必须还原出原始脚本。
        for script in ("echo hello", "a && b | c", "echo it's fine", "ls *.py"):
            argv = shlex.split(shell_command(script))
            self.assertEqual(argv, ["bash", "-c", script])

    # --- bash -------------------------------------------------------------

    def test_bash_supports_shell_syntax(self):
        out = self.tools["bash"].invoke({"command": "echo a b | tr ' ' '\\n' && ls *.md"})
        self.assertIn("a", out)
        self.assertIn("README.md", out)

    def test_bash_reports_nonzero_exit_without_raising(self):
        out = self.tools["bash"].invoke({"command": "grep -q zzz README.md"})
        self.assertIn("exit code: 1", out)

    # --- read / write / edit ---------------------------------------------

    def test_read_file_numbers_lines(self):
        out = self.tools["read_file"].invoke({"file_path": "/workspace/app/main.py"})
        self.assertTrue(out.startswith("1\tdef hello():"))

    def test_read_file_paginates(self):
        out = self.tools["read_file"].invoke(
            {"file_path": "app/main.py", "offset": 5, "limit": 1}
        )
        self.assertIn("def other():", out)
        self.assertIn("offset=6", out)

    def test_read_file_rejects_binary(self):
        with open(f"{self.base}/bin.dat", "wb") as handle:
            handle.write(b"\x00\x01\x02")
        out = self.tools["read_file"].invoke({"file_path": "bin.dat"})
        self.assertIn("二进制", out)

    def test_write_file_creates_parent_dirs(self):
        out = self.tools["write_file"].invoke(
            {"file_path": "src/deep/new.txt", "content": "hello\nworld\n"}
        )
        self.assertIn("已写入", out)
        self.assertTrue(os.path.exists(f"{self.base}/src/deep/new.txt"))

    def test_write_file_does_not_double_workspace(self):
        self.tools["write_file"].invoke({"file_path": "/workspace/out.txt", "content": "x"})
        self.assertFalse(os.path.exists(f"{self.base}/workspace"))

    def test_edit_file_replaces_unique_match(self):
        out = self.tools["edit_file"].invoke(
            {
                "file_path": "app/main.py",
                "old_string": "return 'hi'",
                "new_string": "return 'bye'",
            }
        )
        self.assertIn("替换 1 处", out)
        with open(f"{self.base}/app/main.py") as handle:
            self.assertIn("return 'bye'", handle.read())

    def test_edit_file_rejects_ambiguous_match(self):
        out = self.tools["edit_file"].invoke(
            {"file_path": "app/main.py", "old_string": "return", "new_string": "yield"}
        )
        self.assertIn("出现了 2 次", out)
        # 没改动原文件
        with open(f"{self.base}/app/main.py") as handle:
            self.assertIn("return 'hi'", handle.read())

    def test_edit_file_replace_all(self):
        out = self.tools["edit_file"].invoke(
            {
                "file_path": "app/main.py",
                "old_string": "return",
                "new_string": "yield",
                "replace_all": True,
            }
        )
        self.assertIn("替换 2 处", out)

    def test_edit_file_missing_old_string(self):
        out = self.tools["edit_file"].invoke(
            {"file_path": "app/main.py", "old_string": "nope", "new_string": "x"}
        )
        self.assertIn("找不到", out)

    # --- glob -------------------------------------------------------------

    def test_glob_finds_by_extension(self):
        out = self.tools["glob"].invoke({"pattern": "**/*.py"})
        self.assertIn("app/main.py", out)

    def test_glob_excludes_node_modules(self):
        # /workspace 不是 git 仓库，rg 不会自动应用 .gitignore——必须靠显式排除。
        # 断言落在"结果行"上，而不是整段文本：提示语里本来就会列出被排除的目录名，
        # 拿整段做 assertNotIn 会误判。
        out = self.tools["glob"].invoke({"pattern": "**/*.js"})
        self.assertIn("没有匹配", out)
        self.assertEqual(
            [ln for ln in out.splitlines() if ln.endswith(".js")],
            [],
        )

    def test_glob_expands_braces_in_find_fallback(self):
        self.assertEqual(_find_name_expr("*.{ts,tsx}"), "\\( -name '*.ts' -o -name '*.tsx' \\)")
        out = self.tools["glob"].invoke({"pattern": "**/*.{ts,tsx}"})
        self.assertIn("app/page.tsx", out)

    def test_glob_empty_result_is_not_the_placeholder(self):
        # run_shell 会把空输出格式化成 "(无输出)"，那个字符串绝不能混进结果。
        out = self.tools["glob"].invoke({"pattern": "**/*.rs"})
        self.assertNotIn("无输出", out)
        self.assertIn("没有匹配", out)

    def test_find_path_expr_uses_literal_prefix(self):
        self.assertEqual(_find_path_expr("app/**/*.py"), "-path '*/app/*'")
        self.assertEqual(_find_path_expr("**/*.py"), "")

    # --- grep -------------------------------------------------------------

    def test_grep_content_mode(self):
        out = self.tools["grep"].invoke({"pattern": "hello"})
        self.assertIn("README.md", out)

    def test_grep_no_match_is_not_an_error(self):
        out = self.tools["grep"].invoke({"pattern": "zzzzz"})
        self.assertIn("没有匹配", out)
        self.assertNotIn("错误", out)

    def test_grep_bad_regex_reports_error(self):
        out = self.tools["grep"].invoke({"pattern": "[unclosed"})
        self.assertIn("错误", out)

    def test_grep_rejects_unknown_output_mode(self):
        out = self.tools["grep"].invoke({"pattern": "x", "output_mode": "bogus"})
        self.assertIn("错误", out)

    def test_grep_excludes_node_modules(self):
        out = self.tools["grep"].invoke({"pattern": "hello", "glob": "*.js"})
        self.assertNotIn("node_modules", out)


if __name__ == "__main__":
    unittest.main()
