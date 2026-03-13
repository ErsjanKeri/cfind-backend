"""add neighbourhoods table and unique constraint on cities

Revision ID: f1e2d3c4b5a6
Revises: c5d3e2f1a8b9
Create Date: 2026-03-11 09:50:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'f1e2d3c4b5a6'
down_revision = 'c5d3e2f1a8b9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('neighbourhoods',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('city_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['city_id'], ['cities.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_neighbourhoods_city_id'), 'neighbourhoods', ['city_id'], unique=False)

    op.create_unique_constraint('uq_cities_country_name', 'cities', ['country_code', 'name'])
    op.create_unique_constraint('uq_neighbourhoods_city_name', 'neighbourhoods', ['city_id', 'name'])


def downgrade() -> None:
    op.drop_constraint('uq_neighbourhoods_city_name', 'neighbourhoods', type_='unique')
    op.drop_constraint('uq_cities_country_name', 'cities', type_='unique')
    op.drop_index(op.f('ix_neighbourhoods_city_id'), table_name='neighbourhoods')
    op.drop_table('neighbourhoods')
