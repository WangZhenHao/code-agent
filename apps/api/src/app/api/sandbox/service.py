"""沙箱生命周期服务：启动 / 暂停会话沙箱，并把预览状态同步进 sessions 表。

`start_sandbox` 返回 SDK 的 Sandbox 句柄（不是"句柄摘要"）：调用方拿到就能直接
`commands.run(...)`，不必再按 id 查一次。

停止分两个函数，按「还要不要这份数据」选，不靠参数开关：

- `stop_sandbox`（**暂停**，会话级默认）：把 Sandbox CR 的 `spec.operatingMode` 设成
  Suspended，控制器删 Pod 但保留 CR / Service / PVC，下次 start 唤回 Running 时按原
  podTemplate 重建 Pod 并绑回同一块卷，/workspace 里的代码原样还在（见 client/sandbox.py
  的 suspend_sandbox / resume_sandbox）。预览超时回收走它。
- `delete_sandbox`（**销毁**，不可逆）：删 SandboxClaim，连 PVC 一起释放。只给确定不再
  需要数据的路径用（如用户删会话）。
"""

import asyncio
import logging
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import HTTPException, status
from k8s_agent_sandbox import SandboxError
from k8s_agent_sandbox.exceptions import SandboxNotFoundError
from k8s_agent_sandbox.sandbox import Sandbox
from sqlalchemy import select, update

from app.api.sandbox.client import (
    create_sandbox_for_id,
    delete_sandbox as delete_sandbox_handle,
    get_sandbox_for_id,
    resume_sandbox,
    sandbox_url,
    suspend_sandbox,
)
from app.db.models.session import PreviewStatus, Session, SessionStatus
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)

# 按 session_id 的进程内锁：同一个 id 的 start/stop 串行化，防止连点/并发的
# start 各建一个沙箱（create_sandbox_for_id 本身不去重，且一次创建要等 claim
# ready，窗口内第二次 start 会看不到第一个）。只在本进程内有效——多副本部署
# 时不同进程仍会各建一个，那种场景得靠 DB 层唯一约束兜底。
_locks: dict[str, asyncio.Lock] = {}
_lock_refs: dict[str, int] = defaultdict(int)


@asynccontextmanager
async def _session_lock(id: str):
    """拿到 id 对应的锁；用完释放，最后一个离开者把锁对象清掉，避免 _locks 常驻。

    计数 ref 而非简单"用完即删"：等待者可能已有别人把锁从 _locks 删掉、自己
    手上却握着旧对象，两边各建各的锁就失去互斥。ref 归零才删，保证同一时刻
    所有同 id 调用者共享同一个 Lock。
    """
    _lock_refs[id] += 1
    lock = _locks.setdefault(id, asyncio.Lock())
    try:
        async with lock:
            yield
    finally:
        _lock_refs[id] -= 1
        if _lock_refs[id] <= 0:
            _lock_refs.pop(id, None)
            _locks.pop(id, None)


# async def _require_session(id: str) -> None:
#     """确认会话存在且未删除；否则 404。

#     不区分 403：和 chat/service.py 一样，用别人的 id 探测时两种情况响应一致，
#     不泄露"这个 id 存在但不归你"。
#     """
#     async with SessionLocal() as session:
#         exists = await session.scalar(
#             select(Session.id).where(
#                 Session.id == id,
#                 Session.status != SessionStatus.delete,
#             )
#         )
#     if exists is None:
#         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")


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
    id: str,
    preview_status: PreviewStatus,
    preview_url: str | None,
    preview_time: datetime | None,
) -> None:
    """把预览状态、地址与启动时刻写回 sessions 行。

    用 UPDATE 而非先 SELECT 再改，省一次往返。preview_time 传 None 即清空
    （停止沙箱时），传具体时刻即记录本次启动时间。

    preview_time 语义 = "最近一次 start 调用的时刻"：会话已在跑时 start 会复用
    沙箱，但同样刷新该值（与 preview_status 一并刷成 running）。若将来想要
    "沙箱真正启动的时刻、复用时不改"，得改成只在新建分支写。
    """
    async with SessionLocal() as session:
        await session.execute(
            update(Session)
            .where(Session.id == id)
            .values(
                preview_status=preview_status.value,
                preview_url=preview_url,
                preview_time=preview_time,
            )
        )
        await session.commit()


async def start_sandbox(id: str) -> Sandbox:
    """启动（或复用）会话沙箱，返回其句柄，并把预览状态与地址写回 sessions 表。

    幂等：已经启动过就直接复用，不重复建；无论复用还是新建，都会把 DB 里的预览
    状态刷成 running、地址刷成当前句柄算出来的 URL（句柄重建后 URL 可能变）。
    调用方拿到返回值即可直接 commands.run(...)，无需再查。
    """
    # await _require_session(id)

    # 查询+创建整体加锁：否则连点时第二个调用会在第一个还没建完（>1min）时
    # _find_existing 查不到，各建一个沙箱。
    async with _session_lock(id):
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
        else:
            # 复用分支：句柄找回来了不代表 Pod 在。上次停过的话 CR 还挂在 Suspended
            # 上，Pod 是删掉的 —— 不唤回来，调用方拿到的是个没有容器的句柄，
            # 后面 commands.run 必挂。resume_sandbox 内部先读一次 operatingMode，
            # 已经在 Running 的直接返回，不做无谓的 patch 与等待。
            #
            # 这一步在 to_thread 里跑：wait_for_sandbox_ready 是同步 watch 循环，
            # 最长阻塞 ready_timeout 秒，直接 await 会把整个事件循环卡住。
            await asyncio.to_thread(resume_sandbox, sandbox)

    # preview_url 由 sandbox_id 拼出（见 client/sandbox.py 的 sandbox_url）。
    url = sandbox_url(sandbox)
    await _persist_preview(id, PreviewStatus.running, url, datetime.now(timezone.utc))
    return sandbox


async def stop_sandbox(id: str) -> None:
    """暂停会话沙箱：Pod 删掉、卷保留，下次进来数据还在。

    暂停后 /workspace 的内容留在 PVC 上，下次 start_sandbox 唤回 Running 时 Pod
    重建、绑回同一块卷，agent 改过的代码与装过的依赖都还在。回收的是 Pod（算力），
    不是数据。

    幂等：已经停过或从没建过（句柄取不到）时，跳过动作，仅把 DB 状态刷成 idle。
    """
    # await _require_session(id)

    # 与 start 共用同一把 id 锁：暂停改的是 Sandbox CR，与并发的 start（可能要新建
    # claim、可能要 resume 同一个 CR）交叉会互相踩——尤其 suspend 之后紧跟的 start
    # 必须在 CR 还在时看到 Suspended，串行化后两者不交叉。
    async with _session_lock(id):
        sandbox = await _find_existing(id)
        if sandbox is not None:
            # suspend_sandbox 内部先 close_connection（关本地 port-forward、清
            # _pod_name 缓存，为的是恢复后不会指向已消失的旧 Pod）再 patch
            # operatingMode。它全程是同步阻塞的 K8s 调用，所以丢进线程里。
            await asyncio.to_thread(suspend_sandbox, sandbox)

    await _persist_preview(id, PreviewStatus.idle, None, None)


async def delete_sandbox(id: str) -> None:
    """销毁会话沙箱：删 SandboxClaim，连 PVC 一起释放（不可逆）。

    与 stop_sandbox 的分工是这个模块仅有的区分点：

    - `stop_sandbox`（暂停）：保留 Sandbox CR / Service / PVC，用户下次进来
      `/workspace` 里的代码原样还在。**会话级的默认动作**，预览超时回收走它。
    - `delete_sandbox`（销毁）：删掉 SandboxClaim，claim 一没 Sandbox 与 PVC 都
      跟着走（shutdownPolicy 默认 Delete）。**只给"会话被真正删掉"这类确定不再需要
      数据的路径用**，比如用户删会话、或将来按「最后活跃」清理长期不用的沙箱。
      误用的代价是数据不可逆地丢失。

    两者名字都带 sandbox 但作用域不同，调用方按「还要不要这份数据」来选，不要按
    「名字看起来更像关闭」来选。

    幂等：已经销毁或从没建过（句柄取不到）时，跳过删除，仅把 DB 状态刷成 idle。
    """
    # await _require_session(id)

    # 与 start 共用同一把 id 锁：删 claim 时若有并发 start 正在建，会删错对象或
    # 留下孤儿 claim，串行化后两者不交叉。
    async with _session_lock(id):
        sandbox = await _find_existing(id)
        if sandbox is not None:
            # 客户端那个同名函数内部会 terminate 句柄并摘掉追踪记录，namespace
            # 固定在客户端侧（默认 default），这里只管把句柄交出去。
            await asyncio.to_thread(delete_sandbox_handle, sandbox)

    await _persist_preview(id, PreviewStatus.idle, None, None)
