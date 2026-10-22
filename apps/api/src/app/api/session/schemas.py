"""会话管理接口的请求/响应模型。

与 app/api/chat/schemas.py 的分工：那边是「跑对话」的接口（创建、消息、详情），
这边是会话本身的**管理**动作（列表、编辑、删除）。两边都有 Session 的字段
视图，但 `ChatDetailResponse` 是给单个会话详情用的窄视图，列表页要的是分页
+ 轻量字段，所以这里另起 `SessionItem`，不硬套一个模型。
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.session import Platform, PublicStatus


class SessionSort(StrEnum):
    """列表排序字段。都是倒序（最近的在前）。

    注意取值是 `update_at` 而不是列名 `updated_at`——沿用接口约定的拼写，
    与数据库列名的对应关系在 service 层做一次映射。
    """

    update_at = "update_at"
    created_at = "created_at"


class SessionListRequest(BaseModel):
    page: int = Field(default=1, ge=1, description="页码，从 1 开始", examples=[1])
    page_size: int = Field(
        default=20, ge=1, le=100, description="每页条数，上限 100", examples=[20]
    )
    keyword: str | None = Field(
        default=None,
        max_length=255,
        description="按标题模糊搜索（ILIKE），不传则不过滤",
        examples=["快排"],
    )
    platform: Platform | None = Field(
        default=None, description="按平台过滤，不传则全平台", examples=["web"]
    )
    publish: PublicStatus | None = Field(
        default=None,
        description="按部署状态过滤：1=已部署，0=未部署，不传则两者都返回",
        examples=[1],
    )
    sort: SessionSort = Field(
        default=SessionSort.update_at,
        description="排序字段，均为倒序：`update_at`=按更新时间，`created_at`=按创建时间",
        examples=["update_at", "created_at"],
    )


class SessionItem(BaseModel):
    """列表/编辑响应里的一个会话。

    status 是整数状态码，见 app.db.models.session.SessionStatus：
    0=已删除，1=进行中。
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(examples=["e9394c054c9641e8981ca78b99b70dde"])
    title: str = Field(examples=["帮我写个快排"])
    title_image: str | None = Field(default=None, description="封面图 URL")
    description: str | None = Field(default=None, description="会话描述")

    status: int = Field(examples=[1])
    publish: int = Field(default=0, description="部署状态：0=未部署，1=已部署")
    views: int = Field(default=0, description="浏览量")

    preview_status: str = Field(default="idle", examples=["idle"])
    preview_url: str | None = Field(default=None)

    platform: str = Field(default="web", examples=["web"])

    git_repo_name: str | None = Field(default=None)
    git_repo_url: str | None = Field(default=None)

    created_at: datetime
    updated_at: datetime


class SessionListResponse(BaseModel):
    data: list[SessionItem]
    total: int = Field(description="符合过滤条件的会话总数（不含已删除）", examples=[42])
    page: int = Field(examples=[1])
    page_size: int = Field(examples=[20])


class SessionUpdateRequest(BaseModel):
    """编辑会话。**只改传了的字段**——没传的保持原值，不是整体覆盖。

    注意 null 与「没传」的区别：`{"title_image": null}` 表示显式清空封面，
    不传 title_image 表示不动它。service 层用 `exclude_unset=True` 区分。
    """

    title: str | None = Field(
        default=None, min_length=1, max_length=255, description="会话标题"
    )
    title_image: str | None = Field(
        default=None, max_length=2048, description="封面图 URL，传 null 清空"
    )
    description: str | None = Field(default=None, description="会话描述，传 null 清空")
    publish: PublicStatus | None = Field(
        default=None, description="部署状态：0=未部署，1=已部署"
    )
    platform: Platform | None = Field(
        default=None, description="平台", examples=["web", "mini_program"]
    )


class SessionDeleteResponse(BaseModel):
    """删除会话的响应。

    带 status 而不是空响应：前端拿到就能直接更新本地那条记录（标灰/移出列表），
    不必再拉一次列表或详情。值恒为 SessionStatus.delete（0）。
    """

    id: str = Field(examples=["e9394c054c9641e8981ca78b99b70dde"])
    # 会话状态码，见 app.db.models.session.SessionStatus：0=已删除，1=进行中
    status: int = Field(examples=[0])
