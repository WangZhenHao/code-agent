"""沙箱预览的定时回收：preview_time 超时的会话，把沙箱关掉。

和 service.py 的分工：那边是「用户动作触发的启停」，这边是「无人触发时的兜底」。
回收动作本身不重写，直接复用 `stop_sandbox`（幂等，且和 start 共用同一把按 id
的进程内锁，不会和并发的 start 交叉）。

调度器跑在 API 进程内（由 main.py 的 lifespan 启停）。多副本部署时每个副本都会
扫一遍，同一行可能被两个副本同时收——`stop_sandbox` 幂等 + `_find_existing` 把
SandboxNotFoundError 吞成「没建过」，所以后果只是多一次 delete 调用，不会删错。
要严格单实例得在部署层解决（leader election 或换成 K8s CronJob），在这里加锁没用
（`_locks` 是进程内的，跨副本不共享）。
"""

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.api.sandbox.service import stop_sandbox
from app.db.models.session import Session
from app.db.session import SessionLocal
from app.settings import settings

logger = logging.getLogger(__name__)

# 任务 id 固定，便于日志和将来的手动触发（如 scheduler.get_job(...).modify 改间隔）。
_SWEEP_JOB_ID = "sweep_expired_previews"

# 模块级单体：lifespan 启停的是同一个实例。不设成 None 再懒加载，是因为
# `AsyncIOScheduler()` 构造本身不启动循环、不建线程，只是建个对象。
_scheduler = AsyncIOScheduler(timezone=timezone.utc)


async def sweep_expired_previews() -> None:
    """扫一遍超时的预览会话，逐个回收沙箱。

    单行回收失败只记日志，不中断整轮：某个 claim 被手动删过、或 apiserver 一时
    连不上，不该让后面几十个正常会话都跟着不回收。失败的行 preview_time 保持不变，
    下一轮会再试，天然重试。
    """
    cutoff = datetime.now(timezone.utc) - timedelta(
        minutes=settings.sandbox_preview_ttl_minutes
    )

    # 时间比较放在 DB 端做（用 cutoff 参数而不是 SQL 的 now()，是为了让 ttl
    # 留在 Python 侧统一配置），避免各副本时钟不一致导致该收的不收。
    #
    # 故意不加 status != SessionStatus.delete：删除会话的路径目前也不释放沙箱，
    # 带上这个过滤会让「已删除会话 + 存活的沙箱」永远漏掉，白占 warmpool。
    async with SessionLocal() as session:
        rows = await session.scalars(
            select(Session.id).where(
                Session.preview_time.is_not(None),
                Session.preview_time < cutoff,
            )
        )
        ids = list(rows)

    if not ids:
        return

    logger.info("预览回收：发现 %d 个超时会话", len(ids))
    for id in ids:
        try:
            await stop_sandbox(id)
        except Exception:
            logger.exception("预览回收失败 id=%s", id)
        else:
            logger.info("预览回收完成 id=%s", id)


def start_sweeper() -> None:
    """启动定时扫描。在 lifespan 里调，此时事件循环已在运行。

    max_instances=1：上一轮还没扫完就不起新的，否则慢轮次会叠加成并发的
    delete_sandbox 风暴。coalesce=True：进程被挂起后恢复时只补跑一次，而不是把
    积压的触发一个个补上。两者都是「宁可少收、不可重收」的取向，正好和回收动作
    幂等但不免费的事实匹配。
    """
    _scheduler.add_job(
        sweep_expired_previews,
        "interval",
        minutes=settings.sandbox_sweep_interval_minutes,
        id=_SWEEP_JOB_ID,
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()
    logger.info(
        "预览回收调度器已启动：每 %d 分钟扫一次，ttl=%d 分钟",
        settings.sandbox_sweep_interval_minutes,
        settings.sandbox_preview_ttl_minutes,
    )


def stop_sweeper() -> None:
    """停掉调度器。wait=False：不等正在跑的那一轮扫完，否则退出会挂在
    delete_sandbox 的网络调用上；那一轮的 DB 状态写入是幂等的，中断无所谓。
    """
    # APScheduler 的 shutdown 对未启动的实例是安全的；重复调用也不报错。
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("预览回收调度器已停止")
