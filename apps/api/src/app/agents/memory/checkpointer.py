"""LangGraph 的会话持久化。

会话 ID 即 thread_id，也是沙箱 Pod 名称与标签的来源。
目前返回内存实现，方便本地跑通；生产应换成 AsyncPostgresSaver。
"""

from langgraph.checkpoint.memory import InMemorySaver


def get_checkpointer() -> InMemorySaver:
    return InMemorySaver()
