"""模型客户端。

集中在这里创建，便于统一控制超时、重试和用量统计。
"""

from functools import lru_cache

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel


@lru_cache(maxsize=8)
def get_model(name: str = "claude-sonnet-5", *, temperature: float = 0.0) -> BaseChatModel:
    """按名字取一个 chat model，结果缓存复用。"""
    return init_chat_model(name, temperature=temperature)
