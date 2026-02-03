"""Simplify user profiles - merge common fields into User table

Revision ID: 20260127_150000
Revises: 0d399bab58f6
Create Date: 2026-01-27 15:00:00

Changes:
1. Add phone_number, company_name, website to users table
2. Copy agency_name from agent_profiles to users.company_name
3. Copy phone_number from agent_profiles to users.phone_number
4. Copy company_name from buyer_profiles to users.company_name
5. Remove agency_name column from agent_profiles
6. Drop buyer_profiles table entirely

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260127_150000'
down_revision = '0d399bab58f6'  # Points to initial_schema_all_models
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Upgrade database schema.

    Step-by-step to avoid data loss.
    """

    # =========================================================================
    # STEP 1: Add new columns to users table (nullable first, to allow existing rows)
    # =========================================================================
    print("📝 Step 1: Adding new columns to users table...")
    op.add_column('users', sa.Column('phone_number', sa.String(), nullable=True))
    op.add_column('users', sa.Column('company_name', sa.String(), nullable=True))
    op.add_column('users', sa.Column('website', sa.String(), nullable=True))
    print("✅ Columns added")

    # =========================================================================
    # STEP 2: Copy data from agent_profiles.phone_number → users.phone_number
    # =========================================================================
    print("📝 Step 2: Copying agent phone numbers to users table...")
    op.execute("""
        UPDATE users
        SET phone_number = agent_profiles.phone_number
        FROM agent_profiles
        WHERE users.id = agent_profiles.user_id
        AND agent_profiles.phone_number IS NOT NULL
    """)
    print("✅ Agent phone numbers copied")

    # =========================================================================
    # STEP 3: Copy agency_name → users.company_name (for agents)
    # =========================================================================
    print("📝 Step 3: Copying agency names to users.company_name...")
    op.execute("""
        UPDATE users
        SET company_name = agent_profiles.agency_name
        FROM agent_profiles
        WHERE users.id = agent_profiles.user_id
        AND agent_profiles.agency_name IS NOT NULL
    """)
    print("✅ Agency names copied to company_name")

    # =========================================================================
    # STEP 4: Copy buyer_profiles.company_name → users.company_name (for buyers)
    # =========================================================================
    print("📝 Step 4: Copying buyer company names to users table...")
    op.execute("""
        UPDATE users
        SET company_name = buyer_profiles.company_name
        FROM buyer_profiles
        WHERE users.id = buyer_profiles.user_id
        AND buyer_profiles.company_name IS NOT NULL
    """)
    print("✅ Buyer company names copied")

    # =========================================================================
    # STEP 5: Remove agency_name from agent_profiles (now redundant)
    # =========================================================================
    print("📝 Step 5: Removing agency_name column from agent_profiles...")
    op.drop_column('agent_profiles', 'agency_name')
    print("✅ agency_name column dropped")

    # =========================================================================
    # STEP 6: Drop buyer_profiles table entirely (all data migrated)
    # =========================================================================
    print("📝 Step 6: Dropping buyer_profiles table...")
    op.drop_table('buyer_profiles')
    print("✅ buyer_profiles table dropped")

    print("\n🎉 Migration complete!")
    print("   - User table now has: phone_number, company_name, website")
    print("   - AgentProfile.agency_name removed (use User.company_name)")
    print("   - BuyerProfile table deleted")


def downgrade() -> None:
    """
    Downgrade database schema (rollback changes).

    Recreates the old structure.
    """

    print("⚠️  Rolling back migration...")

    # Recreate buyer_profiles table
    op.create_table('buyer_profiles',
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('company_name', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id')
    )

    # Add agency_name back to agent_profiles
    op.add_column('agent_profiles', sa.Column('agency_name', sa.String(), nullable=True))

    # Copy company_name back to agency_name for agents
    op.execute("""
        UPDATE agent_profiles
        SET agency_name = users.company_name
        FROM users
        WHERE agent_profiles.user_id = users.id
        AND users.role = 'agent'
    """)

    # Copy company_name back to buyer_profiles for buyers
    op.execute("""
        INSERT INTO buyer_profiles (user_id, company_name)
        SELECT id, company_name
        FROM users
        WHERE role = 'buyer'
    """)

    # Copy phone_number back to agent_profiles
    op.execute("""
        UPDATE agent_profiles
        SET phone_number = users.phone_number
        FROM users
        WHERE agent_profiles.user_id = users.id
    """)

    # Remove columns from users
    op.drop_column('users', 'website')
    op.drop_column('users', 'company_name')
    op.drop_column('users', 'phone_number')

    print("✅ Rollback complete")
