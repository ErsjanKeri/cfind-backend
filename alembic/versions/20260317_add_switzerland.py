"""Add Switzerland country and major cities

Revision ID: 20260317_switzerland
Revises: 20260317_listing_verify
Create Date: 2026-03-17

Changes:
- Add Switzerland (ch) to countries table
- Add major Swiss cities
"""

from alembic import op
import sqlalchemy as sa


revision = "20260317_switzerland"
down_revision = "20260317_listing_verify"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add Switzerland
    op.execute(
        "INSERT INTO countries (code, name) VALUES ('ch', 'Switzerland') ON CONFLICT (code) DO NOTHING"
    )

    # Add major Swiss cities
    # Get Switzerland's code for FK reference
    cities = [
        "Zurich",
        "Geneva",
        "Basel",
        "Bern",
        "Lausanne",
        "Winterthur",
        "Lucerne",
        "St. Gallen",
        "Lugano",
        "Zug",
    ]

    for city in cities:
        op.execute(
            f"INSERT INTO cities (country_code, name) VALUES ('ch', '{city}') ON CONFLICT DO NOTHING"
        )


def downgrade() -> None:
    op.execute("DELETE FROM cities WHERE country_code = 'ch'")
    op.execute("DELETE FROM countries WHERE code = 'ch'")
