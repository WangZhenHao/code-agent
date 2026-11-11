"""Agent 中止功能模块。

提供取消正在运行的 agent 任务的相关功能，包括：
- 注册和管理运行中的 agent 上下文
- 发送中止信号
- 处理流式消息的累积和收尾
"""

from .abort_handler import abort_update, cancel_all, run_agent_with_abort
from .message_buffer import accumulate, finalize_partial
from .run_registry import RunContext, get, register, signal_abort, unregister

__all__ = [
    # 中止处理
    "cancel_all",
    "run_agent_with_abort",
    "abort_update",
    # Run 注册表
    "register",
    "get",
    "unregister",
    "signal_abort",
    "RunContext",
    # 消息缓冲
    "accumulate",
    "finalize_partial",
]
