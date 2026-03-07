"""add_country_code_to_listings_users_demands

Revision ID: e717bc3425c2
Revises: d589e2e1dbf4
Create Date: 2026-03-07 10:02:09.617992

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'e717bc3425c2'
down_revision = 'd589e2e1dbf4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add columns as nullable first
    op.add_column('listings', sa.Column('country_code', sa.String(length=2), nullable=True))
    op.add_column('buyer_demands', sa.Column('country_code', sa.String(length=2), nullable=True))
    op.add_column('users', sa.Column('country_preference', sa.String(length=2), nullable=True))

    # Backfill existing rows with "al"
    op.execute("UPDATE listings SET country_code = 'al' WHERE country_code IS NULL")
    op.execute("UPDATE buyer_demands SET country_code = 'al' WHERE country_code IS NULL")

    # Now set not-null constraint
    op.alter_column('listings', 'country_code', nullable=False)
    op.alter_column('buyer_demands', 'country_code', nullable=False)

    # Add indexes and foreign keys
    op.create_index(op.f('ix_listings_country_code'), 'listings', ['country_code'], unique=False)
    op.create_foreign_key('fk_listings_country_code', 'listings', 'countries', ['country_code'], ['code'])
    op.create_index(op.f('ix_buyer_demands_country_code'), 'buyer_demands', ['country_code'], unique=False)
    op.create_foreign_key('fk_buyer_demands_country_code', 'buyer_demands', 'countries', ['country_code'], ['code'])
    op.create_foreign_key('fk_users_country_preference', 'users', 'countries', ['country_preference'], ['code'])


def downgrade() -> None:
    op.drop_constraint('fk_users_country_preference', 'users', type_='foreignkey')
    op.drop_column('users', 'country_preference')
    op.drop_constraint('fk_listings_country_code', 'listings', type_='foreignkey')
    op.drop_index(op.f('ix_listings_country_code'), table_name='listings')
    op.drop_column('listings', 'country_code')
    op.drop_constraint('fk_buyer_demands_country_code', 'buyer_demands', type_='foreignkey')
    op.drop_index(op.f('ix_buyer_demands_country_code'), table_name='buyer_demands')
    op.drop_column('buyer_demands', 'country_code')
