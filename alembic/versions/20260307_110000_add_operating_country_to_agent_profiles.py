"""add operating_country to agent_profiles

Revision ID: a3b1c9d2e4f5
Revises: e717bc3425c2
Create Date: 2026-03-07 11:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a3b1c9d2e4f5'
down_revision = 'e717bc3425c2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add column as nullable first
    op.add_column('agent_profiles', sa.Column('operating_country', sa.String(length=2), nullable=True))

    # Backfill existing agents with "al"
    op.execute("UPDATE agent_profiles SET operating_country = 'al' WHERE operating_country IS NULL")

    # Add foreign key to countries table
    op.create_foreign_key(
        'fk_agent_profiles_operating_country',
        'agent_profiles', 'countries',
        ['operating_country'], ['code']
    )


def downgrade() -> None:
    op.drop_constraint('fk_agent_profiles_operating_country', 'agent_profiles', type_='foreignkey')
    op.drop_column('agent_profiles', 'operating_country')
