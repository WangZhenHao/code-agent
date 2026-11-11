"""JSON-RPC 方法注册表。

名字 → handler 的映射在 **import 期** 建好：`methods/*.py` 里每个 handler 上挂
一个装饰器，`router.py` 里 `from app.api.ws import methods` 触发注册。

为什么重名当场抛错而不是覆盖：重名的表现是「某个方法悄悄返回了另一个方法的结果」，
比启动失败难查得多。import 期抛 RuntimeError，进程直接起不来，问题在部署前就暴露。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

# handler 固定两个位置参数：(ctx, params)。不用 kwargs 是为了让类型检查器
# 能对上；缺参的方法也照样收两个，params 是个空模型。
Handler = Callable[[Any, Any], Awaitable[Any]]


@dataclass(frozen=True, slots=True)
class MethodSpec:
    name: str
    handler: Handler
    # params 的校验模型；None 表示该方法不校验（只有确实「什么参数都收」时才用）
    params_model: type[BaseModel] | None


_METHODS: dict[str, MethodSpec] = {}


def rpc_method(name: str, *, params_model: type[BaseModel] | None = None):
    """登记一个 JSON-RPC 方法。

    **装饰器返回原函数，不包一层 wrapper**：测试里 `mock.patch.object(模块, "x")`
    替换的是模块属性，分发器查注册表拿到的仍是原来那个对象——包 wrapper 的话
    patch 之后注册表里还是旧函数，测试会静默失效。
    """

    def deco(fn: Handler) -> Handler:
        if name in _METHODS:
            raise RuntimeError(f"JSON-RPC 方法重复注册: {name}")
        _METHODS[name] = MethodSpec(name=name, handler=fn, params_model=params_model)
        return fn

    return deco


def get_method(name: str) -> MethodSpec | None:
    return _METHODS.get(name)


def registered() -> dict[str, MethodSpec]:
    """只读快照，给文档/调试用。"""
    return dict(_METHODS)
