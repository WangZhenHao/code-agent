"""运行时配置，全部走环境变量（前缀 CODE_AGENT_）。

注意：前缀只作用于本类。LangChain / LangGraph 自己读的是 LANGSMITH_*、
ANTHROPIC_API_KEY 这类约定名，那些变量不走这里，只是同放在 .env 里。
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CODE_AGENT_",
        env_file=".env",
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

    @property
    def cors_origin_list(self) -> list[str]:
        """切分并去掉空白项；空字符串得到空列表（即不放开任何跨域来源）。"""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
