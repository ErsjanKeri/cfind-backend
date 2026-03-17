"""Add listing verification (pending/rejected status, rejection reason)

Revision ID: 20260317_listing_verify
Revises: 20260311_095000_add_neighbourhoods
Create Date: 2026-03-17

Changes:
- Add rejection_reason and rejected_at columns to listings
- Convert existing 'draft' statuses to 'pending'
"""

from alembic import op
import sqlalchemy as sa


revision = "20260317_listing_verify"
down_revision = "f1e2d3c4b5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("listings", sa.Column("rejection_reason", sa.String(), nullable=True))
    op.add_column("listings", sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True))

    # Convert any existing 'draft' listings to 'pending'
    op.execute("UPDATE listings SET status = 'pending' WHERE status = 'draft'")


def downgrade() -> None:
    # Convert 'pending' back to 'draft', 'rejected' back to 'inactive'
    op.execute("UPDATE listings SET status = 'draft' WHERE status = 'pending'")
    op.execute("UPDATE listings SET status = 'inactive' WHERE status = 'rejected'")

    op.drop_column("listings", "rejected_at")
    op.drop_column("listings", "rejection_reason")
