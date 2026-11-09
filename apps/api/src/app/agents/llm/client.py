"""模型客户端。

集中在这里创建，便于统一控制超时、重试和用量统计。
"""

from functools import lru_cache

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_moonshot import ChatMoonshot

from app.settings import settings

# lru_cache 是 Python 标准库 functools 里的装饰器，作用是把函数的返回值按参数缓存起来——同样的参数再调一次，直接把上次的结果返回，不再执行函数体。

# 这个单独的 * 是参数分隔符，它本身不是参数，作用是把后面的参数标记成"只能按关键字传，不能按位置传"。
# get_model("claude-sonnet-5", 0.5)              # ❌ TypeError
# get_model("claude-sonnet-5", temperature=0.5)  # ✅
# get_model(temperature=0.5)                     # ✅


# 模型名前缀 → 官方 LangChain 集成包。
# init_chat_model 自带的推断表不全（比如没有 moonshot），所以这里显式列出来，
# 认不出的统一按 openai 协议处理。
_PROVIDER_PREFIXES: tuple[tuple[str, str], ...] = (
    ("claude", "anthropic"),
    ("anthropic", "anthropic"),
    ("gpt", "openai"),
    ("o1", "openai"),
    ("o3", "openai"),
    ("deepseek", "deepseek"),
    ("kimi", "moonshot"),
    ("moonshot", "moonshot"),
    ("glm", "openai"),
    ("qwen", "openai"),
)


def _provider_for(name: str) -> str:
    lowered = name.lower()
    for prefix, provider in _PROVIDER_PREFIXES:
        if lowered.startswith(prefix):
            return provider
    return "openai"


@lru_cache(maxsize=8)
def get_model(name: str = "claude-sonnet-5") -> BaseChatModel:
    """按名字取一个 chat model，结果缓存复用。

    提供商只由模型名决定，对应各自的官方包：
    claude-* → langchain-anthropic，deepseek-* → langchain-deepseek，
    kimi/moonshot-* → langchain-moonshot，其余 → langchain-openai。
    连接参数统一取 settings（api_key / api_url）。
    """
    provider = _provider_for(name)
    if provider == "moonshot":
        # init_chat_model 不认识 moonshot，只能直接构造。
        return ChatMoonshot(
            model_name=name,
            api_key=settings.api_key,
            base_url=settings.api_url,
            timeout=30,
        )
    return init_chat_model(
        name,
        model_provider=provider,
        timeout=30,
        api_key=settings.api_key,
        base_url=settings.api_url,
    )
