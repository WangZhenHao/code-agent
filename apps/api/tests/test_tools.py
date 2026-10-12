"""tools/ 的离线测试：用假的沙箱对象，不需要集群、不需要 port-forward。

假对象（FakeSandbox）刻意复刻官方 python-runtime 的两个行为，因为工具的正确性
几乎全押在它们上：
  1. /execute 用 shlex.split 拆参后直接 exec —— 不经 shell，
     所以工具必须自己套 `bash -c`，否则 `&&`、管道、通配符全废；
  2. 文件 API 把路径 normpath 后 lstrip('/') 再拼到 base dir，
     所以 `files.read("/workspace/a.py")` 会落到 `<base>/workspace/a.py` —— 多一层。
     工具里的 to_sandbox_path 就是为了消掉这个前缀。

跑法：uv run pytest tests/ -q

技能包（read_skill / skill_loader）的测试走 SkillToolTestCase：它把 SKILLS_DIR
指到临时目录，所以既不依赖 public/skills/ 的现有内容，也不需要沙箱。
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
from pathlib import Path
from unittest import mock

from app.agents.helper import skill_loader
from app.agents.helper.agent_prompt import generate_system_prompt
from app.agents.tools import READ_ONLY_TOOL_NAMES, build_tools, create_tools
from app.agents.tools._common import shell_command, to_sandbox_path
from app.agents.tools.glob import _find_name_expr, _find_path_expr
from app.agents.tools.skill import build_read_skill_tool
from app.db.models.session import MessageMode


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

    # --- 按模式取工具 -----------------------------------------------------

    def test_agent_mode_gets_every_tool(self):
        names = [t.name for t in create_tools(FakeSandbox(self.base), MessageMode.agent)]
        self.assertEqual(names, [t.name for t in build_tools(FakeSandbox(self.base))])

    def test_plan_mode_gets_only_read_only_tools(self):
        names = {t.name for t in create_tools(FakeSandbox(self.base), MessageMode.plan)}
        self.assertEqual(names, set(READ_ONLY_TOOL_NAMES))
        # 逐个点名断言，而不是只比集合：READ_ONLY_TOOL_NAMES 被误改时，
        # 上面那句会跟着一起变，等于没测。
        self.assertEqual(names, {"bash", "read_file", "glob", "grep", "read_skill"})

    def test_tool_order_is_unchanged_by_filtering(self):
        # plan 是 agent 的子序列，模型的工具偏好顺序才不会在切模式时翻个儿。
        full = [t.name for t in build_tools(FakeSandbox(self.base))]
        plan = [t.name for t in create_tools(FakeSandbox(self.base), MessageMode.plan)]
        self.assertEqual(plan, [n for n in full if n in set(plan)])


class SkillToolTestCase(unittest.TestCase):
    """read_skill / skill_loader 的离线测试。

    技能包不在沙箱里，所以这里不用 FakeSandbox，而是把 SKILLS_DIR 指到一个
    临时目录——测试因此可以随手造技能包，不依赖 public/skills/ 的现有内容
    （往那里加技能包不该让测试变红）。
    """

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="skills-test-")
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

        self._write(
            "frontend-design/SKILL.md",
            "---\n"
            "name: frontend-design\n"
            "description: Guidance for distinctive visual design.\n"
            "---\n"
            "\n"
            "# Frontend Design\n"
            "line three\n"
            "line four\n",
        )
        self._write("frontend-design/references/QUERIES.md", "query: hello\n")
        # 没有 frontmatter、也没有描述的技能包：描述要回落成占位符。
        self._write("bare-skill/SKILL.md", "# Bare\n")

        self._patch = mock.patch.object(skill_loader, "SKILLS_DIR", Path(self.root))
        self._patch.start()
        self.addCleanup(self._patch.stop)

        self.tool = build_read_skill_tool()

    def _write(self, rel: str, content: str) -> None:
        path = Path(self.root) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    # --- 列表解析 ---------------------------------------------------------

    def test_list_skills_parses_frontmatter(self):
        skills = {s.name: s.description for s in skill_loader.list_skills()}
        self.assertEqual(skills["frontend-design"], "Guidance for distinctive visual design.")
        self.assertEqual(skills["bare-skill"], skill_loader.NO_DESCRIPTION)

    def test_list_skills_ignores_dirs_without_entry_file(self):
        self._write("empty-dir/references/x.md", "x\n")
        self.assertNotIn("empty-dir", [s.name for s in skill_loader.list_skills()])

    def test_missing_skills_dir_is_not_an_error(self):
        # 资源目录缺失时提示词仍要能生成，不能把整次对话带崩。
        with mock.patch.object(skill_loader, "SKILLS_DIR", Path(self.root) / "nope"):
            self.assertEqual(skill_loader.list_skills(), [])
            self.assertEqual(
                skill_loader.format_skill_list([]), "（当前没有可用技能包）"
            )

    def test_format_skill_list_renders_names_and_descriptions(self):
        out = skill_loader.format_skill_list(skill_loader.list_skills())
        self.assertIn("**frontend-design**", out)
        self.assertIn("Guidance for distinctive visual design.", out)

    # --- read_skill -------------------------------------------------------

    def test_reads_entry_file_with_line_numbers(self):
        out = self.tool.invoke({"name": "frontend-design"})
        self.assertIn("# 技能包 frontend-design / SKILL.md", out)
        # frontmatter 被剥掉，编号改从正文第 1 行（那是个空行）起。
        self.assertIn("2\t# Frontend Design", out)
        self.assertNotIn("description: Guidance", out)

    def test_entry_read_lists_sub_files(self):
        # 关键行为：模型看完入口得知道还有 references/QUERIES.md 可读。
        out = self.tool.invoke({"name": "frontend-design"})
        self.assertIn("references/QUERIES.md", out)

    def test_reads_sub_file_by_path(self):
        out = self.tool.invoke(
            {"name": "frontend-design", "path": "references/QUERIES.md"}
        )
        self.assertIn("query: hello", out)
        # 读子文件时不重复整个文件清单。
        self.assertNotIn("全部子文件", out)

    def test_paginates(self):
        # 正文 4 行（空行 / 标题 / line three / line four）。取第 2 行、限 1 行，
        # 应当只剩后面没读的部分，并给出续读用的 offset。
        out = self.tool.invoke({"name": "frontend-design", "offset": 2, "limit": 1})
        self.assertIn("2\t# Frontend Design", out)
        self.assertIn("offset=3", out)
        # 没读完就不附子文件清单（那是读完才给的收尾信息）。
        self.assertNotIn("全部子文件", out)

    def test_unknown_name_lists_available_skills(self):
        out = self.tool.invoke({"name": "nope"})
        self.assertIn("错误", out)
        self.assertIn("frontend-design", out)

    def test_missing_sub_file_lists_files(self):
        out = self.tool.invoke({"name": "frontend-design", "path": "references/no.md"})
        self.assertIn("错误", out)
        self.assertIn("references/QUERIES.md", out)

    def test_rejects_path_escape(self):
        for path in ("../../etc/passwd", "/etc/passwd"):
            out = self.tool.invoke({"name": "frontend-design", "path": path})
            self.assertIn("错误", out, path)
        # 真逃出去了的话，下面这个文件就读到了。
        self.assertNotIn("root:", self.tool.invoke({"name": "frontend-design"}))

    def test_rejects_bad_limit_and_offset(self):
        self.assertIn("错误", self.tool.invoke({"name": "frontend-design", "limit": 0}))
        self.assertIn("错误", self.tool.invoke({"name": "frontend-design", "offset": 999}))

    # --- 提示词 -----------------------------------------------------------

    def test_system_prompt_embeds_skill_list(self):
        prompt = generate_system_prompt("/workspace", MessageMode.agent, "")
        self.assertIn("**frontend-design**", prompt)
        self.assertIn("Guidance for distinctive visual design.", prompt)


if __name__ == "__main__":
    unittest.main()
