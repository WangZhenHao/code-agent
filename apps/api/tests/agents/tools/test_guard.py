"""plan 模式 bash 只读守卫的离线测试。

这是**防误触**而不是安全边界（见 guard.py 的模块注释），但它的失效方式很具体：
放行了一条写命令，模型就会在用户审阅计划之前把工作区改掉，plan 模式整个白做。
所以用例按「必然要拒的写法」列，而不是按白名单逐条点名。

跑法：uv run python -m unittest tests.agents.tools.test_guard
"""

from __future__ import annotations

import unittest

from app.agents.tools.guard import check_readonly_command


def ok(command: str) -> bool:
    return check_readonly_command(command) is None


class AllowTestCase(unittest.TestCase):
    def test_read_only_commands_pass(self):
        for cmd in (
            "ls",
            "ls -la src",
            "cat README.md",
            "head -n 20 src/app/main.py",
            "tail -f /dev/null",  # 参数看着像写，但命令本身只读
            "wc -l src/app/*.py",
            "tree -L 2",
            "pwd",
            "date",
            "jq '.a' package.json",
        ):
            self.assertTrue(ok(cmd), cmd)

    def test_pipes_and_logical_chains_are_allowed(self):
        # 管道和 && / || 是分段用的，不是写入口——plan 模式明确允许。
        self.assertTrue(ok("cat package.json | jq .name"))
        self.assertTrue(ok("ls && pwd"))
        self.assertTrue(ok("ls || pwd"))

    def test_git_read_only_subcommands(self):
        for cmd in (
            "git status",
            "git log --oneline -10",
            "git diff HEAD~1",
            "git show HEAD",
            "git --no-pager log -1",
        ):
            self.assertTrue(ok(cmd), cmd)

    def test_git_without_subcommand_passes(self):
        # 只打用法说明，没有副作用。
        self.assertTrue(ok("git"))
        self.assertTrue(ok("git --version"))

    def test_quoted_pipe_is_plain_text(self):
        # shlex 认得引号：引号里的 `|` 是普通字符，不该被切段、更不该被当成
        # "空分段"拒掉。
        #
        # `;` / `&` 是例外：它们在 _DENY_CHARS 里，整条命令扫一遍不看引号——
        # 这是刻意的保守取舍（shlex 之后分不清引号内外的 `&`），
        # 所以 `cat "a;b"` 仍会被拒。
        self.assertTrue(ok('ls "a|b"'))
        self.assertIsNotNone(check_readonly_command('cat "a;b"'))

    def test_assignment_prefix_is_skipped(self):
        # `FOO=1 ls` 要校验的是 ls；`export` 这个词本身也不能被当成命令名拒掉。
        self.assertTrue(ok("FOO=1 ls"))
        self.assertTrue(ok("export FOO=bar && ls"))
        self.assertTrue(ok("A=1 B=2 pwd"))

    def test_all_assignment_segment_passes(self):
        # 整段只有赋值：没有命令要执行，也就没有副作用。
        self.assertTrue(ok("FOO=1"))
        self.assertTrue(ok("FOO=1 && BAR=2"))


class RejectTestCase(unittest.TestCase):
    def assertRejected(self, cmd: str, *, contains: str | None = None) -> None:
        reason = check_readonly_command(cmd)
        self.assertIsNotNone(reason, cmd)
        self.assertIn("错误", reason)
        if contains:
            self.assertIn(contains, reason)

    def test_write_commands_rejected(self):
        for cmd in ("rm -rf src", "mv a b", "cp a b", "mkdir x", "touch x", "tar -xf a.tar"):
            self.assertRejected(cmd)

    def test_forwarders_rejected(self):
        # 这些能把任意命令藏进参数里，放行等于没校验。
        for cmd in (
            "bash -c 'echo hi'",
            "sh -c 'rm -rf /'",
            "python -c \"open('x','w')\"",
            "node -e 'process.exit()'",
            "env rm -rf x",
            "xargs rm",
            "make build",
            "npm install",
            "uv run rm -rf x",
        ):
            self.assertRejected(cmd)

    def test_denied_command_gets_write_operation_hint(self):
        # 黑名单只用来把报错说清楚（"这是写操作"而不是"不在白名单里"）。
        self.assertRejected("rm x", contains="写操作")

    def test_unknown_command_reports_not_whitelisted(self):
        self.assertRejected("foobar --x", contains="白名单")

    def test_redirection_and_command_substitution_rejected(self):
        for cmd in (
            "ls > out.txt",
            "ls >> out.txt",
            "cat < secret",
            "ls $(rm -rf x)",
            "ls `rm -rf x`",
            "echo $HOME",
        ):
            self.assertRejected(cmd)

    def test_structural_metacharacters_rejected(self):
        for cmd in ("ls; rm -rf x", "ls & ls", "(ls)", "ls {a,b}"):
            self.assertRejected(cmd)

    def test_guarded_flags_rejected_anywhere(self):
        # `sed -i` 会原地改文件；参数可能在任意一段，所以整条命令都扫。
        self.assertRejected("sed -i s/a/b/ f.txt", contains="参数")
        for cmd in ("find . -delete", "perl --in-place x.pl", "find . -exec rm {} \\;"):
            self.assertRejected(cmd)

    def test_git_write_subcommands_rejected(self):
        for cmd in ("git checkout .", "git reset --hard", "git clean -fd", "git push", "git config a b"):
            self.assertRejected(cmd, contains="git")

    def test_git_branch_is_rejected(self):
        # branch 不带参数时是查询，带参数就是创建——分不清就不要放进来。
        self.assertRejected("git branch new-feature")

    def test_empty_and_unbalanced_quotes(self):
        self.assertRejected("")
        self.assertRejected("   ")
        self.assertRejected("grep 'unclosed x")

    def test_empty_segment_rejected(self):
        self.assertRejected("ls && && pwd")
        self.assertRejected("ls ||")

    def test_bad_segment_poisons_whole_command(self):
        # 逐段校验：一段不合格整条拒，不能因为第一段合法就放行后面的 rm。
        self.assertRejected("ls && rm x")


if __name__ == "__main__":
    unittest.main()
