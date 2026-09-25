"""手机号归一化与校验。

放在独立的纯函数模块里，是为了保证「归一化」这件事只有一个实现、
且永远发生在查库之前。`users.phone` 上有 partial unique index，
一旦同一个号以两种写法入库（13800138000 / +8613800138000），
就会建出两个账号，而且是先到先得、事后很难合并的那种事故。

只做中国大陆手机号：11 位、1 开头、第二位 3-9。不做国际号码——
真要做的时候，这个模块是整个改动唯一的入口，接口层不用动。
"""

import re

# 允许的输入写法：可选 +86 / 86 前缀，中间可以有空格、短横线。
# 不做「输入什么就存什么」——存库一律用归一化后的 11 位裸号。
_STRIP = re.compile(r"[\s\-()]")
_PREFIX = re.compile(r"^(?:\+?86)")
_MAINLAND = re.compile(r"^1[3-9]\d{9}$")


class InvalidPhoneError(ValueError):
    """手机号无法归一化成合法的大陆号码。"""


def normalize_phone(raw: str) -> str:
    """把用户输入的手机号归一化成 11 位裸号。

    接受 `13800138000` / `138 0013 8000` / `+8613800138000` / `86-138-0013-8000`，
    一律返回 `13800138000`。非法输入抛 InvalidPhoneError。

    注意前缀剥离只做一次且在去分隔符之后：先剥前缀会把 `8 6 138...`
    这类带空格的写法漏掉，先清分隔符则 `+86` 里的 `+` 还在，判断更稳。
    """
    cleaned = _STRIP.sub("", raw).strip()
    cleaned = _PREFIX.sub("", cleaned, count=1)
    if not _MAINLAND.match(cleaned):
        raise InvalidPhoneError(f"非法手机号：{raw!r}")
    return cleaned
