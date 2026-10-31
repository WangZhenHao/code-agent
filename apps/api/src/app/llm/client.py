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
    """按名字取一个 chat model，结果缓存复用。

    模型名到厂商的映射**交给网关，不交给 LangChain**。

    init_chat_model 默认按模型名前缀猜厂商（claude-* → anthropic 包、
    deepseek-* → deepseek 包……），猜中的那个包必须是**独立安装的原生集成包**，
    没装就在运行时抛 "requires the langchain-xxx package"。但我们走的是统一的
    OpenAI 兼容网关（CODE_AGENT_API_URL），claude / deepseek / kimi 都由网关
    按 OpenAI 格式转发——既不该、也不需要为每家装原生包。

    显式传 model_provider="openai" 关掉那个前缀推断：所有请求都编成 OpenAI 协议，
    发往 base_url，由网关负责路由到真正的后端。代价是拿不到厂商独有参数
    （Anthropic 的 cache_control / thinking 等）——需要时再改回原生包。

    新增模型 = 网关侧支持 + 传个名字即可，这里和依赖都不用动。
    """
    return init_chat_model(
        name,
        model_provider="openai",
        timeout=30,
        api_key=settings.api_key,
        base_url=settings.api_url,
    )
