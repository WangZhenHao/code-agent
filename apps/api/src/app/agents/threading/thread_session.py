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
    is_after_replay_cursor,
    is_message_snapshot,
    is_root_lifecycle,
    matches_subscription,
    normalize_event,
    sanitize_event,
)

logger = logging.getLogger(__name__)

# 空闲多久发一次 SSE 注释心跳（秒）。模型长时间思考时没有事件出去，中间网关
# 会按空闲超时掐连接；`: ping` 是 SSE 标准注释行，客户端解析器会忽略。
_HEARTBEAT_SECONDS = 15

# 回放缓冲上限（条数）。按轮次清空，这里只是兜底，防止一轮超长对话无限增长。
_BUFFER_MAXLEN = 2000


@dataclass
class _Sink:
    """一个 /stream 连接。queue 里放已经编码好的 SSE 帧。"""

    params: dict[str, Any]
    queue: asyncio.Queue[str] = field(default_factory=asyncio.Queue)


class ThreadSession:
    """一个线程的事件缓冲、订阅者与 run。由 registry 持有，线程内唯一。"""

    def __init__(self, thread_id: str) -> None:
        self._thread_id = thread_id
        self._buffer: list[dict[str, Any]] = []
        # 跨轮单调递增：不能被「清空 buffer」重置，客户端的 since 游标依赖它。
        self._seq = -1
        self._sinks: list[_Sink] = []
        self._run_task: asyncio.Task[None] | None = None
        self._run_id: str | None = None

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
        event = sanitize_event(
            normalize_event(
                {
                    **event,
                    "type": "event",
                    "seq": seq,
                    "event_id": f"{self._thread_id}:{seq}",
                }
            )
        )
        self._buffer.append(event)
        if len(self._buffer) > _BUFFER_MAXLEN:
            del self._buffer[: len(self._buffer) - _BUFFER_MAXLEN]

        for sink in self._sinks:
            if matches_subscription(event, sink.params):
                sink.queue.put_nowait(encode_sse(event))

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

        # 同线程已有 run：先让它收手再起新的。不 await——旧 run 可能还要跑完
        # 当前超步才对 abort 有反应，等它会把 commands 请求拖住。
        if self._run_task is not None and not self._run_task.done():
            signal_abort(self._thread_id)

        # 本轮开始，缓冲区只留本轮的事件（历史由 /chat/message 提供）。
        self._buffer.clear()
        self._run_id = run_id
        task = asyncio.create_task(self._run(state, run_id))
        self._run_task = task
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
        return run_id

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
                    self._emit(raw_event)
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
            for event in snapshot:
                if not is_after_replay_cursor(event, params):
                    continue
                if not matches_subscription(event, params):
                    continue
                yield encode_sse(event)

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

    # ── 取消 ───────────────────────────────────────────────────────────────

    async def cancel(self) -> bool:
        """请求中止本线程的 run。返回「确实有 run 在跑」。"""
        signal_abort(self._thread_id)
        return self._run_task is not None and not self._run_task.done()


# thread_id -> ThreadSession。进程内单例表；会话不主动淘汰（单副本 + 缓冲
# 按轮次清空，占用有限）。
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
