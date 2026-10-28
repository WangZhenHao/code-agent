"""JSON-RPC 2.0 信封：模型、错误码、构造器。

线格式以 docs/test.md 里抓到的 Coze 帧为准：

    客户端 → 服务端  {"jsonrpc":"2.0","id":6,"method":"preview.status","params":{}}
    服务端 → 客户端  {"jsonrpc":"2.0","id":6,"result":{...}}
    服务端主动推送  {"jsonrpc":"2.0","method":"web.server_status_changed","params":{...}}

**通知（notification）的判定必须看原始 dict 里有没有 "id" 这个键**，不能看
`payload.get("id") is None`：规范里 `"id": null` 是"请回我"（只是 id 取 null），
和"没有 id 所以我不用回"是两回事。模型上两者都是 `id=None`，区分不了，所以
`dispatcher` 是在 `model_validate` 之前判断的。
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field

# ── 错误码 ────────────────────────────────────────────────────────────────
# 前五个是 JSON-RPC 2.0 规范定死的。
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

# -32000..-32099 是规范留给服务端自定义的区间，这里区分两类业务错误：
RESOURCE_NOT_FOUND = (
    -32001
)  # devbox 不存在 / 已删 / 不归你（对齐 HTTP 层「归属错一律 404」）
SERVER_BUSY = -32002  # 单连接并发请求超上限

BATCH_UNSUPPORTED = "不支持批量请求"


class JsonRpcRequest(BaseModel):
    """一条请求。extra 允许：规范要求忽略不认识的成员，不该因此把请求判成非法。"""

    jsonrpc: Literal["2.0"]
    method: str = Field(min_length=1)
    # 只收对象形式的 params。位置参数（数组）在 dispatcher 里显式拒绝并说明原因。
    params: dict[str, Any] | None = None
    # int | str | None：必须原样回显，6 不能变成 "6"。bool 会被 pydantic v2 的
    # smart union 排除在 int 之外，所以 `"id": true` 会校验失败——这是对的。
    id: int | str | None = None


class JsonRpcErrorObject(BaseModel):
    code: int
    message: str
    data: Any | None = None


class JsonRpcError(Exception):
    """handler 抛这个 = 精确控制错误码；其余异常一律 INTERNAL_ERROR。

    为什么不给每个业务错误建一个子类：错误码是线上的契约，调用方只看 code；
    子类层级多一层，收益只是服务端可读性，而 `raise JsonRpcError(RESOURCE_NOT_FOUND, ...)`
    在调用点已经把意图写清楚了。
    """

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


def dumps(envelope: dict[str, Any]) -> str:
    """统一序列化。ensure_ascii=False 让中文原样发出（省带宽、日志可读）；
    紧凑分隔符让一帧尽量短——WS 每帧都过一遍网络。"""
    return json.dumps(envelope, ensure_ascii=False, separators=(",", ":"))


def response(id_: int | str | None, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def error_response(
    id_: int | str | None, code: int, message: str, data: Any = None
) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": id_, "error": error}


def notification(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """服务端主动推送。没有 id 就是通知，按规范客户端不能返回任何东西。"""
    return {"jsonrpc": "2.0", "method": method, "params": params or {}}
