"""外部客户端集合。

目前只有沙箱客户端。注意 `sandbox_client` 是模块级单例变量，
import 本包即建立到 router 的连接（副作用），别在循环依赖里 import 它。

导入方式：
    from app.api.sandbox.client import sandbox_client, SANDBOX_NAMESPACE, WARMPOOL
"""

from app.api.sandbox.client.sandbox import (
    SANDBOX_ID_LABEL,
    SANDBOX_NAMESPACE,
    WARMPOOL,
    create_sandbox_for_id,
    get_sandbox_for_id,
    sandbox_client,
    sandbox_url,
)

__all__ = [
    "SANDBOX_ID_LABEL",
    "SANDBOX_NAMESPACE",
    "WARMPOOL",
    "create_sandbox_for_id",
    "get_sandbox_for_id",
    "sandbox_client",
    "sandbox_url",
]
