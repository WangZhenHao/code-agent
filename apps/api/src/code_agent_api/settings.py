"""运行时配置，全部走环境变量（前缀 CODE_AGENT_）。"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CODE_AGENT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "code-agent-api"
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True

    # 沙箱层的 provider：本地开发用 docker，集群里换成 kubernetes
    sandbox_provider: str = "docker"
    sandbox_namespace: str = "code-agent-sandboxes"


settings = Settings()
