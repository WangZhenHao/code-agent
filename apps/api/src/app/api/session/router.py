"""会话管理接口：列表、编辑、删除。

路径沿用 chat 模块的显式动作名风格（/session/list、/session/update/{id}），
和 /chat/create、/chat/detail/{id} 保持一致。三个都是 POST——包括「查询」
性质的 list：项目约定是 POST + JSON body，不分页参数塞 query string。
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.session.schemas import (
    SessionDeleteResponse,
    SessionItem,
    SessionListRequest,
    SessionListResponse,
    SessionUpdateRequest,
)
from app.api.session.service import delete_session, list_sessions, update_session
from app.db.models.user import User
from app.db.session import get_session
from app.security import get_current_user

router = APIRouter(prefix="/session", tags=["session"])


@router.post(
    "/list",
    response_model=SessionListResponse,
    summary="会话列表",
    description=(
        "当前登录用户的会话，**不含已删除**，倒序（最近的在最前）。\n\n"
        "`sort` 决定按哪个时间排：`update_at`（默认，更新时间）"
        "或 `created_at`（创建时间）。\n\n"
        "可选过滤：`keyword` 按标题模糊匹配，`platform` 按平台过滤，"
        "`publish` 按部署状态过滤（1=已部署，0=未部署）。"
    ),
)
async def session_list(
    req: SessionListRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await list_sessions(req, user.id, session)


@router.post(
    "/update/{id}",
    response_model=SessionItem,
    summary="编辑会话",
    description=(
        "只改请求里出现的字段：不传 = 保持原值，传 `null` = 清空"
        "（`title` 是必填列，传 null 会被忽略）。\n\n"
        "可改：`title`、`title_image`、`description`、`publish`、`platform`。"
    ),
    responses={404: {"description": "会话不存在、已删除，或不属于当前用户"}},
)
async def session_update(
    id: str,
    req: SessionUpdateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """编辑会话。路径参数名必须与 `{id}` 逐字一致，否则会退化成查询参数 `?id=`。"""
    return await update_session(id, req, user.id, session)


@router.post(
    "/delete/{id}",
    response_model=SessionDeleteResponse,
    summary="删除会话",
    description=(
        "与会话的其它删除入口语义一致，**不可逆**：销毁会话沙箱、清掉 LangGraph "
        "线程状态，并把 sessions 行置为已删除（软删）。\n\n"
        "幂等：重复删除同一个 id 一律 404。"
    ),
    responses={404: {"description": "会话不存在、已删除，或不属于当前用户"}},
)
async def session_delete(
    id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await delete_session(id, user.id, session)
