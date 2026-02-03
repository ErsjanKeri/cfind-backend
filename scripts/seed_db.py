"""
Database seeding script for CompanyFinder Albania FastAPI Backend.

Seeds:
- Admin user (master admin)
- 2 verified agents with profiles
- 1 buyer with profile
- 2 sample listings
- Credit packages (5 tiers)
- Promotion tier configs (Featured & Premium)

Matches frontend seed.ts data exactly for consistency.
"""

import asyncio
import sys
import os
from datetime import datetime, timezone
from decimal import Decimal

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import delete
from app.db.session import AsyncSessionLocal
import uuid

# Import ALL models for SQLAlchemy relationship resolution
from app.models.user import User, AgentProfile  # BuyerProfile removed!
from app.models.token import EmailVerificationToken, PasswordResetToken, RefreshToken
from app.models.listing import Listing, ListingImage
from app.models.lead import Lead, SavedListing
from app.models.demand import BuyerDemand
from app.models.promotion import CreditTransaction, PromotionHistory, CreditPackage, PromotionTierConfig

from app.core.security import hash_password


# ============================================================================
# PREDEFINED UUIDs (for consistent seeding)
# ============================================================================
ADMIN_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
AGENT_1_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
AGENT_2_ID = uuid.UUID("00000000-0000-0000-0000-000000000003")
BUYER_1_ID = uuid.UUID("00000000-0000-0000-0000-000000000004")
LISTING_1_ID = uuid.UUID("00000000-0000-0000-0000-000000000101")
LISTING_2_ID = uuid.UUID("00000000-0000-0000-0000-000000000102")


async def clean_database():
    """Clean up existing data before seeding."""
    print("🧹 Cleaning existing data...")

    async with AsyncSessionLocal() as db:
        # Delete in correct order (respecting foreign keys)
        await db.execute(delete(ListingImage))
        await db.execute(delete(Listing))
        await db.execute(delete(CreditPackage))
        await db.execute(delete(PromotionTierConfig))
        await db.execute(delete(AgentProfile))
        # BuyerProfile table removed - no longer exists
        await db.execute(delete(User))

        await db.commit()

    print("✅ Database cleaned\n")


async def seed_admin():
    """Seed master admin user."""
    print("👑 Seeding Admin...")

    async with AsyncSessionLocal() as db:
        # Admin password (matches frontend)
        admin_password = hash_password("570139281209847")

        admin = User(
            id=ADMIN_ID,
            email="admin@cfind.ai",
            name="Master Admin",
            role="admin",
            password=admin_password,
            email_verified=True,
            created_at=datetime.now(timezone.utc)
        )

        db.add(admin)
        await db.commit()

    print("✅ Admin created: admin@cfind.ai / 570139281209847\n")


async def seed_agents():
    """Seed verified agents with profiles."""
    print("👨‍💼 Seeding Agents...")

    async with AsyncSessionLocal() as db:
        # Agent 1: Arben Hoxha
        agent1_password = hash_password("Agent123!")

        agent1 = User(
            id=AGENT_1_ID,
            email="arben.hoxha@realestate.al",
            name="Arben Hoxha",
            role="agent",
            password=agent1_password,
            email_verified=True,
            # Common fields now in User table
            phone_number="+355691234567",
            company_name="Tirana Business Brokers",  # Moved from agency_name!
            website="https://tiranabiz.al",
            created_at=datetime.now(timezone.utc)
        )
        db.add(agent1)

        agent1_profile = AgentProfile(
            user_id=AGENT_1_ID,
            # agency_name REMOVED - using User.company_name
            # phone_number REMOVED - using User.phone_number
            license_number="AL-BRK-2024-001",
            bio_en="Over 15 years of experience in business acquisitions across Albania.",
            whatsapp_number="+355691234567",
            license_document_url="https://example.com/docs/agent1-license.pdf",
            company_document_url="https://example.com/docs/agent1-company.pdf",
            id_document_url="https://example.com/docs/agent1-id.pdf",
            verification_status="approved",
            verified_at=datetime.now(timezone.utc),
            listings_count=12,
            deals_completed=45,
            credit_balance=50  # Starting credits for demo
        )
        db.add(agent1_profile)

        # Agent 2: Elena Koci
        agent2_password = hash_password("Agent123!")

        agent2 = User(
            id=AGENT_2_ID,
            email="elena.koci@brokers.al",
            name="Elena Koci",
            role="agent",
            password=agent2_password,
            email_verified=True,
            # Common fields now in User table
            phone_number="+355699876543",
            company_name="Premium Business Sales",  # Moved from agency_name!
            website="https://premiumbiz.al",
            created_at=datetime.now(timezone.utc)
        )
        db.add(agent2)

        agent2_profile = AgentProfile(
            user_id=AGENT_2_ID,
            # agency_name REMOVED - using User.company_name
            # phone_number REMOVED - using User.phone_number
            license_number="AL-BRK-2024-002",
            bio_en="Expert in technology and service-based business transactions.",
            whatsapp_number="+355699876543",
            license_document_url="https://example.com/docs/agent2-license.pdf",
            company_document_url="https://example.com/docs/agent2-company.pdf",
            id_document_url="https://example.com/docs/agent2-id.pdf",
            verification_status="approved",
            verified_at=datetime.now(timezone.utc),
            listings_count=8,
            deals_completed=28,
            credit_balance=25
        )
        db.add(agent2_profile)

        await db.commit()

    print("✅ Agent 1: arben.hoxha@realestate.al / Agent123!")
    print("✅ Agent 2: elena.koci@brokers.al / Agent123!\n")


async def seed_buyers():
    """Seed buyer with profile."""
    print("🛒 Seeding Buyers...")

    async with AsyncSessionLocal() as db:
        # Buyer 1: Marco Rossi
        buyer1_password = hash_password("Buyer123!")

        buyer1 = User(
            id=BUYER_1_ID,
            email="investor@example.com",
            name="Marco Rossi",
            role="buyer",
            password=buyer1_password,
            email_verified=True,
            # Common fields now in User table
            company_name="Rossi Investments Ltd.",  # Moved from BuyerProfile!
            phone_number="+355681111111",
            website="https://rossiinvestments.com",
            created_at=datetime.now(timezone.utc)
        )
        db.add(buyer1)

        # BuyerProfile REMOVED - all fields now in User table!

        await db.commit()

    print("✅ Buyer 1: investor@example.com / Buyer123!\n")


async def seed_listings():
    """Seed sample listings."""
    print("🏢 Seeding Listings...")

    async with AsyncSessionLocal() as db:
        # Listing 1: Italian Restaurant
        listing1 = Listing(
            id=LISTING_1_ID,
            agent_id=AGENT_1_ID,
            status="active",

            # Public info
            public_title_en="High-End Italian Restaurant",
            public_description_en="Award-winning Italian restaurant in prime location.",
            category="restaurant",
            public_location_city_en="Tirana",
            public_location_area="Blloku",

            # Private info
            real_business_name="Trattoria Bella Napoli",
            real_location_address="Rruga e Durresit, Nr 25",

            # Financials
            asking_price_eur=Decimal("350000"),
            asking_price_lek=Decimal("35000000"),
            monthly_revenue_eur=Decimal("40000"),
            monthly_revenue_lek=Decimal("4000000"),
            roi=Decimal("41"),

            # Metadata
            view_count=234,
            created_at=datetime.now(timezone.utc)
        )
        db.add(listing1)

        # Listing 1 images
        listing1_img1 = ListingImage(
            id=uuid.uuid4(),
            listing_id=LISTING_1_ID,
            url="/elegant-italian-restaurant.png",
            order=0
        )
        db.add(listing1_img1)

        listing1_img2 = ListingImage(
            id=uuid.uuid4(),
            listing_id=LISTING_1_ID,
            url="/restaurant-kitchen-professional.jpg",
            order=1
        )
        db.add(listing1_img2)

        # Listing 2: Cocktail Bar
        listing2 = Listing(
            id=LISTING_2_ID,
            agent_id=AGENT_1_ID,
            status="active",

            # Public info
            public_title_en="Profitable Cocktail Bar",
            public_description_en="Trendy cocktail bar in the heart of the nightlife district.",
            category="bar",
            public_location_city_en="Tirana",
            public_location_area="City Center",

            # Private info
            real_business_name="The Speakeasy Lounge",
            real_location_address="Rruga Pjeter Bogdani, Nr 8",

            # Financials
            asking_price_eur=Decimal("180000"),
            asking_price_lek=Decimal("18000000"),
            monthly_revenue_eur=Decimal("18000"),
            monthly_revenue_lek=Decimal("1800000"),
            roi=Decimal("43"),

            # Metadata
            view_count=156,
            created_at=datetime.now(timezone.utc)
        )
        db.add(listing2)

        # Listing 2 images
        listing2_img1 = ListingImage(
            id=uuid.uuid4(),
            listing_id=LISTING_2_ID,
            url="/modern-cocktail-bar-interior-dark.jpg",
            order=0
        )
        db.add(listing2_img1)

        listing2_img2 = ListingImage(
            id=uuid.uuid4(),
            listing_id=LISTING_2_ID,
            url="/bar-counter-bottles.jpg",
            order=1
        )
        db.add(listing2_img2)

        await db.commit()

    print("✅ Listing 1: High-End Italian Restaurant (€350,000)")
    print("✅ Listing 2: Profitable Cocktail Bar (€180,000)\n")


async def seed_credit_packages():
    """Seed credit packages (PropertyFinder-style)."""
    print("💳 Seeding Credit Packages...")

    async with AsyncSessionLocal() as db:
        packages = [
            {
                "name": "Starter",
                "credits": 10,
                "price_eur": Decimal("15"),
                "price_lek": Decimal("1500"),
                "savings": None,
                "is_popular": False,
                "sort_order": 1
            },
            {
                "name": "Basic",
                "credits": 25,
                "price_eur": Decimal("30"),
                "price_lek": Decimal("3000"),
                "savings": "Save 20%",
                "is_popular": False,
                "sort_order": 2
            },
            {
                "name": "Standard",
                "credits": 50,
                "price_eur": Decimal("50"),
                "price_lek": Decimal("5000"),
                "savings": "Save 33%",
                "is_popular": True,  # Most popular
                "sort_order": 3
            },
            {
                "name": "Pro",
                "credits": 100,
                "price_eur": Decimal("80"),
                "price_lek": Decimal("8000"),
                "savings": "Save 47%",
                "is_popular": False,
                "sort_order": 4
            },
            {
                "name": "Agency",
                "credits": 250,
                "price_eur": Decimal("175"),
                "price_lek": Decimal("17500"),
                "savings": "Save 53%",
                "is_popular": False,
                "sort_order": 5
            }
        ]

        for pkg in packages:
            credit_package = CreditPackage(**pkg)
            db.add(credit_package)

        await db.commit()

    print("✅ 5 credit packages created (Starter to Agency)\n")


async def seed_promotion_tiers():
    """Seed promotion tier configurations."""
    print("🏆 Seeding Promotion Tier Configs...")

    async with AsyncSessionLocal() as db:
        # Featured tier
        featured = PromotionTierConfig(
            tier="featured",
            credit_cost=5,
            duration_days=30,
            display_name="Featured",
            description="Appear above standard listings with a Featured badge",
            badge_color="blue-500",
            is_active=True
        )
        db.add(featured)

        # Premium tier
        premium = PromotionTierConfig(
            tier="premium",
            credit_cost=15,
            duration_days=30,
            display_name="Premium",
            description="Top of search results, Premium badge, homepage carousel",
            badge_color="amber-500",
            is_active=True
        )
        db.add(premium)

        await db.commit()

    print("✅ Featured tier: 5 credits / 30 days")
    print("✅ Premium tier: 15 credits / 30 days\n")


async def main():
    """Main seeding function."""
    print("\n" + "="*60)
    print("🌱 CompanyFinder Albania - Database Seeding")
    print("="*60 + "\n")

    try:
        # Clean database
        await clean_database()

        # Seed users
        await seed_admin()
        await seed_agents()
        await seed_buyers()

        # Seed listings
        await seed_listings()

        # Seed promotion system
        await seed_credit_packages()
        await seed_promotion_tiers()

        print("="*60)
        print("🎉 Seeding completed successfully!")
        print("="*60 + "\n")

        print("📝 Login Credentials:\n")
        print("  Admin:")
        print("    Email: admin@cfind.ai")
        print("    Password: 570139281209847\n")

        print("  Agent 1 (Arben Hoxha):")
        print("    Email: arben.hoxha@realestate.al")
        print("    Password: Agent123!")
        print("    Credits: 50\n")

        print("  Agent 2 (Elena Koci):")
        print("    Email: elena.koci@brokers.al")
        print("    Password: Agent123!")
        print("    Credits: 25\n")

        print("  Buyer (Marco Rossi):")
        print("    Email: investor@example.com")
        print("    Password: Buyer123!\n")

        print("📊 Database Summary:")
        print("  - 1 Admin")
        print("  - 2 Verified Agents")
        print("  - 1 Buyer")
        print("  - 2 Listings (both active)")
        print("  - 5 Credit Packages")
        print("  - 2 Promotion Tiers\n")

        print("🚀 Start the server:")
        print("  uvicorn app.main:app --reload\n")

        print("🌐 Access API:")
        print("  http://localhost:8000/docs\n")

    except Exception as e:
        print(f"\n❌ Seeding failed: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
