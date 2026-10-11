"""沙箱生命周期服务：启动 / 关闭会话沙箱，并把预览状态同步进 sessions 表。


## 已知局限

`create_sandbox_for_id` 不做去重（见 client/sandbox.py 的注释）。同一个 id
并发调用 start，会各建一个沙箱、贴同一个 label。当前靠上层"一个会话串行操作"
规避；真要防，需要在这里加按 id 的进程内锁。
"""

import asyncio
import logging
from dataclasses import dataclass

from fastapi import HTTPException, status
from k8s_agent_sandbox import SandboxError
from k8s_agent_sandbox.exceptions import SandboxNotFoundError
from sqlalchemy import select, update

from app.api.sandbox.client import (
    SANDBOX_NAMESPACE,
    create_sandbox_for_id,
    get_sandbox_for_id,
    sandbox_client,
    sandbox_url,
)
from app.db.models.session import PreviewStatus, Session, SessionStatus
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SandboxInfo:
    """一次 start/stop 之后沙箱与预览的状态摘要。供路由层直接透出。"""

    id: str
    preview_status: str
    preview_url: str | None


async def _require_session(id: str) -> None:
    """确认会话存在且未删除；否则 404。

    不区分 403：和 chat/service.py 一样，用别人的 id 探测时两种情况响应一致，
    不泄露"这个 id 存在但不归你"。
    """
    async with SessionLocal() as session:
        exists = await session.scalar(
            select(Session.id).where(
                Session.id == id,
                Session.status != SessionStatus.delete,
            )
        )
    if exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")


async def _find_existing(id: str):
    """按逻辑 ID 找回沙箱句柄；没建过返回 None。

    `get_sandbox_for_id` 在 claim 还在、但底层 Sandbox 已被回收时会抛
    SandboxNotFoundError——对这种"残骸"当成没启动过，让调用方走新建/跳过。
    其余异常（如 port-forward 断了、apiserver 连不上）是真故障，照常冒泡。
    """
    try:
        return await asyncio.to_thread(get_sandbox_for_id, id)
    except SandboxNotFoundError:
        return None


async def _persist_preview(
    id: str, preview_status: PreviewStatus, preview_url: str | None
) -> None:
    """把预览状态与地址写回 sessions 行。用 UPDATE 而非先 SELECT 再改，省一次往返。"""
    async with SessionLocal() as session:
        await session.execute(
            update(Session)
            .where(Session.id == id)
            .values(preview_status=preview_status.value, preview_url=preview_url)
        )
        await session.commit()


async def start_sandbox(id: str) -> SandboxInfo:
    """启动（或复用）会话沙箱，并把预览状态与访问地址写回 sessions 表。

    幂等：已经启动过就直接复用，不重复建；无论复用还是新建，都会把 DB 里的预览
    状态刷成 running、地址刷成当前句柄算出来的 URL（句柄重建后 URL 可能变）。
    """
    # await _require_session(id)

    sandbox = await _find_existing(id)
    if sandbox is None:
        try:
            sandbox = await asyncio.to_thread(create_sandbox_for_id, id)
        except SandboxError as exc:
            # 建不起来（warmpool 没有、claim 失败、超时等）是基础设施故障，
            # 转成 5xx 让调用方感知，而不是静默留下一个"启动了"的错觉。
            logger.exception("沙箱启动失败 id=%s", id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"沙箱启动失败：{exc}",
            ) from exc

    # preview_url 由 sandbox_id 拼出（见 client/sandbox.py 的 sandbox_url）。
    url = sandbox_url(sandbox)
    await _persist_preview(id, PreviewStatus.running, url)
    return SandboxInfo(id=id, preview_status=PreviewStatus.running.value, preview_url=url)


async def stop_sandbox(id: str) -> SandboxInfo:
    """关闭会话沙箱，并把预览状态复位、地址清空。

    幂等：已经关过或从没建过（句柄取不到）时，跳过删除，仅把 DB 状态刷成 idle。
    """
    # await _require_session(id)

    sandbox = await _find_existing(id)
    if sandbox is not None:
        # delete_sandbox 内部会 terminate 句柄并摘掉客户端里的追踪记录；
        # namespace 必须与建沙箱时一致（默认 default）。
        await asyncio.to_thread(
            sandbox_client.delete_sandbox, sandbox.claim_name, SANDBOX_NAMESPACE
        )

    await _persist_preview(id, PreviewStatus.idle, None)
    return SandboxInfo(id=id, preview_status=PreviewStatus.idle.value, preview_url=None)
