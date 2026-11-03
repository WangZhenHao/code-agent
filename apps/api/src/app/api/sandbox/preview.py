"""沙箱内的预览服务：拉起 Next dev server、探测端口、写库、推给前端。

启动入口是 `start_preview(session_id, sandbox)` —— 同步函数，起一个后台任务
就返回，调用方（`start_agent_run`）不必等 Next 首次编译完成的十几秒。

就绪的判据是 `localhost:3000` 返回 200，而不是「命令跑完了」：`npm run dev` 用
nohup 丢到后台，命令本身立刻返回，那不代表服务可用。

推送走 `publish_devbox_event`（进程内），method 是 `web.server_status_changed`，
`params.preview` 与 `preview.status` 应答同形状（`preview_payload`）。

另外承载 WS 层「读预览状态」的两个纯函数：`resolve_devbox`（归属校验）与
`preview_params`（Session 行 → 预览对象）。放这里是因为它们和推送共用同一份
形状定义，拆开会两边字段漂移。注意这带来一条反向依赖：本模块 import
`ws.core.auth` 取领域异常——`ws.core.auth` 不 import sandbox，不成环。
"""

import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import Any

from k8s_agent_sandbox.sandbox import Sandbox
from sqlalchemy import select

from app.api.sandbox.client import sandbox_url
from app.api.sandbox.service import persist_preview
from app.api.ws.core import hub
from app.api.ws.core.auth import CLOSE_NOT_FOUND, WsAuthError
from app.db.models.session import PreviewStatus, Session, SessionStatus
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)

# 沙箱内 Next dev server 的端口（与 deploy/api/sandbox-ingress 的 X-Sandbox-Port 一致）。
DEV_PORT = 3000

# 后台起 dev server。运行时 /execute 用 shlex.split 不经 shell，所以显式 `sh -c`，
# 末尾 `&` 让 shell 立刻返回、不阻塞到超时。每次起 run 都跑一遍是幂等的（nohup
# 重启），保证沙箱被回收重建后预览仍然可用。
PREVIEW_COMMAND = "sh -c 'cd /workspace && nohup npm run dev > /tmp/next.log 2>&1 &'"

PROBE_COMMAND = (
    f"sh -c 'curl -s -o /dev/null -w %{{http_code}} localhost:{DEV_PORT}/ 2>/dev/null'"
)

# 首次编译通常十几秒，给足余量。
_PROBE_INTERVAL = 1.5
_PROBE_ATTEMPTS = 60

# 后台任务要留强引用：只被事件循环弱引用着的话可能中途被 GC，异常也会被静默吞掉。
_tasks: set[asyncio.Task] = set()


def preview_payload(status: str, preview_url: str | None) -> dict[str, Any]:
    """预览对象的对外形状。推送和 `preview.status` 应答共用这一份定义。

    只有 status / preview_url 有数据来源；其余键名保留、值为 None —— 它们对应的
    能力本地还没有，假值比缺字段更容易误导前端。
    """
    return {
        "status": status,
        "preview_url": preview_url,
        # 由 status 推导，不是独立数据：running 才算开了预览
        "preview_enabled": status == PreviewStatus.running.value,
        # --- 值待定 ---
        "worktree_name": None,
        "branch": None,
        "running_previews": None,
        "max_previews": None,
        "sub_id": None,
        "project_type": None,
    }


async def resolve_devbox(devbox_id: str, user_id: int) -> Session:
    """确认会话存在、未删除、且归当前用户。

    三种失败共用 4404（对齐 HTTP 层「归属错一律 404」）：区分开等于告诉攻击者
    「这个 id 存在，只是不是你的」。
    """
    async with SessionLocal() as session:
        row = await session.scalar(
            select(Session).where(
                Session.id == devbox_id,
                Session.user_id == user_id,
                Session.status != SessionStatus.delete,
            )
        )
    if row is None:
        raise WsAuthError(CLOSE_NOT_FOUND, "devbox 不存在")
    return row


def preview_params(row: Session) -> dict[str, Any]:
    """Session 行 → 预览对象。形状与推送共用 `preview_payload`，避免两边字段漂移。"""
    return preview_payload(
        row.preview_status or PreviewStatus.idle.value, row.preview_url
    )


def start_preview(session_id: str, sandbox: Sandbox) -> None:
    """后台保证预览可用，并推送最终状态。不 await、不抛异常。"""
    task = asyncio.create_task(_ensure(session_id, sandbox))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def _ensure(session_id: str, sandbox: Sandbox) -> None:
    try:
        # 同一会话第二次发消息的常态：dev server 还在跑，重启只会白等一次编译。
        if not await asyncio.to_thread(_probe, sandbox):
            await persist_preview(session_id, PreviewStatus.building, None, None)
            ready = await asyncio.to_thread(_start_and_wait, sandbox)
            status = PreviewStatus.running if ready else PreviewStatus.failed
            url = sandbox_url(sandbox)
            if not ready:
                logger.warning(
                    "预览未在预期时间内就绪 id=%s，看看沙箱内 /tmp/next.log", session_id
                )
        else:
            status = PreviewStatus.running
            url = sandbox_url(sandbox)

        await persist_preview(session_id, status, url, datetime.now(UTC))
        _publish(session_id, status, url)
    except Exception:
        # 后台任务里的异常没有调用方接，只能记日志，不能让任务静默死掉。
        logger.exception("预览启动失败 id=%s", session_id)


def _publish(session_id: str, status: PreviewStatus, url: str | None) -> None:
    try:
        hub.publish_devbox_event(
            session_id,
            "web.server_status_changed",
            {"preview": preview_payload(status.value, url)},
        )
    except Exception:
        # 推送是尽力而为：没人连着返回 0，序列化失败也只影响显示。
        logger.warning("预览状态推送失败 id=%s", session_id, exc_info=True)


def _probe(sandbox: Sandbox) -> bool:
    """同步探测：dev server 已经在应答。任何异常都当没就绪。"""
    commands = sandbox.commands
    if commands is None:
        return False
    try:
        stdout = commands.run(PROBE_COMMAND).stdout or ""
        return stdout.strip() == "200"
    except Exception:
        return False


def _start_and_wait(sandbox: Sandbox) -> bool:
    """同步：拉起 dev server 并轮询就绪。整体在 to_thread 里跑，不占事件循环。"""
    commands = sandbox.commands
    if commands is None:
        raise RuntimeError("沙箱没有暴露 commands 接口，无法启动预览服务")
    commands.run(PREVIEW_COMMAND)
    for _ in range(_PROBE_ATTEMPTS):
        if _probe(sandbox):
            return True
        time.sleep(_PROBE_INTERVAL)
    return False
