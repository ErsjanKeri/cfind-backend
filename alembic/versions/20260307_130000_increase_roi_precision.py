"""increase roi column precision from 5,2 to 10,2

Revision ID: b4c2d1e5f6a7
Revises: a3b1c9d2e4f5
Create Date: 2026-03-07 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'b4c2d1e5f6a7'
down_revision = 'a3b1c9d2e4f5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        'listings', 'roi',
        type_=sa.Numeric(precision=10, scale=2),
        existing_type=sa.Numeric(precision=5, scale=2),
        existing_nullable=True
    )


def downgrade() -> None:
    op.alter_column(
        'listings', 'roi',
        type_=sa.Numeric(precision=5, scale=2),
        existing_type=sa.Numeric(precision=10, scale=2),
        existing_nullable=True
    )
