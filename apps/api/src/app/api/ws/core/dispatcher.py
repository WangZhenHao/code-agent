"""把一帧原始文本变成一帧应答（或不回）。

职责边界：**只做 JSON-RPC 语义**，不碰 WebSocket 对象、不碰 Redis、不碰 DB。
这样分发逻辑可以纯单测，不用起 FastAPI。

错误处理原则：
- 能定位到请求的（有 id）就带 id 回错误，客户端能对上号；
- 定位不到的（解析失败、非对象、数组）按规范回 id=null；
- handler 抛的未知异常一律 INTERNAL_ERROR，原文只进日志不进响应——异常消息里
  可能带 SQL、连接串、内部路径。
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from app.api.ws import schemas
from app.api.ws.core.registry import get_method

if TYPE_CHECKING:  # 仅类型用途，避免 connection ↔ dispatcher 的运行时循环
    from app.api.ws.core.connection import ConnectionContext

logger = logging.getLogger(__name__)


def _valid_id(value: Any) -> int | str | None:
    """只回显合法的 id。`true` 虽然能塞进 JSON，但规范里 id 只能是数字或字符串。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, str)):
        return value
    return None


async def dispatch(raw: str, ctx: ConnectionContext) -> str | None:
    """处理一帧文本。返回要发回去的文本；通知返回 None。"""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return schemas.dumps(
            schemas.error_response(None, schemas.PARSE_ERROR, "JSON 解析失败")
        )

    if not isinstance(payload, dict):
        # 批量请求（数组）也落在这里。当前前端只发单条，而批量的语义（逐条回、
        # 数组结果、和推送交错的顺序）是这类实现最容易烂的地方，先明确拒绝；
        # 以后真要支持，就是在这个分支里对每个元素递归调 dispatch。
        message = (
            schemas.BATCH_UNSUPPORTED
            if isinstance(payload, list)
            else "请求必须是 JSON 对象"
        )
        return schemas.dumps(
            schemas.error_response(None, schemas.INVALID_REQUEST, message)
        )

    # 通知判定看原始 dict 有没有 id 键，不看值（见 schemas 模块 docstring）。
    is_notification = "id" not in payload
    id_ = _valid_id(payload.get("id"))

    try:
        req = schemas.JsonRpcRequest.model_validate(payload)
    except ValidationError as exc:
        data = json.loads(exc.json())
        return schemas.dumps(
            schemas.error_response(id_, schemas.INVALID_REQUEST, "请求格式不合法", data)
        )

    text = await _invoke(req, ctx)
    return None if is_notification else text


async def _invoke(req: schemas.JsonRpcRequest, ctx: ConnectionContext) -> str:
    """查表 → 校验参数 → 调 handler，任何失败都转成错误信封。"""
    spec = get_method(req.method)
    if spec is None:
        return schemas.dumps(
            schemas.error_response(
                req.id, schemas.METHOD_NOT_FOUND, f"未知方法: {req.method}"
            )
        )

    if isinstance(req.params, list):
        # 模型上 params 已经是 dict | None，走不到这里；留作契约守卫。
        return schemas.dumps(
            schemas.error_response(
                req.id,
                schemas.INVALID_PARAMS,
                "不支持位置参数",
                {"reason": "params 必须是对象"},
            )
        )

    try:
        if spec.params_model is None:
            params: Any = req.params or {}
        else:
            params = spec.params_model.model_validate(req.params or {})
    except ValidationError as exc:
        # exc.json() 而不是 exc.errors()：后者可能带 ctx 里的异常实例，
        # 不保证能 JSON 序列化。
        return schemas.dumps(
            schemas.error_response(
                req.id, schemas.INVALID_PARAMS, "参数错误", json.loads(exc.json())
            )
        )

    try:
        result = await spec.handler(ctx, params)
    except schemas.JsonRpcError as exc:
        return schemas.dumps(
            schemas.error_response(req.id, exc.code, exc.message, exc.data)
        )
    except Exception:
        logger.exception("JSON-RPC 方法执行失败 method=%s", req.method)
        return schemas.dumps(
            schemas.error_response(req.id, schemas.INTERNAL_ERROR, "服务器内部错误")
        )

    # 结果统一成 JSON 原生类型：datetime / StrEnum / BaseModel 都在这里落地，
    # 免得每个 handler 自己记着 model_dump。
    if hasattr(result, "model_dump"):
        result = result.model_dump(mode="json")
    return schemas.dumps(schemas.response(req.id, result))
