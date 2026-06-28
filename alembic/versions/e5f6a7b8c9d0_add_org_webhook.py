"""Add organizations.webhook_url / webhook_secret for BLOCK event webhooks

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-25 00:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('organizations', sa.Column('webhook_url', sa.String(length=500), nullable=True))
    op.add_column('organizations', sa.Column('webhook_secret', sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column('organizations', 'webhook_secret')
    op.drop_column('organizations', 'webhook_url')
