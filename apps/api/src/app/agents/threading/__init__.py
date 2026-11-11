"""Agent Streaming Protocol 的线程层：事件协议 + 进程内会话。

对应参考项目 streaming-cookbook 的 `src/app/session.py`：每个线程一个
`ThreadSession`，进程内 buffer + sinks，seq 自增。API 单副本部署，不需要
Redis / Pub-Sub 那套跨副本协调。

导入方式（**写完整子模块路径**：
`from app.agents.threading.thread_session import get_session`。本包的
`__init__` 只做导出、保持轻量，但包名与标准库 `threading` 同名，调用方的
`from threading import ...` 不受影响，因为它走的是标准库的搜索路径）。
"""

from .thread_session import ThreadSession, get_session

__all__ = ["ThreadSession", "get_session"]
