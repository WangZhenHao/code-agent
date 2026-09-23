"""用户表。

字段按产品给的定义落地（Prisma 风格的 `String? @unique` 在这里换成
可空列 + partial unique index），唯一一处改动是 `password` -> `password_hash`：
明文密码不落库，这一列以后只存 bcrypt / argon2 的哈希值。

为什么不用普通 UNIQUE 而用 partial index：Postgres 的 UNIQUE 允许多行 NULL，
所以普通 UNIQUE 也能满足「可空 + 唯一」。写成 `WHERE col IS NOT NULL` 是为了
让迁移文件里一眼看出意图，也避免以后有人误以为 NULL 也算重复。
"""

from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    email: Mapped[str | None] = mapped_column(String(320), default=None)
    phone: Mapped[str | None] = mapped_column(String(32), default=None)
    # 外部身份源的唯一标识（微信 openid / 企业 SSO 的 sub 等），先建列占位
    uid: Mapped[str | None] = mapped_column(String(128), default=None)

    name: Mapped[str | None] = mapped_column(String(128), default=None)
    # 预留：头像 URL、扩展 JSON 文本等，具体格式等前端定了再收窄
    profile: Mapped[str | None] = mapped_column(String(2048), default=None)

    # 只存哈希，绝不存明文；不设默认长度上限以外的约束，哈希长度由算法决定
    password_hash: Mapped[str | None] = mapped_column(String(255), default=None)

    __table_args__ = (
        Index("uq_users_email", "email", unique=True, postgresql_where="email IS NOT NULL"),
        Index("uq_users_phone", "phone", unique=True, postgresql_where="phone IS NOT NULL"),
        Index("uq_users_uid", "uid", unique=True, postgresql_where="uid IS NOT NULL"),
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r}>"
