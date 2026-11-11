"""WebSocket / JSON-RPC 层。

刻意不在这里 import 子模块（同 `app/api/__init__.py` 的理由）：`api/__init__`
或本文件一 re-export，任何 `import app.api.ws.schemas` 都会把整棵路由树
（含 LangGraph）拖进来，制造循环 import。调用方直接
`from app.api.ws.router import router`。

方法注册由 `app.api.ws.router` 里唯一一行 `from app.api.ws import methods` 触发。
"""
