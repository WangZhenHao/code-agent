"""WS 层的可调参数。

**为什么不放进 app/settings.py**：那一层是全服务的配置台，加一个只服务于
单个子系统的字段会把 `settings` 变成杂物间。这里改用
`CODE_AGENT_WS_<NAME>` 环境变量覆盖——`Settings` 配了 `extra="ignore"` 但
字段也留着，所以有 env 就用 env，没有就用下面的默认值，settings.py 一行不用改。
"""

from __future__ import annotations

from app.settings import settings

# 应用层心跳间隔（秒）。LB / nginx 的空闲超时往往比想象中短（ALB 默认 60s），
# 靠 uvicorn 协议层 ping 不够——有些代理只认数据帧。25s 是给 60s 留一半余量。
HEARTBEAT_SECONDS: int = getattr(settings, "ws_heartbeat_seconds", 25)

# 单条消息上限（字节）。这是应用层的第二道闸：uvicorn 的 --ws-max-size 默认
# 16 MiB，且在应用看到消息之前就把它读进内存了，部署命令上要一起调小。
MAX_MESSAGE_BYTES: int = getattr(settings, "ws_max_message_bytes", 262_144)

# 每个连接的出站队列长度。应答走阻塞 put（背压传给请求任务），通知走
# put_nowait（满了丢弃）——所以这个值只决定「读得慢的客户端能排多少条应答」。
SEND_QUEUE_SIZE: int = getattr(settings, "ws_send_queue_size", 128)

# 单连接同时在处理的最大请求数。超了直接回 -32002（忙），避免一个客户端
# 连发把任务表打爆。
MAX_INFLIGHT: int = getattr(settings, "ws_max_inflight", 32)
