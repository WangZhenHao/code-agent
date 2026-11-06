"""`web.sandbox_status` / `web.preview_heartbeat`：前端进入会话时的状态查询与续期。

两个方法都只做「查库 + 必要时触发后台动作」，不在请求里等 k8s：冷启动一次沙箱
最长 180s，挂在请求上会把 WS 调用方卡死。启动完成后的状态变化仍由
`web.server_status_changed` 推送，所以这里的应答是「发起前」的快照。

`web.sandbox_status` 在 `preview_time IS NULL` 或预览已失败时额外拉起沙箱 + dev
server（`ensure_sandbox_and_preview`，去重、不 await）；心跳只把 `preview_time`
刷成当前时刻，沙箱已被回收就返回 `extended=false`，不复活。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from app.api.ws.core.registry import rpc_method

if TYPE_CHECKING:
    from app.api.ws.core.connection import ConnectionContext


class _NoParams(BaseModel):
    """两个方法暂时都不接受参数。留着模型而不是 `params_model=None`，将来加
    字段时校验直接生效。"""

    model_config = ConfigDict(extra="forbid")


class SandboxStatusResult(BaseModel):
    """沙箱状态快照。字段集与 `preview_payload` 一致，前端只认一套形状。"""

    status: str
    preview_url: str | None = None
    preview_enabled: bool = False


class PreviewHeartbeatResult(BaseModel):
    """续期结果。只回「续没续上」，状态变化走推送，不再重复一份快照。

    `extended=false` 表示沙箱已经不在跑了（preview_time 为 NULL），前端据此
    决定要不要重新发一次 `web.sandbox_status`。
    """

    devbox_id: str
    extended: bool = False


@rpc_method("web.sandbox_status", params_model=_NoParams)
async def sandbox_status(
    ctx: ConnectionContext, params: _NoParams
) -> SandboxStatusResult:
    # 延迟 import：sandbox 包会拉进 k8s SDK / DB / hub 一整串，注册表本身
    # 只依赖 registry（同 web.preview_status 的理由）。
    from app.api.sandbox.preview import (
        ensure_sandbox_and_preview,
        preview_params,
        resolve_devbox,
    )

    row = await resolve_devbox(ctx.devbox_id, ctx.user.id)

    # 没跑过（preview_time 为 NULL）或上次预览失败时补一次启动。注意调用放在
    # 取快照之前但不等它：返回的 status 仍是库里当前值（通常是 idle），随后的
    # building / running 由推送补齐。
    if row.preview_time is None or row.preview_status == "failed":
        ensure_sandbox_and_preview(ctx.devbox_id)

    return SandboxStatusResult(**preview_params(row))


@rpc_method("web.preview_heartbeat", params_model=_NoParams)
async def preview_heartbeat(
    ctx: ConnectionContext, params: _NoParams
) -> PreviewHeartbeatResult:
    from app.api.sandbox.preview import resolve_devbox, touch_preview

    # 行数据用不上，但这次查询就是归属校验（不属于你的 devbox 直接 4404）。
    await resolve_devbox(ctx.devbox_id, ctx.user.id)
    extended = await touch_preview(ctx.devbox_id)
    return PreviewHeartbeatResult(devbox_id=ctx.devbox_id, extended=extended)
