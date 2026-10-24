"""运行时配置，全部走环境变量（前缀 CODE_AGENT_）。

注意：前缀只作用于本类。LangChain / LangGraph 自己读的是 LANGSMITH_*、
ANTHROPIC_API_KEY 这类约定名，那些变量不走这里，只是同放在 .env 里。
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"   # apps/api/.env


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CODE_AGENT_",
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "code-agent-api"

    # 以下字段不写默认值：值必须来自环境变量或 .env。
    # 字段声明不能省——pydantic-settings 按字段名匹配环境变量，
    # 没有声明就没地方放值（这个项目里就踩过：注释掉声明后 .env 里的
    # CODE_AGENT_DEBUG 读不到，且不报错，直到访问时才 AttributeError）。
    # extra="ignore" 决定了漏配不报错，所以字段少一个的表现是静默失效。
    host: str
    port: int
    debug: bool
    cors_origins: str

    # 本地依赖服务连接串，值与 docker-compose.yml 同源（见 .env.example）
    database_url: str
    redis_url: str

    # ---------- 鉴权 ----------

    # JWT 签名密钥。同 host/port：不设默认值，缺失即启动失败。
    # 给个弱默认值比启动失败更危险——生产会静默用上人尽皆知的密钥。
    jwt_secret: str
    # 令牌有效期（天）。本阶段产品，太短会让用户反复登录；改短只需改这一处。
    jwt_expire_days: int = 7

    # ---------- 短信验证码 ----------

    # 验证码本身的有效期；也是「同号重发冷却」以外的另一个时间量
    sms_code_ttl_seconds: int = 300
    # 同一手机号两次发送之间的最小间隔，挡连点与短信轰炸
    sms_resend_cooldown_seconds: int = 60
    # 同一验证码允许的连续校验失败次数，超过即作废该码
    sms_max_attempts: int = 5

    # ---------- 语言模型 ----------
    api_key: str
    api_url: str

    # ---------- LangGraph checkpointer 连接池 ----------
    # 这三个是可选调优项，不是必填项，所以给默认值；跟上面 host/port 那批
    # 「缺失即启动失败」的性质不同，别照抄那种写法。
    #
    # 注意用的是 psycopg 的连接池，和 db/session.py 那个 SQLAlchemy engine
    # 是两个独立池：前者给 checkpointer，后者给业务表。SQLAlchemy 的池参数
    # 不作用于这里，反之亦然。
    checkpoint_pool_min_size: int = 1
    checkpoint_pool_max_size: int = 10
    # 借连接的最长等待时间（秒）。池满时超过这个时间就抛 PoolTimeout，
    # 而不是无限挂住整个请求。
    checkpoint_pool_timeout: float = 30.0

    # ---------- Thread 事件缓冲 ----------
    # /threads/{id}/stream 的回放缓冲放在 Redis（见 agents/threading/event_bus.py）。
    # 这个 TTL 同时作用于事件 Stream 和 seq 计数：线程长期没人访问后，回放
    # 窗口自然过期，避免 Redis 无限增长。客户端在那之后再重连会拿不到历史，
    # 需要靠 /chat/message 拉取落库的消息重新渲染。
    thread_event_ttl_seconds: int = 24 * 60 * 60

    # ---------- 沙箱预览回收 ----------
    # 同样是有默认值的调优项，不是必填项。
    #
    # preview_time 距现在超过这个分钟数的沙箱，会被 sweeper 回收。preview_time
    # 在每次 start 时刷新（含复用），所以这个值衡量的是"最后一次启动到现在"，
    # 而不是"沙箱真实存活时长"。
    sandbox_preview_ttl_minutes: int = 30
    # 扫描间隔（分钟）。只是扫描频率，不需要和 ttl 一个量级：取 ttl 的零头即可，
    # 代价是多扫几次空表，收益是回收延迟小。
    sandbox_sweep_interval_minutes: int = 5

    env: str

    @property
    def cors_origin_list(self) -> list[str]:
        """切分并去掉空白项；空字符串得到空列表（即不放开任何跨域来源）。"""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
