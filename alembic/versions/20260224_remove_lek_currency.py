"""Remove LEK currency fields - EUR only

Revision ID: 20260224_remove_lek
Revises: 20260127_150000
Create Date: 2026-02-24

Changes:
1. Drop asking_price_lek, monthly_revenue_lek from listings table
2. Drop budget_min_lek, budget_max_lek from buyer_demands table
3. Drop price_lek from credit_packages table

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260224_remove_lek'
down_revision = '20260127_150000'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Remove LEK currency columns - simplify to EUR only.
    """

    # =========================================================================
    # STEP 1: Drop LEK columns from listings table
    # =========================================================================
    print("📝 Step 1: Removing LEK columns from listings table...")
    op.drop_column('listings', 'asking_price_lek')
    op.drop_column('listings', 'monthly_revenue_lek')
    print("✅ Listings table updated")

    # =========================================================================
    # STEP 2: Drop LEK columns from buyer_demands table
    # =========================================================================
    print("📝 Step 2: Removing LEK columns from buyer_demands table...")
    op.drop_column('buyer_demands', 'budget_min_lek')
    op.drop_column('buyer_demands', 'budget_max_lek')
    print("✅ Buyer demands table updated")

    # =========================================================================
    # STEP 3: Drop LEK column from credit_packages table
    # =========================================================================
    print("📝 Step 3: Removing LEK column from credit_packages table...")
    op.drop_column('credit_packages', 'price_lek')
    print("✅ Credit packages table updated")

    print("🎉 Migration complete - EUR only!")


def downgrade() -> None:
    """
    Restore LEK currency columns (if needed to rollback).

    Note: Data will be lost - LEK values cannot be recovered.
    """

    # =========================================================================
    # STEP 1: Restore LEK columns to credit_packages
    # =========================================================================
    print("📝 Restoring LEK column to credit_packages...")
    op.add_column('credit_packages',
        sa.Column('price_lek', sa.Numeric(precision=12, scale=2), nullable=True))
    print("✅ Credit packages restored")

    # =========================================================================
    # STEP 2: Restore LEK columns to buyer_demands
    # =========================================================================
    print("📝 Restoring LEK columns to buyer_demands...")
    op.add_column('buyer_demands',
        sa.Column('budget_min_lek', sa.Numeric(precision=15, scale=2), nullable=True))
    op.add_column('buyer_demands',
        sa.Column('budget_max_lek', sa.Numeric(precision=15, scale=2), nullable=True))
    print("✅ Buyer demands restored")

    # =========================================================================
    # STEP 3: Restore LEK columns to listings
    # =========================================================================
    print("📝 Restoring LEK columns to listings...")
    op.add_column('listings',
        sa.Column('asking_price_lek', sa.Numeric(precision=15, scale=2), nullable=True))
    op.add_column('listings',
        sa.Column('monthly_revenue_lek', sa.Numeric(precision=15, scale=2), nullable=True))
    print("✅ Listings restored")

    print("⚠️  Warning: LEK data was not preserved - columns restored as NULL")
