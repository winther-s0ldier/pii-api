"""Add stat_logs.api_key_id for per-key usage metering

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-25 00:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('stat_logs', sa.Column('api_key_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        'fk_stat_logs_api_key_id', 'stat_logs', 'api_keys',
        ['api_key_id'], ['id'], ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_stat_logs_api_key_id', 'stat_logs', type_='foreignkey')
    op.drop_column('stat_logs', 'api_key_id')
