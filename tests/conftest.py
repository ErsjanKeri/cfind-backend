"""
Test infrastructure for API integration tests.

Sets up:
- Test database (PostgreSQL — local or Docker via TEST_DATABASE_URL env var)
- Fresh tables created before each test session, dropped after
- httpx AsyncClient wired to the FastAPI app
- get_db override so the app uses the test database
- Auth helper fixtures (register, login, get cookies)
- S3 mocking (no real uploads during tests)

Run with Docker:
    docker compose -f docker-compose.test.yml up --build --abort-on-container-exit
"""

import os
import uuid
from unittest.mock import patch, AsyncMock

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

# Import all models so Base.metadata knows about every table
from app.models import Base  # noqa: F401 — triggers all model imports

from app.db.session import get_db
from app.main import app


# ==========================================================================
# DATABASE SETUP
# ==========================================================================

# Read from env (set by docker-compose.test.yml), fallback to local
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://localhost:5432/cfind_test"
)

# Create engine for test database
test_engine = create_async_engine(
    TEST_DATABASE_URL,
    poolclass=NullPool,
    echo=False,
)

# Session factory for test database
TestSessionLocal = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def override_get_db():
    """
    Replacement for app.db.session.get_db.
    Same logic (auto-commit, rollback on error) but uses the test database.
    """
    async with TestSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ==========================================================================
# SESSION-SCOPED FIXTURES (run once per test session)
# ==========================================================================

@pytest.fixture(scope="session", autouse=True)
async def setup_database():
    """
    Create all tables before tests run, seed reference data, drop after.

    scope="session" means this runs ONCE at the start, not per-test.
    autouse=True means every test gets this automatically.
    """
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed reference data — must match production (scripts/populate_countries.py + seed_db.py)
    async with TestSessionLocal() as session:
        from decimal import Decimal
        from app.models.country import Country, City
        from app.models.promotion import CreditPackage, PromotionTierConfig

        # Countries + cities (from scripts/populate_countries.py)
        countries_data = {
            "al": {
                "name": "Albania",
                "cities": [
                    "Tirana", "Durrës", "Vlorë", "Shkodër", "Elbasan",
                    "Korçë", "Fier", "Berat", "Lushnjë", "Sarandë",
                ],
            },
            "ae": {
                "name": "United Arab Emirates",
                "cities": [
                    "Dubai", "Abu Dhabi", "Sharjah", "Ajman",
                    "Ras Al Khaimah", "Umm Al Quwain", "Fujairah",
                ],
            },
        }
        for code, data in countries_data.items():
            session.add(Country(code=code, name=data["name"]))
            for city_name in data["cities"]:
                session.add(City(country_code=code, name=city_name))

        # Credit packages (matched to CreditPackage model — EUR only)
        packages = [
            {"name": "Starter", "credits": 10, "price_eur": Decimal("15"), "savings": None, "is_popular": False, "sort_order": 1},
            {"name": "Basic", "credits": 25, "price_eur": Decimal("30"), "savings": "Save 20%", "is_popular": False, "sort_order": 2},
            {"name": "Standard", "credits": 50, "price_eur": Decimal("50"), "savings": "Save 33%", "is_popular": True, "sort_order": 3},
            {"name": "Pro", "credits": 100, "price_eur": Decimal("80"), "savings": "Save 47%", "is_popular": False, "sort_order": 4},
            {"name": "Agency", "credits": 250, "price_eur": Decimal("175"), "savings": "Save 53%", "is_popular": False, "sort_order": 5},
        ]
        for pkg in packages:
            session.add(CreditPackage(**pkg))

        # Promotion tiers (from scripts/seed_db.py)
        session.add(PromotionTierConfig(
            tier="featured", credit_cost=5, duration_days=30,
            display_name="Featured", description="Appear above standard listings with a Featured badge",
            badge_color="blue-500", is_active=True,
        ))
        session.add(PromotionTierConfig(
            tier="premium", credit_cost=15, duration_days=30,
            display_name="Premium", description="Top of search results, Premium badge, homepage carousel",
            badge_color="amber-500", is_active=True,
        ))

        await session.commit()

    yield  # Tests run here

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await test_engine.dispose()


# ==========================================================================
# FUNCTION-SCOPED FIXTURES (run per test)
# ==========================================================================

@pytest.fixture(autouse=True)
async def clean_tables():
    """
    Truncate all tables between tests so each test starts with a clean DB.

    This is faster than drop/create — it keeps the schema but removes all rows.
    TRUNCATE ... CASCADE handles foreign key dependencies.

    Skips 'countries' — reference data seeded once in setup_database.
    """
    yield  # Test runs first

    # Cleanup after test — skip reference tables seeded once in setup_database
    skip = {"countries", "cities", "credit_packages", "promotion_tier_configs"}
    tables_to_truncate = [
        f'"{table.name}"'
        for table in reversed(Base.metadata.sorted_tables)
        if table.name not in skip
    ]
    if tables_to_truncate:
        async with test_engine.begin() as conn:
            await conn.exec_driver_sql(
                "TRUNCATE TABLE {} RESTART IDENTITY CASCADE".format(
                    ", ".join(tables_to_truncate)
                )
            )


@pytest.fixture
async def db():
    """
    Provide a raw database session for tests that need direct DB access
    (e.g., checking records were created, reading verification tokens).
    """
    async with TestSessionLocal() as session:
        yield session


@pytest.fixture
async def client():
    """
    HTTP client wired to the FastAPI app.

    - Overrides get_db → test database
    - Mocks S3 uploads → returns fake URLs (no real file uploads)
    - Mocks email sending → always succeeds silently
    - Uses ASGITransport so requests go through the full FastAPI stack
      (middleware, deps, routes, repos, DB) without starting a real server.
    """
    # Point the app at the test database
    app.dependency_overrides[get_db] = override_get_db

    # Disable ALL rate limiters — each auth route file creates its own Limiter instance
    from app.api.routes.auth import registration, session, password, verification
    from app.api.routes import chat
    all_limiters = [
        app.state.limiter,
        registration.limiter,
        session.limiter,
        password.limiter,
        verification.limiter,
        chat.limiter,
    ]
    for lim in all_limiters:
        lim.enabled = False

    # Mock S3 — patch where it's USED (upload_service), not where it's defined (s3_client)
    with patch("app.services.upload_service.upload_file", return_value="https://test-bucket.s3.amazonaws.com/fake/file.jpg"), \
         patch("app.services.upload_service.delete_file", return_value=True), \
         patch("app.services.upload_service.generate_presigned_post", return_value={"url": "https://test-bucket.s3.amazonaws.com", "fields": {}}), \
         patch("app.services.email_service.send_email_smtp", new_callable=AsyncMock, return_value=True):

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c

    # Clean up overrides
    for lim in all_limiters:
        lim.enabled = True
    app.dependency_overrides.clear()


# ==========================================================================
# AUTH HELPER FIXTURES
# ==========================================================================

@pytest.fixture
def test_password():
    """Standard password that meets all validation rules."""
    return "TestPass123"


@pytest.fixture
async def registered_buyer(client, test_password):
    """
    Register a buyer and verify their email.

    Returns dict with:
    - id: user UUID
    - email: buyer's email
    - name: buyer's name
    - password: plain text password (for login)
    """
    email = f"buyer_{uuid.uuid4().hex[:8]}@test.com"
    name = "Test Buyer"

    # Register
    r = await client.post("/api/auth/register", data={
        "name": name,
        "email": email,
        "password": test_password,
        "role": "buyer",
    })
    assert r.status_code == 201, f"Buyer registration failed: {r.text}"
    user_id = r.json()["user_id"]

    # Verify email directly in DB (skip email flow)
    async with TestSessionLocal() as session:
        from sqlalchemy import update
        from app.models.user import User
        await session.execute(
            update(User).where(User.id == user_id).values(email_verified=True)
        )
        await session.commit()

    return {"id": user_id, "email": email, "name": name, "password": test_password}


@pytest.fixture
async def registered_agent(client, test_password):
    """
    Register an agent with documents and verify their email.
    Agent is NOT yet approved by admin — verification_status = "pending".

    Returns dict with:
    - id, email, name, password
    """
    email = f"agent_{uuid.uuid4().hex[:8]}@test.com"
    name = "Test Agent"

    # Create minimal fake file uploads
    files = {
        "license_document": ("license.pdf", b"fake-pdf-content", "application/pdf"),
        "company_document": ("company.pdf", b"fake-pdf-content", "application/pdf"),
        "id_document": ("id.pdf", b"fake-pdf-content", "application/pdf"),
    }

    r = await client.post("/api/auth/register", data={
        "name": name,
        "email": email,
        "password": test_password,
        "role": "agent",
        "company_name": "Test Agency LLC",
        "operating_country": "al",
        "license_number": "LIC-12345",
        "phone": "+355691234567",
        "whatsapp": "+355691234567",
    }, files=files)
    assert r.status_code == 201, f"Agent registration failed: {r.text}"
    user_id = r.json()["user_id"]

    # Verify email directly in DB
    async with TestSessionLocal() as session:
        from sqlalchemy import update
        from app.models.user import User
        await session.execute(
            update(User).where(User.id == user_id).values(email_verified=True)
        )
        await session.commit()

    return {"id": user_id, "email": email, "name": name, "password": test_password}


@pytest.fixture
async def admin_user(client, test_password):
    """
    Create an admin user directly in the DB.
    (Admins are created manually, not through registration.)

    Returns dict with:
    - id, email, name, password
    """
    from app.core.security import hash_password

    admin_id = uuid.uuid4()
    email = f"admin_{uuid.uuid4().hex[:8]}@test.com"

    async with TestSessionLocal() as session:
        from app.models.user import User
        admin = User(
            id=admin_id,
            name="Test Admin",
            email=email,
            password=hash_password(test_password),
            role="admin",
            email_verified=True,
        )
        session.add(admin)
        await session.commit()

    return {"id": str(admin_id), "email": email, "name": "Test Admin", "password": test_password}


async def login_user(client, email: str, password: str) -> dict:
    """
    Log in a user and return cookies dict.

    Usage:
        cookies = await login_user(client, buyer["email"], buyer["password"])
        r = await client.get("/api/some-endpoint", cookies=cookies)
    """
    r = await client.post("/api/auth/login", json={
        "email": email,
        "password": password,
    })
    assert r.status_code == 200, f"Login failed for {email}: {r.text}"

    # Extract all cookies set by the response
    cookies = {}
    for cookie_name in ["access_token", "csrf_token", "refresh_token"]:
        if cookie_name in r.cookies:
            cookies[cookie_name] = r.cookies[cookie_name]

    return cookies


async def auth_headers_and_cookies(cookies: dict) -> tuple[dict, dict]:
    """
    Build headers + cookies for authenticated state-changing requests.

    State-changing requests (POST/PUT/DELETE) need:
    - access_token cookie (auth)
    - X-CSRF-Token header (CSRF protection)

    Returns: (headers, cookies) tuple
    """
    headers = {}
    if "csrf_token" in cookies:
        headers["X-CSRF-Token"] = cookies["csrf_token"]
    return headers, cookies


async def approve_agent(client, admin_cookies: dict, agent_id: str):
    """Admin approves an agent's verification."""
    headers, cookies = await auth_headers_and_cookies(admin_cookies)
    r = await client.post(
        f"/api/admin/agents/{agent_id}/verify",
        headers=headers,
        cookies=cookies,
    )
    assert r.status_code == 200, f"Agent approval failed: {r.text}"
    return r.json()
