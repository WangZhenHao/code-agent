"""WS 层的业务逻辑：devbox 归属校验、预览对象映射。

和 HTTP 层的 service 同构：不 import FastAPI 类型，错误用领域异常/符号表达，
由 router 翻译成关闭码或 JSON-RPC 错误码。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.api.ws.core.auth import CLOSE_NOT_FOUND, WsAuthError
from app.db.models.session import PreviewStatus, Session, SessionStatus
from app.db.session import SessionLocal


async def resolve_devbox(devbox_id: str, user_id: int) -> Session:
    """确认会话存在、未删除、且归当前用户。

    三种失败共用 4404（对齐 HTTP 层「归属错一律 404」）：区分开等于告诉攻击者
    「这个 id 存在，只是不是你的」。
    """
    async with SessionLocal() as session:
        row = await session.scalar(
            select(Session).where(
                Session.id == devbox_id,
                Session.user_id == user_id,
                Session.status != SessionStatus.delete,
            )
        )
    if row is None:
        raise WsAuthError(CLOSE_NOT_FOUND, "devbox 不存在")
    return row


def preview_params(row: Session) -> dict[str, Any]:
    """Session 行 → 预览对象。

    只输出**有数据来源**的字段（sessions 表的 preview_status / preview_url）。
    其余键名保留但值为 None：它们对应的能力本地还没有，具体值待定，这里不填占位
    ——假值（比如凭空报一个 running_previews=1）比缺字段更容易误导前端。
    """
    status = row.preview_status or PreviewStatus.idle.value
    return {
        "status": status,
        "preview_url": row.preview_url,
        # 由 status 推导，不是独立数据：running 才算开了预览
        "preview_enabled": status == PreviewStatus.running.value,
        # --- 值待定：键名先留着，避免前端将来要改解析结构 ---
        "worktree_name": None,
        "branch": None,
        "running_previews": None,
        "max_previews": None,
        "sub_id": None,
        "project_type": None,
    }
