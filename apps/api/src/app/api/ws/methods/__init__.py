"""JSON-RPC 方法注册入口。

`router.py` 里那唯一一行 `from app.api.ws import methods` 就是靠 import 本模块、
再 import 下面每个子模块，让它们的 `@rpc_method` 装饰器在 import 期跑一遍。
所以**新加方法文件后必须在这里 import 一次**，否则方法存在但永远 -32601。
"""

from app.api.ws.methods import preview

__all__ = ["preview"]
