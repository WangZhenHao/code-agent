"""外部客户端集合。

目前只有沙箱客户端。`SandboxClient` 走懒加载：import 本包不会连接 router，
首次调用 `get_sandbox_client()` 时才建（它构造时要读 kubeconfig）。

导入方式：
    from app.api.sandbox.client import get_sandbox_client, SANDBOX_NAMESPACE, WARMPOOL
"""

from app.api.sandbox.client.sandbox import (
    SANDBOX_ID_LABEL,
    SANDBOX_NAMESPACE,
    WARMPOOL,
    create_sandbox_for_id,
    delete_sandbox,
    get_sandbox_client,
    get_sandbox_for_id,
    resume_sandbox,
    sandbox_url,
    suspend_sandbox,
)

__all__ = [
    "SANDBOX_ID_LABEL",
    "SANDBOX_NAMESPACE",
    "WARMPOOL",
    "create_sandbox_for_id",
    "delete_sandbox",
    "get_sandbox_client",
    "get_sandbox_for_id",
    "resume_sandbox",
    "sandbox_url",
    "suspend_sandbox",
]
