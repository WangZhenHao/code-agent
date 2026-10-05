"""add mode column to messages

模型 app/db/models/session.py 里 Messages 有 `model` 和 `mode` 两列，但建表迁移
782c9e69b5d7 只建了 `model`——`mode` 一直没落 DDL，于是 ORM 的 INSERT 带上 mode
时数据库报 `column "mode" of relation "messages" does not exist`。这里补上。

mode 与 model 对齐：String(16)、非空。写这段时 messages 表为空，直接加到 NOT NULL
不会撞存量行；service 层建消息时本就传了 mode，也不依赖这个列的默认值。

Revision ID: 9b2e5c7f1a3d
Revises: c3f1a9d4e7b2
Create Date: 2026-10-05 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9b2e5c7f1a3d'
down_revision: Union[str, Sequence[str], None] = 'c3f1a9d4e7b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('messages', sa.Column('mode', sa.String(length=16), nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('messages', 'mode')
