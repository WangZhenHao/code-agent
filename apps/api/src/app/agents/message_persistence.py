"""消息持久化模块：负责将对话消息落库。

从 api/agent/service.py 搬过来的：那里本来是这个函数唯一的家，但 finish 节点要用它，
而 finish 是被 node/__init__ 导入的、node 又被 helper/agent_stream 导入、后者又被
api/agent/service 导入——于是 service → helper → node → finish → service 成环，
import 直接失败（和 state.py、message_buffer.py 同一个成因）。

搬到 agents/ 下做成叶子模块：它只依赖 db 层，不依赖任何 agents/api 内部的模块，
谁都能 import 它。**别把它再搬回 service.py**，否则那个环立刻复现。

命名为 message_persistence.py 表明其职责：专注于消息的数据持久化操作。
"""

import logging

from langchain_core.messages import message_to_dict

from app.db.models.session import MessageStatus, Messages, Role
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


async def persist_round(state, status: MessageStatus = MessageStatus.complete):
    """把本轮对话落进 messages 表。

    status 由 finish 节点给：正常跑完是 complete，被 abort 中止的是 interrupted。

    这是 assistant 轮次的**唯一落库路径**，而且它是 recent 才真正跑起来的——finish
    以前是同步节点、调用本函数却没 await，coroutine 建完就丢，所以 messages 表里
    长期只有 user 那一行。改动见 node/finish.py。

    落库 role 是 Role.assistant（见下方构造处），与续跑守卫配套：续跑分支
    （api/agent/service.py 的 _continue_state）要求**最后一条是 user** 才允许续跑，
    所以正常跑完的会话（最后一条 assistant）续跑会 409，只有被中断的轮次能续——
    这正是想要的语义。改这里的 role 会直接影响那个守卫。
    """
    # session_id 在 try **之前**取。原来它在 try 里绑定，于是除了 SessionLocal()
    # 本身失败之外的任何异常（比如 currentRoundMessages 缺 key），except 里引用
    # session_id 都会再抛一个 UnboundLocalError，把真正的错误盖掉。
    session_id = state['session']['id']

    # 用 .get 而不是 []：currentRoundMessages 只有 codeAgent 会写。planAgent 分支
    # （sync 占位节点）永远没有这个 key，取不着就是 KeyError，而异常从节点抛出会让
    # 整轮 run 失败——收尾节点自己把跑完的一轮搞挂，是最不该发生的失败方式。
    round_messages = state.get('currentRoundMessages') or []

    # 一条都没有就不写。空数组在 JSONB 里是合法值但没有意义，前端还要为一个空气泡
    # 多渲染一条；而且中止在第一次模型调用之前正是这种情况。
    if not round_messages:
        return

    try:
        async with SessionLocal() as session:
            parsts = [message_to_dict(msg) for msg in round_messages]
            message = Messages(
                session_id=session_id,
                role=Role.assistant,
                status=status,
                model=state['model'],
                parts=parsts,
                mode=state['mode'],
            )
            session.add(message)
            await session.commit()
    except Exception as exc:
        logger.exception("persist_round 失败 session_id=%s", session_id)
        raise exc
