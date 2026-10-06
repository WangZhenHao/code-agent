"""外部客户端集合。

目前只有沙箱客户端。注意 `sandbox_client` 是模块级单例变量，
import 本包即建立到 router 的连接（副作用），别在循环依赖里 import 它。

导入方式：
    from app.agents.client import sandbox_client, SANDBOX_NAMESPACE, WARMPOOL
"""

from app.agents.client.sandbox import (
    sandbox_client,
)

__all__ = ["sandbox_client"]
