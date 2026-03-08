"""
Database seeding script - Matches cfind-frontend/prisma/seed.ts exactly
Creates initial data for development and testing
"""
import asyncio
import sys
import uuid
from pathlib import Path
from datetime import datetime, UTC

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.session import AsyncSessionLocal
from app.models.user import User, AgentProfile, BuyerProfile
from app.models.listing import Listing, ListingImage
from app.models.promotion import CreditPackage, PromotionTierConfig, PromotionHistory, CreditTransaction
from app.models.lead import Lead, SavedListing  # Import to register models
from app.models.demand import BuyerDemand  # Import to register models
from app.models.token import EmailVerificationToken, PasswordResetToken, RefreshToken  # Import to register models
from app.core.security import hash_password


async def seed_database():
    """Seed database with initial data matching frontend seed"""
    async with AsyncSessionLocal() as db:
        try:
            print("Start seeding ...")

            # ================================================================
            # AGENT 1: Arben Hoxha
            # ================================================================
            print("Seeding Agent 1: Arben Hoxha...")
            agent1 = User(
                id=uuid.UUID("00000000-0000-0000-0000-000000000001"),  # agent-1
                email="arben.hoxha@realestate.al",
                name="Arben Hoxha",
                role="agent",
                email_verified=True,
                password=hash_password("Agent123!"),  # Default password
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            db.add(agent1)
            await db.flush()

            agent1_profile = AgentProfile(
                user_id=agent1.id,
                agency_name="Tirana Business Brokers",
                license_number="AL-BRK-2024-001",
                bio_en="Over 15 years of experience in business acquisitions across Albania.",
                whatsapp_number="+355691234567",
                phone_number="+355691234567",
                license_document_url="https://example.com/docs/agent1-license.pdf",
                company_document_url="https://example.com/docs/agent1-company.pdf",
                id_document_url="https://example.com/docs/agent1-id.pdf",
                verification_status="approved",
                verified_at=datetime.now(UTC),
                credit_balance=50,  # Starting credits for demo
            )
            db.add(agent1_profile)

            # ================================================================
            # AGENT 2: Elena Koci
            # ================================================================
            print("Seeding Agent 2: Elena Koci...")
            agent2 = User(
                id=uuid.UUID("00000000-0000-0000-0000-000000000002"),  # agent-2
                email="elena.koci@brokers.al",
                name="Elena Koci",
                role="agent",
                email_verified=True,
                password=hash_password("Agent123!"),  # Default password
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            db.add(agent2)
            await db.flush()

            agent2_profile = AgentProfile(
                user_id=agent2.id,
                agency_name="Premium Business Sales",
                license_number="AL-BRK-2024-002",
                bio_en="Expert in technology and service-based business transactions.",
                whatsapp_number="+355699876543",
                phone_number="+355699876543",
                license_document_url="https://example.com/docs/agent2-license.pdf",
                company_document_url="https://example.com/docs/agent2-company.pdf",
                id_document_url="https://example.com/docs/agent2-id.pdf",
                verification_status="approved",
                verified_at=datetime.now(UTC),
                credit_balance=0,
            )
            db.add(agent2_profile)

            # ================================================================
            # BUYER 1: Marco Rossi
            # ================================================================
            print("Seeding Buyer 1: Marco Rossi...")
            buyer1 = User(
                id=uuid.UUID("00000000-0000-0000-0000-000000000003"),  # buyer-1
                email="investor@example.com",
                name="Marco Rossi",
                role="buyer",
                email_verified=True,
                password=hash_password("Buyer123!"),  # Default password
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            db.add(buyer1)
            await db.flush()

            buyer1_profile = BuyerProfile(
                user_id=buyer1.id,
                company_name="Rossi Investments Ltd.",
            )
            db.add(buyer1_profile)

            # ================================================================
            # ADMIN: Master Admin
            # ================================================================
            print("Seeding Admin...")
            admin = User(
                id=uuid.UUID("00000000-0000-0000-0000-000000000099"),  # admin-main
                email="admin@cfind.ai",
                name="Master Admin",
                role="admin",
                email_verified=True,
                password=hash_password("570139281209847"),  # Exact match from frontend
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            db.add(admin)

            await db.flush()
            print("Users seeded successfully.")

            # ================================================================
            # LISTING 1: High-End Italian Restaurant
            # ================================================================
            print("Seeding Listing 1: High-End Italian Restaurant...")
            listing1 = Listing(
                id=uuid.UUID("10000000-0000-0000-0000-000000000001"),  # listing-1
                agent_id=agent1.id,
                status="active",
                # Public info
                public_title_en="High-End Italian Restaurant",
                public_description_en="Award-winning Italian restaurant in prime location.",
                category="restaurant",
                public_location_city_en="Tirana",
                public_location_area="Blloku",
                # Pricing
                asking_price_eur=350000,
                monthly_revenue_eur=40000,
                roi=41,
                # Private info
                real_business_name="Trattoria Bella Napoli",
                real_location_address="Rruga e Durresit, Nr 25",
                # Meta
                view_count=234,
                promotion_tier="standard",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            db.add(listing1)
            await db.flush()

            # Listing 1 images
            listing1_img1 = ListingImage(
                id=uuid.uuid4(),
                listing_id=listing1.id,
                url="/elegant-italian-restaurant.png",
                order=0,
            )
            listing1_img2 = ListingImage(
                id=uuid.uuid4(),
                listing_id=listing1.id,
                url="/restaurant-kitchen-professional.jpg",
                order=1,
            )
            db.add_all([listing1_img1, listing1_img2])

            # ================================================================
            # LISTING 2: Profitable Cocktail Bar
            # ================================================================
            print("Seeding Listing 2: Profitable Cocktail Bar...")
            listing2 = Listing(
                id=uuid.UUID("10000000-0000-0000-0000-000000000002"),  # listing-2
                agent_id=agent1.id,
                status="active",
                # Public info
                public_title_en="Profitable Cocktail Bar",
                public_description_en="Trendy cocktail bar in the heart of the nightlife district.",
                category="bar",
                public_location_city_en="Tirana",
                public_location_area="City Center",
                # Pricing
                asking_price_eur=180000,
                monthly_revenue_eur=18000,
                roi=43,
                # Private info
                real_business_name="The Speakeasy Lounge",
                real_location_address="Rruga Pjeter Bogdani, Nr 8",
                # Meta
                view_count=156,
                promotion_tier="standard",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            db.add(listing2)
            await db.flush()

            # Listing 2 images
            listing2_img1 = ListingImage(
                id=uuid.uuid4(),
                listing_id=listing2.id,
                url="/modern-cocktail-bar-interior-dark.jpg",
                order=0,
            )
            listing2_img2 = ListingImage(
                id=uuid.uuid4(),
                listing_id=listing2.id,
                url="/bar-counter-bottles.jpg",
                order=1,
            )
            db.add_all([listing2_img1, listing2_img2])
            print("Listings seeded successfully.")

            # ================================================================
            # CREDIT PACKAGES (5 packages - exact match to frontend)
            # ================================================================
            print("Seeding Credit Packages...")
            packages = [
                CreditPackage(
                    id=uuid.uuid4(),
                    name="Starter",
                    credits=10,
                    price_eur=15.0,
                    savings=None,
                    is_popular=False,
                    is_active=True,
                    sort_order=1,
                ),
                CreditPackage(
                    id=uuid.uuid4(),
                    name="Basic",
                    credits=25,
                    price_eur=30.0,
                    savings="Save 20%",
                    is_popular=False,
                    is_active=True,
                    sort_order=2,
                ),
                CreditPackage(
                    id=uuid.uuid4(),
                    name="Standard",
                    credits=50,
                    price_eur=50.0,
                    savings="Save 33%",
                    is_popular=True,  # This is the popular package
                    is_active=True,
                    sort_order=3,
                ),
                CreditPackage(
                    id=uuid.uuid4(),
                    name="Pro",
                    credits=100,
                    price_eur=80.0,
                    savings="Save 47%",
                    is_popular=False,
                    is_active=True,
                    sort_order=4,
                ),
                CreditPackage(
                    id=uuid.uuid4(),
                    name="Agency",
                    credits=250,
                    price_eur=175.0,
                    savings="Save 53%",
                    is_popular=False,
                    is_active=True,
                    sort_order=5,
                ),
            ]
            db.add_all(packages)
            print("Credit Packages seeded.")

            # ================================================================
            # PROMOTION TIER CONFIGS (2 tiers - exact match to frontend)
            # ================================================================
            print("Seeding Promotion Tier Configs...")
            tiers = [
                PromotionTierConfig(
                    id=uuid.uuid4(),
                    tier="featured",
                    credit_cost=5,
                    duration_days=30,
                    display_name="Featured",
                    description="Appear above standard listings with a Featured badge",
                    badge_color="blue-500",
                    is_active=True,
                ),
                PromotionTierConfig(
                    id=uuid.uuid4(),
                    tier="premium",
                    credit_cost=15,
                    duration_days=30,
                    display_name="Premium",
                    description="Top of search results, Premium badge, homepage carousel",
                    badge_color="amber-500",
                    is_active=True,
                ),
            ]
            db.add_all(tiers)
            print("Promotion Tier Configs seeded.")

            # Commit all changes
            await db.commit()
            print("\n" + "=" * 60)
            print("✅ Database seeded successfully!")
            print("=" * 60)
            print("\nTest accounts created:")
            print("  Admin:  admin@cfind.ai / 570139281209847")
            print("  Agent1: arben.hoxha@realestate.al / Agent123!")
            print("  Agent2: elena.koci@brokers.al / Agent123!")
            print("  Buyer:  investor@example.com / Buyer123!")
            print("=" * 60)

        except Exception as e:
            await db.rollback()
            print(f"\n❌ Error seeding database: {str(e)}")
            import traceback
            traceback.print_exc()
            raise


if __name__ == "__main__":
    asyncio.run(seed_database())