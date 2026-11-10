"""模型客户端。

集中在这里创建，便于统一控制超时、重试和用量统计。
"""

from functools import lru_cache

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_deepseek import ChatDeepSeek
from langchain_moonshot import ChatMoonshot
from langchain_openai import ChatOpenAI

from app.settings import settings

# lru_cache 是 Python 标准库 functools 里的装饰器，作用是把函数的返回值按参数缓存起来——同样的参数再调一次，直接把上次的结果返回，不再执行函数体。

# 这个单独的 * 是参数分隔符，它本身不是参数，作用是把后面的参数标记成"只能按关键字传，不能按位置传"。
# get_model("claude-sonnet-5", 0.5)              # ❌ TypeError
# get_model("claude-sonnet-5", temperature=0.5)  # ✅
# get_model(temperature=0.5)                     # ✅


# 模型名前缀 → 官方 LangChain 集成包，决定 get_model 走哪个分支构造客户端。
# glm/qwen 走 openai 协议没错，但关闭 thinking 用的字段形状跟纯 openai（gpt/o1/o3）
# 不一样，所以单独分出 provider 名字，不能跟 openai 混在一起处理。
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
    ("glm", "glm"),
    ("qwen", "qwen"),
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
        return ChatMoonshot(
            model_name=name,
            api_key=settings.api_key,
            base_url=settings.api_url,
            timeout=30,
            thinking=False,
        )
    if provider == "deepseek":
        # ChatDeepSeek（继承 ChatOpenAI）没有专门的 thinking 字段，裸传
        # thinking kwarg 会被 build_extra 收进 model_kwargs、再整体展开成
        # kwargs 丢给 OpenAI SDK 的 create()，对方不认识直接报 TypeError。
        # 非 OpenAI 原生参数必须走 extra_body，才会被原样塞进请求体、不经过
        # SDK 签名校验。直接用 ChatDeepSeek 构造而不走 init_chat_model，
        # 这条分支的参数形状才看得明白。
        return ChatDeepSeek(
            model_name=name,
            api_key=settings.api_key,
            base_url=settings.api_url,
            timeout=30,
            extra_body={"thinking": {"type": "disabled"}},
        )
    if provider == "anthropic":
        # ChatAnthropic 有专门的 thinking 字段，直接传即可关闭。
        return ChatAnthropic(
            model=name,
            api_key=settings.api_key,
            base_url=settings.api_url,
            timeout=30,
            thinking={"type": "disabled"},
        )
    if provider == "glm":
        # 智谱 GLM（4.6 及以上）跟 deepseek 一样用 thinking 请求参数，形状也
        # 一样是 {"type": "disabled"}，走 extra_body 透传。注意 GLM-5.3 及以上
        # 的某些型号强制开思考，传 disabled 会报错，目前仓库没配到那些型号。
        return ChatOpenAI(
            model=name,
            api_key=settings.api_key,
            base_url=settings.api_url,
            timeout=30,
            extra_body={"thinking": {"type": "disabled"}},
        )
    if provider == "qwen":
        # 通义千问（DashScope OpenAI 兼容模式）关思考用的是顶层 enable_thinking
        # 布尔值，字段名和形状跟 anthropic/deepseek/glm 都不一样，同样走
        # extra_body 透传。注意带 -thinking 后缀的纯推理型号这个参数不生效，
        # 目前仓库没配到那些型号。
        return ChatOpenAI(
            model=name,
            api_key=settings.api_key,
            base_url=settings.api_url,
            timeout=30,
            extra_body={"enable_thinking": False},
        )
    # 兜底的纯 openai 协议（gpt-*/o1-*/o3-* 以及认不出的模型名）：gpt-* 本来就
    # 不会思考，o1-*/o3-* 这类推理模型没有能完全关掉 thinking 的开关（只能调
    # reasoning_effort），所以这里不传任何 thinking 相关参数。
    return ChatOpenAI(
        model=name,
        api_key=settings.api_key,
        base_url=settings.api_url,
        timeout=30,
    )
