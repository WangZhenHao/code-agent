"""一条线程（= 一个会话）的 run 生命周期与 SSE 订阅。

对应参考项目 `streaming-cookbook/python/react-custom-backend/src/app/session.py`
的 `LocalThreadSession`：**每个线程一个对象，进程内 buffer + sinks，seq 自增**。
没有 Redis、没有 Pub/Sub、没有跨副本协调——API 是单副本部署，那些复杂度只会
制造时序 bug。

三样东西：

    _buffer   本轮已发出的事件（带 seq），供晚到的 /stream 回放
    _sinks    每个 /stream 连接一个 (params, queue)
    _run_task 当前后台 run 的 task

请求路径：

    POST /agents/{id}/commands → get_session(id).start_run(state)
    POST /agents/{id}/stream   → get_session(id).stream(params)

**回放语义**：每次订阅都从 `since`（缺省为从头）回放缓冲区，不管有没有 run
在跑。否则「run 在 /commands 返回和 /stream 订阅之间就跑完」时客户端什么都
收不到——这正是之前「发消息没反应、刷新页面才正常」的根因。

缓冲区在每轮 run 开始时清空：完整历史由 `GET /chat/message/{id}` 提供，SSE
只负责「本轮增量」（前端 use-chat-message.ts 也按这个前提去重）。seq 跨轮
单调递增、不跟着清空，否则客户端的 `since` 游标会错位。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
import warnings
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from typing import Any

from langchain.agents.middleware.internal_call_transformer import (
    InternalCallTransformer,
)
from langchain_core._api import LangChainBetaWarning

from app.agents.helper.abort_agent import register, signal_abort, unregister
from app.agents.node.state import State
from app.agents.threading.protocol import (
    encode_sse,
    fragment_tool_call_delta,
    is_after_replay_cursor,
    is_message_snapshot,
    is_root_lifecycle,
    is_text_block_finish,
    is_tool_message_event,
    matches_subscription,
    normalize_event,
    redact_tool_event,
    sanitize_event,
    synthesize_tools_events,
)

logger = logging.getLogger(__name__)

# 空闲多久发一次 SSE 注释心跳（秒）。模型长时间思考时没有事件出去，中间网关
# 会按空闲超时掐连接；`: ping` 是 SSE 标准注释行，客户端解析器会忽略。
_HEARTBEAT_SECONDS = 15

# 回放缓冲上限（字节）。按轮次清空，这里只是兜底，防止一轮超长对话无限增长。
# 用字节而不是条数：单条 `values` 快照就可能几 MB，条数上限拦不住。
_BUFFER_MAX_BYTES = 8 * 1024 * 1024

# run 结束后缓冲再保留多久（秒）。窗口内才订阅的客户端仍能拿到本轮完整回放
# （「run 在 commands 返回和 stream 订阅之间就跑完」的场景）；过期后清掉，
# 避免之后的每次连接都重放一遍已结束的轮次。
_BUFFER_TTL_SECONDS = 60

# 起新 run 时等旧 run（被 abort）退出的上限（秒）。旧 run 可能正在一个
# 不可中断的工具调用里，等太久会把这一轮拖住；超时就 cancel。
_ABORT_GRACE_SECONDS = 30

# 无订阅者且空闲的会话保留多久（秒）后被淘汰。会话的完整历史在数据库里，
# 这里只有进程内缓冲，淘汰后重新 get_session 即可。
_SESSION_IDLE_TTL_SECONDS = 10 * 60


@dataclass
class _Sink:
    """一个 /stream 连接。queue 里放已经编码好的 SSE 帧。"""

    params: dict[str, Any]
    queue: asyncio.Queue[str] = field(default_factory=asyncio.Queue)


class ThreadSession:
    """一个线程的事件缓冲、订阅者与 run。由 registry 持有，线程内唯一。"""

    def __init__(self, thread_id: str) -> None:
        self._thread_id = thread_id
        # 缓冲存「已编码的 SSE 帧 + 事件 + 字节数」三元组：帧在发布时编码一次，
        # 回放不再逐连接重复 json.dumps（每帧几 MB 时这是实打实的 CPU）。
        self._buffer: list[tuple[str, dict[str, Any], int]] = []
        self._buffer_bytes = 0
        # 跨轮单调递增：不能被「清空 buffer」重置，客户端的 since 游标依赖它。
        self._seq = -1
        self._sinks: list[_Sink] = []
        self._run_task: asyncio.Task[None] | None = None
        self._run_id: str | None = None
        # 当前缓冲来自哪一轮。延迟清理时据此判断缓冲是否已经被新一轮接管。
        self._buffer_run_id: str | None = None

    # ── 事件分发 ───────────────────────────────────────────────────────────

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _emit(self, event: Mapping[str, Any]) -> None:
        """盖 seq / event_id → 进缓冲 → 广播给匹配的 sink。同步函数：没有 IO 要等。

        `event_id` 是 SDK 的去重键（`StreamController.#seenEventIds`）。前端
        **同时开着两条 SSE**：根内容流（depth 1）和通配 lifecycle watcher，
        后端两条都打 `/stream`，同一事件会各送一次。SDK 靠 event_id 跨这两条
        流去重——没有它就直接追加两遍，表现成首屏输出重复。值必须对同一条
        事件恒定（重放时不变），seq 天然满足。
        """
        seq = self._next_seq()
        # 脱敏放在最前面：所有来源（values 合成、ToolRecorder 直接发、messages
        # 通道）都经过 _emit，一处覆盖。工具参数里的长 content 不进流。
        event = sanitize_event(
            normalize_event(
                {
                    **redact_tool_event(event),
                    "type": "event",
                    "seq": seq,
                    "event_id": f"{self._thread_id}:{seq}",
                }
            )
        )
        frame = encode_sse(event)
        self._buffer.append((frame, event, len(frame)))
        self._buffer_bytes += len(frame)
        while self._buffer and self._buffer_bytes > _BUFFER_MAX_BYTES:
            _, _, size = self._buffer.pop(0)
            self._buffer_bytes -= size

        for sink in self._sinks:
            if matches_subscription(event, sink.params):
                sink.queue.put_nowait(frame)

    def _emit_lifecycle(self, name: str, *, error: str | None = None) -> None:
        data: dict[str, Any] = {"event": name}
        if error is not None:
            data["error"] = error
        self._emit(
            {
                "type": "event",
                "method": "lifecycle",
                "params": {"namespace": [], "data": data},
            }
        )

    # ── 起 run ─────────────────────────────────────────────────────────────

    async def start_run(self, state: State) -> str:
        """登记并启动一次后台 run，立即返回 run_id。

        不 await run 本身：`/commands` 要在第一个事件产生前就返回 JSON 确认。
        """
        run_id = str(uuid.uuid4())

        # 同线程已有 run：先让它收手再起新的，但**不等它**——旧 run 可能还要
        # 跑完当前超步才对 abort 有反应，等它会把 commands 请求拖住。
        # 也不能立刻清缓冲：旧任务在注意到 abort 之前还会继续 _emit，它的事件
        # （包括补发的终止 lifecycle）会写进新一轮的缓冲，前端会把旧 run 的
        # completed 当成本轮的收尾，isLoading 提前收掉。所以把「等旧 run 退出
        # → 清缓冲 → 起跑」串进新任务里，见 _run_sequenced。
        old_task = self._run_task
        if old_task is not None and not old_task.done():
            signal_abort(self._thread_id)

        self._run_id = run_id
        task = asyncio.create_task(self._run_sequenced(state, run_id, old_task))
        self._run_task = task
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
        return run_id

    async def _run_sequenced(
        self,
        state: State,
        run_id: str,
        old_task: asyncio.Task[None] | None,
    ) -> None:
        """等旧 run 退出（有上限）→ 清缓冲 → 开跑。"""
        if old_task is not None and not old_task.done():
            try:
                await asyncio.wait_for(
                    asyncio.shield(old_task), timeout=_ABORT_GRACE_SECONDS
                )
            except (TimeoutError, asyncio.CancelledError):
                # 旧 run 卡在不可中断的调用里：硬取消，别再等了。它剩下的事件
                # 宁可丢掉，也不能串进新一轮的缓冲。
                old_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await old_task

        # 本轮开始，缓冲区只留本轮的事件（历史由 /chat/message 提供）。
        self._buffer.clear()
        self._buffer_bytes = 0
        self._buffer_run_id = run_id

        await self._run(state, run_id)

    async def _run(self, state: State, run_id: str) -> None:
        """跑图并把 v3 协议事件逐条发出去。"""
        # 延迟导入：thread_session 会被 helper 的 __init__ 间接导入，而
        # graphs → node → code_agent → helper 这条链会绕回来。
        from app.agents.graphs import get_graph

        thread_id = self._thread_id

        # 登记本次 run，abort 才能找到它。**必须在第一个事件之前**：
        # run_agent_with_abort 通过 run_registry 拿 RunContext 赛跑 abort 信号，
        # 没登记时它会退化成纯 await——中止功能静默失效。
        run_ctx = register(thread_id)

        terminal: str | None = None
        # 每轮独立的缩小器状态，不能挂在 session 上：下一轮的 lc 消息 id
        # 可能复用同前缀，跨轮残留的基线会让前缀判断永远走回退分支。
        seen_tool_args: dict[str, str] = {}
        # content 长字段的「正在吞」状态，按块记录（见 protocol.deltas._redacted_delta）。
        suppressed_tool_args: dict[str, bool] = {}
        announced_tool_calls: set[str] = set()
        finished_tool_calls: set[str] = set()
        # 本轮出现过的工具消息 id。它们的正文就是工具输出，已落 tool_calls 表，
        # 不再转发到 messages 通道（见 protocol.is_tool_message_event）。
        tool_message_ids: set[str] = set()

        try:
            graph = await get_graph()

            # 清掉上一轮留下的 `aborted: True`。
            #
            # `aborted` 是 LastValue 通道，写进 checkpoint 后会一直留到下一次写入。
            # 上一轮被中止后，新 run 继承到的 state 就是「已中止」，codeAgent 里的
            # 赛跑一开始就判输、finish 也写成 interrupted——表现是「新消息发出去了
            # 但一个字都不回」。必须在 astream_events **之前**写：之后写会与正在
            # 跑的 run 抢同一份 checkpoint。
            await graph.aupdate_state(
                {"configurable": {"thread_id": thread_id}},
                {"aborted": False},
            )

            self._emit_lifecycle("running")

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
                    # 摘要中间件发起的模型调用带 `lc_internal_call` 标记。父图的流
                    # 拿不到子图的 mux，要显式传这个 transformer 才能把内部调用的
                    # token 从事件日志里剔掉。
                    transformers=(InternalCallTransformer,),
                )
                async for raw_event in run:
                    # 只认**根**命名空间的终态。子图（codeAgent）跑完也会发一条
                    # lifecycle completed，把它当终态会让客户端在外层图还在跑
                    # （后面还有 finish 节点）时就断开。
                    if is_root_lifecycle(raw_event, "completed"):
                        terminal = "completed"
                    elif is_root_lifecycle(raw_event, "failed"):
                        terminal = "failed"
                    elif is_root_lifecycle(raw_event, "interrupted"):
                        terminal = "interrupted"

                    # 整条消息快照（摘要中间件塞的 summary HumanMessage /
                    # RemoveMessage）不是增量，转发只会把压缩后的摘要漏给前端。
                    if is_message_snapshot(raw_event):
                        continue
                    # text 块的 content-block-finish 重复了 delta 已发过的全文，
                    # 不转发（tool_call 块必须保留，SDK 用它拿完整参数）。
                    if is_text_block_finish(raw_event):
                        continue
                    # 工具消息（role=tool）的正文就是工具输出，已落 tool_calls 表，
                    # 前端按 tool_call_id 查询——不再进 SSE。
                    if is_tool_message_event(raw_event, tool_message_ids):
                        continue
                    # tool_call_chunk 的 block-delta 是累积整块，每帧重发全部参数
                    # （O(n²)）；改写成只带新增后缀的 tool-call-delta。
                    shrunk = fragment_tool_call_delta(
                        raw_event, seen_tool_args, suppressed_tool_args
                    )
                    if shrunk is None:
                        continue
                    # Python v3 不一定伴随 messages 发 tools 通道事件；从 values
                    # 快照里合成 tool-started / tool-finished，否则前端工具卡片
                    # 收不到状态。合成完 values 本身不再转发（见下）。
                    for synthesized in synthesize_tools_events(
                        shrunk,
                        announced=announced_tool_calls,
                        finished=finished_tool_calls,
                    ):
                        self._emit(synthesized)
                    # values / checkpoints 是整状态快照。hydrate 走
                    # GET /agents/{id}/state，历史走 /chat/message/{id}，这两路
                    # 事件对前端没有增量价值，转发只会在缓冲里堆几 MB。
                    if shrunk.get("method") in {"values", "checkpoints"}:
                        continue
                    self._emit(shrunk)
        except Exception as exc:
            logger.exception(
                "thread run 失败 thread_id=%s run_id=%s", thread_id, run_id
            )
            self._emit_lifecycle("failed", error=str(exc))
            terminal = "failed"
        finally:
            # 图自己没发终止 lifecycle（比如被 abort 提前抬走）时补一个，
            # 否则客户端永远等不到收尾帧。
            if terminal is None:
                self._emit_lifecycle("completed")
            # 传 ctx 而不只传 id：同线程新 run 可能已经顶上来，只按 id 删会把
            # 新的那个一起删掉（见 run_registry.unregister）。
            unregister(thread_id, run_ctx)
            if self._run_id == run_id:
                self._run_id = None
                self._run_task = None
                # 终止后延迟清空：给「run 在 commands 返回和 stream 订阅之间就
                # 跑完」留回放窗口，过期后清掉，避免之后的连接重放已结束的轮次。
                self._schedule_buffer_clear(run_id)

    def _schedule_buffer_clear(self, run_id: str) -> None:
        async def clear_later() -> None:
            await asyncio.sleep(_BUFFER_TTL_SECONDS)
            # 只清「本 run 留下的」缓冲：期间新一轮开始（_run_id 非空）或已经
            # 写完并被新一轮接管（_buffer_run_id 变了）都不动，否则会把新一轮
            # 的回放窗口提前掐掉。
            if self._run_id is not None or self._buffer_run_id != run_id:
                return
            self._buffer.clear()
            self._buffer_bytes = 0

        task = asyncio.create_task(clear_later())
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

    # ── 订阅 ───────────────────────────────────────────────────────────────

    async def stream(self, params: dict[str, Any]) -> AsyncIterator[str]:
        """开一条连接级的 SSE 订阅：先回放 `since` 之后的事件，再接增量。"""
        sink = _Sink(params=params)
        # 先拍快照，再登记 sink。这两行之间没有 await，事件循环不会切走，
        # 所以快照 + 广播恰好覆盖全部事件、不重不漏。
        #
        # 不能边登记边遍历 self._buffer：yield 会让出控制权，run 继续往
        # buffer 里 append；Python 的 list 迭代按索引走，会把新追加的元素
        # 也扫出来——而它们同时又已进了 sink.queue，前端就收到两份
        # （首屏进来时最明显，刷新后 run 已结束所以不复现）。
        snapshot = list(self._buffer)
        self._sinks.append(sink)

        try:
            # 先回放再等增量。这里**不判断有没有 run 在跑**：run 可能在
            # /commands 返回和本订阅建立之间就跑完了，不看缓冲的话客户端
            # 什么都收不到。缓冲每轮开始时清空，回放不会把历史再演一遍。
            for frame, event, _ in snapshot:
                if not is_after_replay_cursor(event, params):
                    continue
                if not matches_subscription(event, params):
                    continue
                yield frame

            # 之后只等增量。空闲时发心跳注释帧，保住中间的网关连接。
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        sink.queue.get(), timeout=_HEARTBEAT_SECONDS
                    )
                except TimeoutError:
                    yield ": ping\n\n"
                    continue
                yield chunk
        finally:
            with contextlib.suppress(ValueError):
                self._sinks.remove(sink)
            # 最后一个订阅者断开且没有 run 在跑：安排空闲淘汰（见 _evict_later）。
            if not self._sinks and not self.is_running():
                self._schedule_eviction()

    def _schedule_eviction(self) -> None:
        async def evict_later() -> None:
            await asyncio.sleep(_SESSION_IDLE_TTL_SECONDS)
            # 期间有新订阅或新 run 就作罢；再检查一次引用的还是不是自己，
            # 避免把 get_session 新建的同 id 会话误删。
            if (
                self._sinks
                or self.is_running()
                or _sessions.get(self._thread_id) is not self
            ):
                return
            _sessions.pop(self._thread_id, None)

        task = asyncio.create_task(evict_later())
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

    # ── 状态 ───────────────────────────────────────────────────────────────

    def is_running(self) -> bool:
        """是否有 run 在本线程上跑着。`/state` 接口用它回答 SDK 的 liveness 探测。"""
        return self._run_task is not None and not self._run_task.done()

    # ── 取消 ───────────────────────────────────────────────────────────────

    async def cancel(self) -> bool:
        """请求中止本线程的 run。返回「确实有 run 在跑」。"""
        signal_abort(self._thread_id)
        return self._run_task is not None and not self._run_task.done()


# thread_id -> ThreadSession。进程内单例表；空闲且无订阅者的会话会被
# _schedule_eviction 淘汰（完整历史在数据库里，重建很便宜）。
_sessions: dict[str, ThreadSession] = {}

# 正在跑的 task 的强引用。asyncio 只弱引用 task，`_run_task` 被新 run 覆盖后
# 旧 task 可能中途被 GC——表现为「发第二条消息，第一条莫名停住」。
_background_tasks: set[asyncio.Task[None]] = set()


def get_session(thread_id: str) -> ThreadSession:
    """取（或创建）该线程的会话对象。"""
    session = _sessions.get(thread_id)
    if session is None:
        session = ThreadSession(thread_id)
        _sessions[thread_id] = session
    return session
