"""Agent Streaming Protocol 的线程层：事件协议、Redis 事件总线、run 会话。

对应参考项目 streaming-cookbook 的 `src/app/session.py`，区别只在状态载体：
那边是进程内 dict，这里是 Redis（Stream 回放 + Pub/Sub 增量），checkpoint
仍走本仓库已有的 Postgres saver。

导入方式（**写完整子模块路径**：
`from app.agents.threading.thread_session import ThreadSession`。本包的
`__init__` 只做导出、保持轻量，但包名与标准库 `threading` 同名，调用方的
`from threading import ...` 不受影响，因为它走的是标准库的搜索路径）。
"""

from .thread_session import ThreadSession

__all__ = ["ThreadSession"]
