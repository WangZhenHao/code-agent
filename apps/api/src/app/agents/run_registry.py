"""进程内的「正在跑的 run」注册表。

解决的问题：一次 agent 对话的 `graph.astream()` 迭代器是 `agent_stream` 里的局部
变量，外部拿不到句柄，所以没有任何办法从另一个请求（`POST /agents/abort/{id}`）
去中止它。这里给每个 session 登记一个 RunContext，abort 接口按下 event，
跑图的节点在赛跑里看到它就收手。

为什么单独成模块：要 import 它的地方横跨 agents/helper/（agent_stream 登记）、
agents/node/（code_agent 赛跑）、api/agent/（abort 接口按下）。它必须像 state.py
一样**不依赖包内任何其它模块**，否则立刻成环——agent_stream 顶层 import node，
node import helper，helper 又 import node。

**只在本进程内有效。** 多副本部署时 abort 请求可能落到另一个副本，拿到 None，
表现为「点了停止没反应」。那种场景要靠 Redis 广播，本模块不做（与
api/sandbox/service.py 的 _locks 同样的限制）。
"""

import asyncio
from dataclasses import dataclass, field


@dataclass
class RunContext:
    """一次正在进行的 run。

    abort / aborted 成对使用，缺一不可：
      - `abort` 是给跑图的节点 await 的 event，负责**让模型和工具停下来**。
      - `aborted` 是给收尾方读的布尔，负责**让 finish 知道该写 interrupted**。
    只按 event 不看 aborted 的话，节点得靠 except CancelledError 来判断是不是
    被中止的；显式布尔更直白，也免得把别的取消混进来。
    """

    session_id: str
    abort: asyncio.Event = field(default_factory=asyncio.Event)
    aborted: bool = False

    # 已经流出去的半截内容，按消息 id 累积：id -> AIMessageChunk | ToolMessage。
    # 存在的理由见 agent_stream：stream_mode="messages" 是回调侧信道，和 checkpoint
    # 无关，所以「模型已经吐了半句话但还没提交」这段内容，除了这里没有任何地方存着。
    partial: dict = field(default_factory=dict)


# session_id -> RunContext。同一 session 上一个新 run 会覆盖旧的（见 register）。
_runs: dict[str, RunContext] = {}


def register(session_id: str) -> RunContext:
    """登记一次新 run，返回它的上下文。

    不做「已有就报错」：同一会话的上一次 run 若因为客户端断连没清干净，新请求
    不应该被卡住。覆盖旧的都是有意的，代价是旧 run 的 abort 失去意义——它本来
    也快被 GC 了。
    """
    ctx = RunContext(session_id=session_id)
    _runs[session_id] = ctx
    return ctx


def get(session_id: str) -> RunContext | None:
    return _runs.get(session_id)


def unregister(session_id: str, ctx: RunContext) -> None:
    """注销。**必须带上自己的 ctx**，不能只按 id 删。

    run 结束时若已经有新 run 顶上来（同 session 连续两次对话，前一个的 finally
    晚到），只按 id 删会把**新的**那个一起删掉，新 run 从此再也不响应 abort——
    而且完全静默。比对对象身份才安全。
    """
    if _runs.get(session_id) is ctx:
        del _runs[session_id]


def signal_abort(session_id: str) -> bool:
    """按下中止。返回是否有 run 接住了这个信号。

    返回 False 不是错误：run 已经跑完、或请求落到了别的副本，都会是 False。
    调用方照常返回 200，让前端重复点「停止」不会弹错误。
    """
    ctx = _runs.get(session_id)
    if ctx is None:
        return False
    ctx.aborted = True
    ctx.abort.set()
    return True
