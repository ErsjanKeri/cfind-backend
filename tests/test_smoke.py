"""
Smoke test — verifies the test infrastructure works.

Tests:
1. Health endpoint responds (app is running)
2. Buyer can register (DB + auth working)
3. Agent can register with docs (file upload mocking working)
4. Login works and returns cookies (JWT working)
"""


async def test_health_check(client):
    """App responds to health check — proves the test client is wired up."""
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"


async def test_buyer_registration(client, test_password):
    """Buyer can register — proves DB writes work."""
    r = await client.post("/api/auth/register", data={
        "name": "Smoke Buyer",
        "email": "smoke_buyer@test.com",
        "password": test_password,
        "role": "buyer",
    })
    assert r.status_code == 201
    assert r.json()["success"] is True
    assert "user_id" in r.json()


async def test_agent_registration(client, test_password):
    """Agent can register with documents — proves S3 mocking works."""
    files = {
        "license_document": ("license.pdf", b"fake-pdf", "application/pdf"),
        "company_document": ("company.pdf", b"fake-pdf", "application/pdf"),
        "id_document": ("id.pdf", b"fake-pdf", "application/pdf"),
    }
    r = await client.post("/api/auth/register", data={
        "name": "Smoke Agent",
        "email": "smoke_agent@test.com",
        "password": test_password,
        "role": "agent",
        "company_name": "Smoke Agency",
        "operating_country": "al",
        "license_number": "SMOKE-001",
        "phone": "+355699999999",
        "whatsapp": "+355699999999",
    }, files=files)
    assert r.status_code == 201, f"Agent registration failed: {r.text}"
    assert r.json()["success"] is True


async def test_login_returns_cookies(client, registered_buyer):
    """Login sets auth cookies — proves JWT signing works."""
    from tests.conftest import login_user

    cookies = await login_user(client, registered_buyer["email"], registered_buyer["password"])

    assert "access_token" in cookies, "No access_token cookie set"
    assert "csrf_token" in cookies, "No csrf_token cookie set"
