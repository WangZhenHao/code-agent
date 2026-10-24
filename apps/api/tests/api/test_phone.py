"""手机号归一化的离线测试。

这个模块的正确性直接决定「同一个号会不会建出两个账号」：`users.phone` 上是
partial unique index，而用户输入天然存在 `138 0013 8000`、`+86-138-...` 这类
写法。一旦归一化漏掉一种，就是两条记录、事后极难合并的事故。

所以这里断言的重点不是"能通过"，而是**所有写法都必须收敛到同一个裸号**。

跑法：uv run python -m unittest tests.api.test_phone
"""

from __future__ import annotations

import unittest

from app.api.user.code.phone import InvalidPhoneError, normalize_phone


class NormalizePhoneTestCase(unittest.TestCase):
    def test_all_accepted_spellings_converge(self):
        # 关键断言：同一批输入必须全部落到 11 位裸号，不能有第二份写法流出去。
        variants = [
            "13800138000",
            "138 0013 8000",
            "138-0013-8000",
            "(138)00138000",
            "+8613800138000",
            "+86 138 0013 8000",
            "86-138-0013-8000",
            "8613800138000",
            "  13800138000  ",
        ]
        for raw in variants:
            self.assertEqual(normalize_phone(raw), "13800138000", raw)

    def test_prefix_stripped_once_after_separators(self):
        # 先清分隔符再剥前缀的顺序是有讲究的：`8 6 138...` 这种拆开的写法
        # 如果先剥前缀就漏了，结果会带一个 86 前缀进库。
        self.assertEqual(normalize_phone("8 6 138 0013 8000"), "13800138000")

    def test_second_digit_range(self):
        # 第二位只接受 3-9：1[0-2] 段在大陆不是有效手机号。
        for second in "3456789":
            self.assertEqual(normalize_phone(f"1{second}800138000"), f"1{second}800138000")
        for second in "012":
            with self.assertRaises(InvalidPhoneError):
                normalize_phone(f"1{second}800138000")

    def test_rejects_wrong_length(self):
        for raw in ("1380013800", "138001380000", "1380013800a", ""):
            with self.assertRaises(InvalidPhoneError, msg=raw):
                normalize_phone(raw)

    def test_rejects_landline_and_other_prefixes(self):
        # 座机（010-...）和 170 号段以外的东西都不该被当成手机号。
        for raw in ("010-12345678", "0512 12345678", "+1 415 555 2671"):
            with self.assertRaises(InvalidPhoneError, msg=raw):
                normalize_phone(raw)

    def test_error_message_keeps_original_input(self):
        # 报错要带回用户原样输入，否则前端只能显示"格式错误"，用户不知道怎么改。
        with self.assertRaises(InvalidPhoneError) as ctx:
            normalize_phone("12345")
        self.assertIn("12345", str(ctx.exception))

    def test_plus_alone_is_not_a_prefix(self):
        # `+86` 里的 `+` 之外，别的 `+` 不该被吞掉后变成合法号码。
        with self.assertRaises(InvalidPhoneError):
            normalize_phone("+13800138000")
        # `+86 8613800138000`：剥一次前缀后还剩 86 开头，长度不对，必须拒。
        with self.assertRaises(InvalidPhoneError):
            normalize_phone("+868613800138000")


if __name__ == "__main__":
    unittest.main()
