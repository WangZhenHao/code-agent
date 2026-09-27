"""模型客户端。

集中在这里创建，便于统一控制超时、重试和用量统计。
"""

from functools import lru_cache

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from app.settings import settings


# lru_cache 是 Python 标准库 functools 里的装饰器，作用是把函数的返回值按参数缓存起来——同样的参数再调一次，直接把上次的结果返回，不再执行函数体。

# 这个单独的 * 是参数分隔符，它本身不是参数，作用是把后面的参数标记成"只能按关键字传，不能按位置传"。
# get_model("claude-sonnet-5", 0.5)              # ❌ TypeError
# get_model("claude-sonnet-5", temperature=0.5)  # ✅
# get_model(temperature=0.5)                     # ✅

@lru_cache(maxsize=8)
def get_model(name: str = "claude-sonnet-5") -> BaseChatModel:
    """按名字取一个 chat model，结果缓存复用。"""
    return init_chat_model(
        name,
        timeout=30,
        api_key=settings.api_key,
        base_url=settings.api_url,
    )
