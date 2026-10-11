"""HTTP 接口层：按领域分子包，每个子包一个 router。

**刻意不在这里 re-export api_router**（不要加 `from app.api.router import api_router`）：
那行会让「导入本包下任何子模块」都等于「导入整棵路由树」。而 agents 层只想要
app.api.chat.schemas 里的一个类型，一 import 就会触发本 __init__，把 router →
agent.router → agent.service → agents.helper → agents.graphs 全拖起来，
和 graphs → node → node/state 的加载链撞成循环导入（ImportError: partially
initialized module）。所以调用方直接 `from app.api.router import api_router`。
"""
