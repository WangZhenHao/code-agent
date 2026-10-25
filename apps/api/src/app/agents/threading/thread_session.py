"""一条线程（= 一个会话）的 run 生命周期与事件订阅。

对应参考项目 `LocalThreadSession`，区别只在状态的存放位置：

| 东西 | 参考项目 | 这里 |
|---|---|---|
| 事件缓冲 / seq | 进程内 list | Redis Stream（回放）+ Pub/Sub（增量） |
| 取消 | `AsyncGraphRunStream.abort()` | `signal_abort()` + Redis control 频道 |
| run 句柄 | 进程内 | 进程内（asyncio 对象没法进 Redis） |

回放缓冲**按轮次自包含**：新 run 开始时清空，run 结束时缩到几十秒的宽限期。
完整历史由 `GET /chat/message/{id}` 提供，这里只服务「本轮增量 + 中途重连」，
不承担长期缓存。

**取消为什么走 signal_abort 而不是 abort() 流**：`run_agent_with_abort`
（app/agents/helper/abort_agent/abort_handler.py）已经在节点内部赛跑了
`run.abort`，让模型和工具停下来、节点照常 return。直接 abort 外层流会让
`finish` 节点不执行，这一轮既不落库、checkpoint 也停在 codeAgent 之前——
现有「中止后写 MessageStatus.interrupted」的语义就没了。
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
import warnings
from collections.abc import AsyncIterator
from typing import Any

from langchain_core._api import LangChainBetaWarning
from langchain_core.messages import AIMessageChunk

from app.agents.helper.abort_agent import register, signal_abort, unregister
from app.agents.node.state import State
from app.agents.threading import event_bus
from app.agents.threading.protocol import (
    encode_sse,
    fragment_tool_call_delta,
    is_root_lifecycle,
    is_text_block_finish,
    matches_subscription,
    synthesize_tools_events,
)
from app.redis import get_redis

logger = logging.getLogger(__name__)

# 空闲多久发一次 SSE 注释心跳（秒）。模型长时间思考时没有事件出去，中间网关
# 会按空闲超时掐连接；`: ping` 是 SSE 标准注释行，客户端解析器会忽略。
_HEARTBEAT_SECONDS = 15

# 本进程正在跑的 run：thread_id -> Task。**只在进程内**——任务对象没法序列化。
# 同线程新 run 顶掉旧 run，靠的是 signal_abort 而不是 task.cancel()，原因见模块
# docstring。
_runs: dict[str, asyncio.Task[None]] = {}

# thread_id -> 本进程的取消频道订阅 task。run 结束后不主动取消：订阅很轻
# （一个 Redis 连接、空闲时无流量），留着让「abort 先到、run 后到」的窗口
# 仍然有效；进程退出时随连接池一起释放。
_control_tasks: dict[str, asyncio.Task[None]] = {}


def _ensure_control_subscription(thread_id: str) -> asyncio.Task[None]:
    """确保本进程订阅着该线程的取消频道。多次调用只会有一个订阅 task。"""
    task = _control_tasks.get(thread_id)
    if task is None or task.done():
        task = asyncio.create_task(_control_listener(thread_id))
        _control_tasks[thread_id] = task
    return task


async def _control_listener(thread_id: str) -> None:
    """常驻订阅 work 频道，收到 abort 就按本进程内的 run 中止信号。

    abort 由任意副本发出（`/threads/{id}/abort` 或新 run 顶掉旧 run），
    持 run 的副本收到后才真正生效。
    """
    redis = get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(event_bus.control_channel(thread_id))
    try:
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            try:
                payload = json.loads(message["data"])
            except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
                continue
            if isinstance(payload, dict) and payload.get("event") == "abort":
                signal_abort(thread_id)
    finally:
        await pubsub.unsubscribe(event_bus.control_channel(thread_id))
        await pubsub.aclose()


def _payload_of(raw: Any) -> dict[str, Any] | None:
    """Pub/Sub 消息体（bytes）→ 事件 dict。解不开就丢，不打断整条流。"""
    try:
        event = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
    except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
        return None
    return event if isinstance(event, dict) else None


def _accumulate_message_delta(partial: dict, payload: dict[str, Any]) -> None:
    """把 v3 的 messages 增量并进 run_ctx.partial（就地修改）。

    为什么需要这一手：旧路径用 `stream_mode="messages"`，拿到的直接是
    AIMessageChunk，`accumulate()` 能原样相加。v3 换了线格式，messages 事件是
    `(payload, metadata)`，payload 是 message-start / content-block-delta /
    content-block-finish 这类事件，**不再有 chunk 对象**。中止时 `abort_update`
    要从 partial 里取「模型已经吐出去、但还没提交」的半截内容，不在这里重建，
    被中止的这轮就落不了库，前端那个气泡和 DB 会对不上。

    重建方式：按 message-start 的 id 建一个 AIMessageChunk，正文用 text-delta，
    工具调用用 content-block-finish 里 `type=tool_call` 的完整块——工具的 args
    在 v3 里是逐片给的 `tool_call_chunk`，拼起来才可解析，而 finish 事件已经给了
    成品，直接取更稳。
    """
    if payload.get("event") == "message-start":
        message_id = payload.get("id")
        role = payload.get("role")
        if role != "ai" or not isinstance(message_id, str):
            return
        partial[message_id] = AIMessageChunk(content="", id=message_id)
        return

    if payload.get("event") == "content-block-delta":
        delta = payload.get("delta") or {}
        if delta.get("type") != "text-delta":
            return
        # v3 的 delta 事件不带消息 id，只能落到「最近开始的那条」上。同一时刻
        # 只有一个模型在流，按插入序取最后一个即可。
        if not partial:
            return
        message_id = next(reversed(partial))
        current = partial[message_id]
        if isinstance(current, AIMessageChunk):
            partial[message_id] = current + AIMessageChunk(
                content=delta.get("text") or "", id=message_id
            )
        return

    if payload.get("event") == "content-block-finish":
        block = payload.get("content") or {}
        if block.get("type") != "tool_call" or not partial:
            return
        message_id = next(reversed(partial))
        current = partial[message_id]
        if isinstance(current, AIMessageChunk):
            partial[message_id] = current + AIMessageChunk(
                content="",
                id=message_id,
                tool_call_chunks=[
                    {
                        "name": block.get("name"),
                        "args": json.dumps(block.get("args") or {}, ensure_ascii=False),
                        "id": block.get("id"),
                        "index": 0,
                    }
                ],
            )


class ThreadSession:
    """一个线程的入口：起 run、订阅事件。调用方每次构造即可，无内部状态。"""

    def __init__(self, thread_id: str) -> None:
        self._thread_id = thread_id

    # ── 起 run ─────────────────────────────────────────────────────────────

    async def start_run(self, state: State) -> str:
        """登记并启动一次后台 run，立即返回 run_id。

        不 await run 本身：`/commands` 要在第一个事件产生前就返回 JSON 确认。
        """
        thread_id = self._thread_id
        run_id = str(uuid.uuid4())

        # 同线程已有 run：先让它收手再起新的。不 await——旧 run 可能还要跑完
        # 当前超步才对 abort 有反应，等它会把 commands 请求拖住。
        _ensure_control_subscription(thread_id)
        previous = _runs.get(thread_id)
        if previous is not None and not previous.done():
            signal_abort(thread_id)

        task = asyncio.create_task(self._run(state, run_id))
        _runs[thread_id] = task
        task.add_done_callback(lambda t: self._on_run_done(t, run_id))
        return run_id

    def _on_run_done(self, task: asyncio.Task[None], run_id: str) -> None:
        """run 结束后的清理。用 done_callback 而不是在 _run 的 finally 里写，
        是为了覆盖「task 在第一次调度前就被取消」这种 finally 不会执行的情况。
        """
        if _runs.get(self._thread_id) is task:
            del _runs[self._thread_id]
        # 异常已经被 _run 内部兜成 lifecycle/failed，这里只需把没被 await 的
        # task 异常取出来，避免 "Task exception was never retrieved" 噪音。
        if not task.cancelled() and task.exception() is not None:
            logger.error(
                "thread run 异常 thread_id=%s run_id=%s",
                self._thread_id,
                run_id,
                exc_info=task.exception(),
            )

    async def _run(self, state: State, run_id: str) -> None:
        """跑图并把 v3 协议事件逐条发布出去。"""
        # 延迟导入：thread_session 会被 helper 的 __init__ 间接导入，而
        # graphs → node → code_agent → helper 这条链会绕回来（同
        # helper/agent_stream.py 的写法）。
        from app.agents.graphs import get_graph

        thread_id = self._thread_id

        # 登记本次 run，abort 才能找到它。**必须在第一个事件之前**：
        # run_agent_with_abort 通过 run_registry 拿 RunContext 赛跑 abort 信号，
        # 没登记时它会退化成纯 await——中止功能静默失效。旧路径由
        # helper/agent_stream.py 负责登记，新路径不经过那里，所以在这里做。
        run_ctx = register(thread_id)

        # 「abort 先到、run 后到」的竞态：abort 请求可能比本 run 的登记还早，
        # 此时 control 频道已经广播过了，只靠订阅会漏。登记之后再消费标记，
        # 这样信号能落到刚建好的 run_ctx 上。
        if await event_bus.consume_abort_request(thread_id):
            signal_abort(thread_id)

        await event_bus.mark_run(thread_id, run_id)
        announced: set[str] = set()
        finished: set[str] = set()
        # 每个工具块上次发出的内容（见 strip_tool_call_args），按 run 持有。
        seen_tool_deltas: dict[str, str] = {}
        terminal: str | None = None
        # 本 run 最后发出的序号。结束时用它判断「流里最新的事件还是不是我的」，
        # 避免把同线程新 run 的缓冲一起收缩（见 event_bus.close_stream）。
        last_seq: int | None = None

        async def publish(event: dict[str, Any]) -> None:
            nonlocal last_seq
            published = await event_bus.publish_event(thread_id, event)
            seq = published.get("seq")
            if isinstance(seq, int):
                last_seq = seq

        try:
            graph = await get_graph()

            # 清掉上一轮留下的 `aborted: True`。
            #
            # `aborted` 是 LastValue 通道，写进 checkpoint 后会一直留到下一次写入。
            # 上一轮被中止后，新 run 继承到的 state 就是「已中止」，codeAgent 里的
            # 赛跑一开始就判输、finish 也写成 interrupted——表现是「新消息发出去了
            # 但一个字都不回」。旧路径没这个问题只是因为每次都是全新的 stream，
            # 但现在 checkpoint 是长期存的，必须显式复位。
            #
            # 必须在 astream_events **之前**写：之后写会与正在跑的 run 抢同一份
            # checkpoint。
            await graph.aupdate_state(
                {"configurable": {"thread_id": thread_id}},
                {"aborted": False},
            )

            await publish(
                {
                    "type": "event",
                    "method": "lifecycle",
                    "params": {"namespace": [], "data": {"event": "running"}},
                }
            )

            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message="The v3 streaming protocol on Pregel is experimental.",
                    category=LangChainBetaWarning,
                )
                # v3 的 astream_events 是**协程**，返回 AsyncGraphRunStream；
                # 不 await 会得到 coroutine，`async for` 直接 TypeError。
                run = await graph.astream_events(
                    state,
                    {"configurable": {"thread_id": thread_id}},
                    version="v3",
                )
                async for raw_event in run:
                    # 中止时落库要用 partial（见 _accumulate_message_delta）。
                    if raw_event["method"] == "messages":
                        data = raw_event["params"].get("data")
                        payload = data[0] if isinstance(data, tuple) and data else data
                        if isinstance(payload, dict):
                            _accumulate_message_delta(run_ctx.partial, payload)

                    # 只认**根**命名空间的终态。子图（codeAgent）跑完也会发一条
                    # lifecycle completed，namespace 非空；把它当终态会让客户端
                    # 在外层图还在跑（后面还有 finish 节点）时就断开。
                    if is_root_lifecycle(raw_event, "completed"):
                        terminal = "completed"
                    elif is_root_lifecycle(raw_event, "failed"):
                        terminal = "failed"
                    elif is_root_lifecycle(raw_event, "interrupted"):
                        terminal = "interrupted"

                    for event in [
                        raw_event,
                        *synthesize_tools_events(
                            raw_event, announced=announced, finished=finished
                        ),
                    ]:
                        # text 块的 finish 只是把 delta 已发过的全文再发一遍，
                        # 不转发；但它得先经过上面的 _accumulate_message_delta，
                        # 否则中止落库拿不到完整正文。
                        if is_text_block_finish(event):
                            continue
                        # tool_call_chunk 的增量是「累积的全量 args」，改成只发
                        # 新增片段（SDK 对 tool-call-delta 是拼接），避免 O(n²)。
                        fragment = fragment_tool_call_delta(event, seen_tool_deltas)
                        if fragment is not None:
                            await publish(fragment)
        except Exception as exc:
            logger.exception("thread run 失败 thread_id=%s run_id=%s", thread_id, run_id)
            await publish(
                {
                    "type": "event",
                    "method": "lifecycle",
                    "params": {
                        "namespace": [],
                        "data": {"event": "failed", "error": str(exc)},
                    },
                }
            )
            terminal = "failed"
        finally:
            # 图自己没发终止 lifecycle（比如被 abort 提前抬走）时补一个，
            # 否则客户端永远等不到收尾帧。
            if terminal is None:
                await publish(
                    {
                        "type": "event",
                        "method": "lifecycle",
                        "params": {"namespace": [], "data": {"event": "completed"}},
                    }
                )
            await event_bus.clear_run(thread_id, run_id)
            # 历史由 /chat/message 提供，事件缓冲只服务「本次 run + 重连」：
            # 结束后缩到宽限期，不让 Redis 攒着整轮对话的逐步输出。
            await event_bus.close_stream(thread_id, last_seq)
            # 传 ctx 而不只传 id：同线程新 run 可能已经顶上来，只按 id 删会把
            # 新的那个一起删掉（见 run_registry.unregister）。
            unregister(thread_id, run_ctx)

    # ── 订阅 ───────────────────────────────────────────────────────────────

    async def stream(self, params: dict[str, Any]) -> AsyncIterator[str]:
        """开一条连接级的 SSE 订阅：先回放 `since` 之后的事件，再接增量。"""
        thread_id = self._thread_id
        redis = get_redis()
        pubsub = redis.pubsub()

        # **先订阅再回放**。反过来的话，回放读完到 subscribe 生效之间产生的
        # 事件会两头都看不到，表现为流里缺一段。
        await pubsub.subscribe(event_bus.event_channel(thread_id))

        # 后台读 Pub/Sub 的单写单读队列。为什么不用 get_message(timeout=)：
        # redis-py 的 get_message 要求 listen() 已经起了读循环，且它自己的
        # timeout 只对内部缓冲有效——空闲时等不到消息就轮询，语义和我们要的
        # 「阻塞到有消息或超时」不一样。一个常驻 reader task 最直白。
        queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        reader = asyncio.create_task(_pump(pubsub, queue))

        since = params.get("since")
        last_seq: int = since if isinstance(since, int) else -1
        # 回放里有没有根级终态。有 = 这一轮已经结束，客户端不需要再挂着等增量。
        saw_terminal = False
        try:
            running = await event_bus.has_run(thread_id)
            # 什么时候回放：
            # - 带了 since：客户端重连，补上断线期间漏掉的事件；
            # - run 正在跑：中途加入的客户端要把这一轮已经发出的事件补齐。
            #
            # 都不满足就**完全不回放**。首次进入 / 刷新的页面历史来自
            # /chat/message，缓冲里留着的是上一轮的逐步输出（可能还没过宽限期），
            # 回放它只会和历史叠出一份重复内容。
            if isinstance(since, int) or running:
                for event in await event_bus.replay_events(
                    thread_id, since if isinstance(since, int) else None
                ):
                    if not matches_subscription(event, params):
                        continue
                    seq = event.get("seq")
                    if isinstance(seq, int):
                        if seq <= last_seq:
                            continue
                        last_seq = seq
                    if any(
                        is_root_lifecycle(event, name)
                        for name in ("completed", "failed", "interrupted")
                    ):
                        saw_terminal = True
                    yield encode_sse(event)

            # 没有 run 在跑、回放里也已经是终态：这只是一次「看历史」的连接，
            # 增量永远不会再来。直接结束，别挂在心跳里等——SDK 侧会按正常断开
            # 处理（重连几次后放弃），不会把它当成错误。
            #
            # 反过来，run 正在跑（has_run 为真）时必须继续等增量；回放里没有
            # 终态说明这一轮还没结束，也要继续。
            if saw_terminal and not await event_bus.has_run(thread_id):
                return

            while True:
                try:
                    message = await asyncio.wait_for(
                        queue.get(), timeout=_HEARTBEAT_SECONDS
                    )
                except TimeoutError:
                    # 空闲心跳。模型在思考时可能很久没有增量，但连接必须在
                    # 网关上保持活跃，否则会被按空闲超时掐掉。
                    yield ": ping\n\n"
                    continue

                if message is None:  # reader 认为流已结束
                    break
                live = _payload_of(message)
                if live is None or not matches_subscription(live, params):
                    continue
                live_seq = live.get("seq")
                if isinstance(live_seq, int):
                    # 回放和增量可能重叠（订阅先于回放），按 seq 去重。
                    if live_seq <= last_seq:
                        continue
                    last_seq = live_seq
                yield encode_sse(live)
        finally:
            reader.cancel()
            await pubsub.unsubscribe(event_bus.event_channel(thread_id))
            await pubsub.aclose()

    # ── 取消 ───────────────────────────────────────────────────────────────

    async def cancel(self) -> bool:
        """请求中止本线程的 run（可跨副本）。返回「确实有 run 在跑」的语义。"""
        thread_id = self._thread_id
        await event_bus.request_abort(thread_id)
        local = signal_abort(thread_id)
        return local or await event_bus.has_run(thread_id)


async def _pump(pubsub: Any, queue: asyncio.Queue[bytes | None]) -> None:
    """把 Pub/Sub 的 `listen()` 迭代器推进单写单读队列。

    单独成函数而不是在 `stream()` 里用 `wait_for(iterator.__anext__())`：
    超时取消 `__anext__` 会丢掉迭代器内部状态，下一轮再取会漏消息或报错。
    常驻 task 负责「一直读」，队列负责「带超时地等」，两件事分开才对。
    """
    try:
        async for message in pubsub.listen():
            if message.get("type") == "message":
                queue.put_nowait(message["data"])
    finally:
        # 结束信号：让 stream() 的 while 能退出，而不是永远等心跳。
        queue.put_nowait(None)

