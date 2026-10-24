"""线程事件总线：Redis Stream 做回放、Pub/Sub 做增量、String 做 run/取消标记。

**为什么不用进程内 dict**（参考项目那样）：`/commands` 和 `/stream` 是两个
独立请求，多副本部署时大概率落在不同 pod 上；进程内缓冲只有发起 run 的那个
副本看得到。这里把「事件」和「取消信号」都过 Redis，任何副本都能回放、都能
广播中止。

键（thread_id 即 session_id，见仓库根 README 约定 #4）：

    thread:{id}:seq          INCR，事件序号。**必须用 INCR**——取「buffer 末尾
                             +1」在多副本下会撞号。
    thread:{id}:events       Stream，entry id = "{seq}-0"，回放按 seq 游标读。
    thread:{id}:events:pub   Pub/Sub，增量广播（消息体就是整条事件 JSON）。
    thread:{id}:control      Pub/Sub，取消信号；持有 run 的副本订阅它。
    thread:{id}:run          String，活跃 run 的 id + TTL。abort 接口据此判断
                             「有没有 run 在跑」（哪怕在别的副本）。
    thread:{id}:abort        String，已请求取消的标记 + TTL。run 启动前若看到它
                             就立刻收手，避免「abort 先到、run 后到」时漏掉。

发布顺序固定：INCR → 盖 seq → XADD → PUBLISH。先写缓冲再广播，订阅端用
last_seq 去重就能同时覆盖「回放 + 订阅」的重叠窗口。
"""

from __future__ import annotations

import json
from typing import Any

from app.agents.threading.protocol import (
    encode_sse,
    normalize_event,
    sanitize_event,
)
from app.redis import get_redis
from app.settings import settings

# 回放缓冲上限。参考项目的 buffer 是 list 且无界增长；这里按「条数」截，
# 再叠一个 TTL，防止没人访问的线程把 Redis 撑爆。
_EVENTS_MAXLEN = 2000

# run 标记的 TTL 比事件短：run 正常结束会主动 DEL，这个 TTL 只是防止进程
# 被 kill 后留下一把「永远有 run 在跑」的假标记。取 2 分钟——足够覆盖一次
# 长思考的间隔，又不至于让 abort 在 run 已死时长期返回 true。
_RUN_MARKER_TTL_SECONDS = 120


def _key(thread_id: str, suffix: str) -> str:
    return f"thread:{thread_id}:{suffix}"


def event_channel(thread_id: str) -> str:
    return _key(thread_id, "events:pub")


def control_channel(thread_id: str) -> str:
    return _key(thread_id, "control")


def _decode(value: Any) -> str:
    """decode_responses=False（见 app/redis.py 的说明），bytes 自己解。"""
    return value.decode() if isinstance(value, bytes) else str(value)


def _load(raw: Any) -> dict[str, Any] | None:
    """把 Stream entry 里的 event 字段解回 ProtocolEvent。"""
    payload = raw.get(b"event") if isinstance(raw, dict) else None
    if payload is None:
        return None
    try:
        event = json.loads(_decode(payload))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return event if isinstance(event, dict) else None


async def publish_event(thread_id: str, event: dict[str, Any]) -> dict[str, Any]:
    """归一化 → 盖 seq → 写缓冲 → 广播，返回最终写出的事件。

    `synthesize_tools_events` 由调用方（ThreadSession）在自己的去重集合上跑完
    之后逐条喂进来——这里只负责编号与分发，不关心事件内容。
    """
    redis = get_redis()
    ttl = settings.thread_event_ttl_seconds

    seq = await redis.incr(_key(thread_id, "seq"))
    event = sanitize_event(normalize_event({**event, "type": "event", "seq": seq}))

    raw = json.dumps(event, ensure_ascii=False)
    pipe = redis.pipeline()
    pipe.xadd(
        _key(thread_id, "events"),
        {"event": raw},
        id=f"{seq}-0",
        maxlen=_EVENTS_MAXLEN,
        approximate=True,
    )
    pipe.expire(_key(thread_id, "events"), ttl)
    pipe.expire(_key(thread_id, "seq"), ttl)
    pipe.publish(event_channel(thread_id), raw)
    await pipe.execute()

    return event


async def replay_events(thread_id: str, since: int | None) -> list[dict[str, Any]]:
    """读出 `seq > since` 的全部事件（since 为 None 则全量）。"""
    redis = get_redis()
    start = f"({since}-0" if isinstance(since, int) else "-"
    entries = await redis.xrange(_key(thread_id, "events"), min=start, max="+")
    events: list[dict[str, Any]] = []
    for _entry_id, fields in entries:
        event = _load(fields)
        if event is not None:
            events.append(event)
    return events


def sse_from_raw(raw: bytes | str) -> str:
    """Pub/Sub 收到的是整条事件 JSON，直接拼成 SSE 帧。"""
    return encode_sse(json.loads(_decode(raw)))


async def mark_run(thread_id: str, run_id: str) -> None:
    """登记活跃 run。同一时刻只留一个：后来的 run 直接覆盖先来的标记。"""
    redis = get_redis()
    await redis.set(
        _key(thread_id, "run"), run_id, ex=_RUN_MARKER_TTL_SECONDS
    )


async def clear_run(thread_id: str, run_id: str) -> None:
    """run 结束时清标记。**比对 id 再删**：同线程新 run 可能已经顶上来。"""
    redis = get_redis()
    key = _key(thread_id, "run")
    current = await redis.get(key)
    if current is not None and _decode(current) == run_id:
        await redis.delete(key)


async def has_run(thread_id: str) -> bool:
    redis = get_redis()
    return bool(await redis.exists(_key(thread_id, "run")))


async def request_abort(thread_id: str) -> None:
    """广播取消：写标记（给「run 还没起来」的窗口用）+ PUBLISH 给持 run 的副本。"""
    redis = get_redis()
    ttl = settings.thread_event_ttl_seconds
    await redis.set(_key(thread_id, "abort"), "1", ex=ttl)
    await redis.publish(control_channel(thread_id), json.dumps({"event": "abort"}))


async def consume_abort_request(thread_id: str) -> bool:
    """取出并清掉「已请求取消」标记。run 启动前调用，堵住先后顺序的竞态。"""
    redis = get_redis()
    key = _key(thread_id, "abort")
    value = await redis.getdel(key)
    return value is not None
