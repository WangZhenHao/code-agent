"""部署表。

一条记录 = 一个会话产出物的一次上线（K8s Deployment + Service + Ingress 三件套）。
session_id 和 user_id 都标了 ondelete="CASCADE"：会话删了，它的部署跟着走，
否则 K8s 里会留下没人认领的 Ingress。

Prisma 里 name / domain 是 `@unique`，但表上又有 isDeleted 软删。这里按「全表唯一」
实现（照搬 @unique 语义）：软删之后该名字/域名仍然被占用，不能复用。
好处是语义直白、和 Prisma 一致；代价是删除过的名字永久占坑。如果以后发现
「删掉重建同名项目」是常见操作，再改成 partial unique index
（`postgresql_where="is_deleted = false"`）——那是一个独立的迁移。
"""

from enum import StrEnum

from sqlalchemy import ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.db.ids import ID_LENGTH, new_id


class DeploymentStatus(StrEnum):
    """部署生命周期。pending 表示已建记录、还没开始调度。"""

    pending = "pending"
    deploying = "deploying"
    running = "running"
    failed = "failed"
    stopped = "stopped"


class Deployment(Base, TimestampMixin):
    """一次部署。"""

    __tablename__ = "deployments"

    id: Mapped[str] = mapped_column(String(ID_LENGTH), primary_key=True, default=new_id)

    # 253 = DNS 主机名的字段上限（RFC 1035），domain 正好是这个量级；
    # name 是用户自己起的部署名，128 够用。两者都走 Index(unique=True) 而不是
    # UniqueConstraint——和 user.py 里 uq_users_* 的写法保持一致，也让生成的索引名
    # 走 base.py 里 uq_ 的命名约定。
    name: Mapped[str] = mapped_column(String(128))
    domain: Mapped[str] = mapped_column(String(253))

    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    port: Mapped[int] = mapped_column(Integer, default=3000, server_default=text("3000"))
    start_command: Mapped[str] = mapped_column(
        String(512), default="bun run start", server_default="bun run start"
    )
    status: Mapped[str] = mapped_column(
        String(16),
        default=DeploymentStatus.pending,
        server_default=DeploymentStatus.pending.value,
    )

    # K8s 侧资源名，创建成功后回填；255 覆盖 K8s 的 253 上限
    k8s_deployment: Mapped[str | None] = mapped_column(String(255), default=None)
    k8s_service: Mapped[str | None] = mapped_column(String(255), default=None)
    k8s_ingress: Mapped[str | None] = mapped_column(String(255), default=None)

    # Text 而非 String(n)：K8s 的报错信息常常带整个事件列表，长度不可控
    error_message: Mapped[str | None] = mapped_column(Text, default=None)
    git_commit_sha: Mapped[str | None] = mapped_column(String(64), default=None)

    is_deleted: Mapped[bool] = mapped_column(
        default=False, server_default=text("false")
    )

    __table_args__ = (
        Index("uq_deployments_name", "name", unique=True),
        Index("uq_deployments_domain", "domain", unique=True),
        # 「我的部署列表」和「这个会话的部署」两种查法
        Index("ix_deployments_user_id_created_at", "user_id", "created_at"),
        Index("ix_deployments_session_id", "session_id"),
    )

    def __repr__(self) -> str:
        return f"<Deployment id={self.id} name={self.name!r} status={self.status}>"
