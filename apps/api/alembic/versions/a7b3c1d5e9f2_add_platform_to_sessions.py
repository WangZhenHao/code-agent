"""add platform to sessions

模型 app/db/models/session.py 里 Session 新增 platform 列，区分会话来自 web
还是小程序。非空列，server_default='web' 让存量行直接回填成 web，不需要单独的
UPDATE 语句——现有会话本来就是 web 端产生的。

Revision ID: a7b3c1d5e9f2
Revises: f4a1b2c3d4e5
Create Date: 2026-10-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7b3c1d5e9f2'
down_revision: Union[str, Sequence[str], None] = 'f4a1b2c3d4e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'sessions',
        sa.Column(
            'platform',
            sa.String(length=16),
            nullable=False,
            server_default='web',
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('sessions', 'platform')
