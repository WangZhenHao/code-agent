"""`preview.*` 方法。

目前只有 `preview.status`：前端连上后主动拉一次，以及收到
`web.server_status_changed` 后兜底核对。预览的启动/停止仍走 HTTP
（`POST /agents/{id}/commands` 里会 start_sandbox），不在这里开。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from app.api.ws.core.registry import rpc_method

if TYPE_CHECKING:
    from app.api.ws.core.connection import ConnectionContext


class PreviewStatusParams(BaseModel):
    """暂时不接受参数。留着模型而不是 `params_model=None`：将来加过滤器
    （worktree_name 等）时校验直接生效，不用先收 dict 再手工判断。"""

    model_config = ConfigDict(extra="forbid")


class PreviewStatusResult(BaseModel):
    """预览状态。

    只有 `status` / `preview_url` / `preview_enabled` 有真实数据来源；
    其余字段是 Coze 那边有、本地还没有的概念，键名先留着，值待定（返回 None）。
    """

    status: str
    preview_url: str | None = None
    preview_enabled: bool = False

    # --- 值待定 ---
    worktree_name: str | None = None
    branch: str | None = None
    running_previews: int | None = None
    max_previews: int | None = None
    sub_id: str | None = None
    project_type: str | None = None


@rpc_method("preview.status", params_model=PreviewStatusParams)
async def preview_status(
    ctx: ConnectionContext, params: PreviewStatusParams
) -> PreviewStatusResult:
    # 延迟 import：service 会 import auth，auth 会 import security/db；
    # 放在模块顶层也能跑，但延迟到调用点能保证「注册表只依赖 registry」这条链
    # 不被 DB 依赖污染——测试 dispatcher 时不用碰数据库驱动。
    from app.api.ws.service import preview_params, resolve_devbox

    # 重查一次库（而不是用握手时的结果）：连接期间会话可能被删，快照要"现在"的真值。
    row = await resolve_devbox(ctx.devbox_id, ctx.user.id)
    return PreviewStatusResult(**preview_params(row))
