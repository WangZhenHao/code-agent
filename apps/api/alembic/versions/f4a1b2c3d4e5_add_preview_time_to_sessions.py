"""add preview_time to sessions

模型 app/db/models/session.py 里 Session 新增 preview_time 列，记录沙箱本次启动
的时刻；停止沙箱时清空为 NULL（与 preview_status 复位 idle 同步）。

可空、无 server_default：NULL 就是「当前没有在跑的沙箱」，是合法状态，存量行
留空即可，不需要回填。

Revision ID: f4a1b2c3d4e5
Revises: 9b2e5c7f1a3d
Create Date: 2026-10-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f4a1b2c3d4e5'
down_revision: Union[str, Sequence[str], None] = '9b2e5c7f1a3d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'sessions',
        sa.Column('preview_time', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('sessions', 'preview_time')
