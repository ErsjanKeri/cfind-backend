"""add_countries_and_cities

Revision ID: d589e2e1dbf4
Revises: 20260224_remove_lek
Create Date: 2026-03-07 09:56:32.883015

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'd589e2e1dbf4'
down_revision = '20260224_remove_lek'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('countries',
    sa.Column('code', sa.String(length=2), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.PrimaryKeyConstraint('code')
    )
    op.create_table('cities',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('country_code', sa.String(length=2), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.ForeignKeyConstraint(['country_code'], ['countries.code'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_cities_country_code'), 'cities', ['country_code'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_cities_country_code'), table_name='cities')
    op.drop_table('cities')
    op.drop_table('countries')
