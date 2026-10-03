"""replace is_deleted columns with status codes

会话/消息/部署三张表去掉 is_deleted 软删列，删除语义统一由 status 表达。
其中 sessions.status 的码值同时重排：0=已删除、1=进行中（旧值是 0=进行中），
所以存量行要把 0 改成 1，否则现存会话会被读成「已删除」。

Revision ID: c3f1a9d4e7b2
Revises: 70082553c125
Create Date: 2026-10-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3f1a9d4e7b2'
down_revision: Union[str, Sequence[str], None] = '70082553c125'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # sessions：先重排码值再收掉 is_deleted。
    # 旧 0=进行中、1=已完成、2=失败 -> 新 0=已删除、1=进行中。
    # 已软删的行本来就该是「已删除」，但旧码值里没有对应值——它们此前 is_deleted=true，
    # 这里先按 is_deleted 把已删行钉成 0，再把剩下的活动行 0->1。
    op.execute("UPDATE sessions SET status = 0 WHERE is_deleted = true")
    op.execute("UPDATE sessions SET status = 1 WHERE status = 0")
    op.alter_column('sessions', 'status', server_default=sa.text('1'))
    op.drop_index('ix_sessions_user_id_is_deleted', table_name='sessions')
    op.drop_column('sessions', 'is_deleted')

    op.drop_column('messages', 'is_deleted')
    op.drop_column('deployments', 'is_deleted')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        'deployments',
        sa.Column('is_deleted', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    )
    op.add_column(
        'messages',
        sa.Column('is_deleted', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    )
    op.add_column(
        'sessions',
        sa.Column('is_deleted', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    )
    # 新 0=已删除 还原成旧的 is_deleted=true + status=0（旧 0=进行中）。
    op.execute("UPDATE sessions SET is_deleted = true WHERE status = 0")
    op.execute("UPDATE sessions SET status = 0")
    op.alter_column('sessions', 'status', server_default=sa.text('0'))
    op.create_index('ix_sessions_user_id_is_deleted', 'sessions', ['user_id', 'is_deleted'], unique=False)
