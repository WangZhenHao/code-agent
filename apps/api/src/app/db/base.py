"""SQLAlchemy 声明式基类与公共 Mixin。

Alembic autogenerate 靠 Base.metadata 做 diff，所以**所有表模型都必须
间接继承这里的 Base**，否则迁移里看不到那张表。
"""

from datetime import datetime

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# 约束命名约定：不写的话索引/约束会由 Postgres 自动起名（如 users_email_key），
# 同一份模型在不同机器上可能拿到不同的名字，autogenerate 就会反复产生
# 无意义的重命名 diff。约定死命名后迁移文件才是可复现的。
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    """created_at / updated_at 两列。

    用 timestamptz（DateTime(timezone=True)）而非 naive datetime：会话、沙箱
    这些表以后要跨时区对齐，naive 存储是后期最容易返工的地方。

    updated_at 走 onupdate=func.now()，即由 ORM 在 UPDATE 时写入；如果以后有
    绕过 ORM 的批量更新，需要额外挂数据库触发器，这里不做。
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
