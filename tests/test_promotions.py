"""
Promotion and credit system tests.

Covers:
- Get credit packages (public endpoint)
- Get promotion tiers (public endpoint)
- Purchase credits (agent buys package → balance increases)
- Promote listing to featured (deducts 5 credits)
- Promote listing to premium (deducts 15 credits)
- Upgrade featured → premium (deducts only 10 credits = difference)
- Insufficient credits → error
- Cancel promotion (tier resets to standard, no refund)
- Get active promotions
- Get agent credits + transaction history
- Role enforcement
"""

import uuid

from tests.conftest import login_user, auth_headers_and_cookies, approve_agent, TestSessionLocal


def make_listing(**overrides):
    base = {
        "country_code": "al",
        "real_business_name": "Promo Test Business",
        "real_location_address": "Rruga Promo 1, Tirana",
        "public_title_en": "Business For Promotion Testing",
        "public_description_en": "A business to test the credit purchase and promotion system flows.",
        "category": "restaurant",
        "public_location_city_en": "Tirana",
        "asking_price_eur": 100000,
        "monthly_revenue_eur": 10000,
        "images": [{"url": "https://test-bucket.s3.amazonaws.com/fake/img.jpg", "order": 0}],
    }
    base.update(overrides)
    return base


async def setup_agent_with_listing(client, registered_agent, admin_user):
    """Approve agent, create listing. Returns (agent_cookies, listing_id)."""
    admin_cookies = await login_user(client, admin_user["email"], admin_user["password"])
    await approve_agent(client, admin_cookies, registered_agent["id"])

    agent_cookies = await login_user(client, registered_agent["email"], registered_agent["password"])
    headers, cookies = await auth_headers_and_cookies(agent_cookies)

    r = await client.post("/api/listings", json=make_listing(), headers=headers, cookies=cookies)
    assert r.status_code == 201
    return agent_cookies, r.json()["listing"]["id"]


async def give_credits(agent_id: str, amount: int):
    """Give credits to an agent directly via DB (simulates admin bonus)."""
    from app.models.promotion import CreditTransaction
    async with TestSessionLocal() as session:
        tx = CreditTransaction(
            id=uuid.uuid4(),
            agent_id=uuid.UUID(agent_id),
            amount=amount,
            type="bonus",
            description="Test credits",
        )
        session.add(tx)

        # Update agent profile balance
        from sqlalchemy import update
        from app.models.user import AgentProfile
        await session.execute(
            update(AgentProfile)
            .where(AgentProfile.user_id == uuid.UUID(agent_id))
            .values(credit_balance=AgentProfile.credit_balance + amount)
        )
        await session.commit()


# ==========================================================================
# PUBLIC ENDPOINTS
# ==========================================================================

class TestPublicEndpoints:

    async def test_get_credit_packages(self, client):
        """Public endpoint returns all 5 credit packages."""
        r = await client.get("/api/promotions/packages")
        assert r.status_code == 200
        packages = r.json()["packages"]
        assert len(packages) == 5
        names = [p["name"] for p in packages]
        assert "Starter" in names
        assert "Basic" in names
        assert "Standard" in names
        assert "Pro" in names
        assert "Agency" in names

    async def test_credit_package_data_matches(self, client):
        """Verify package prices and credits match expected values."""
        r = await client.get("/api/promotions/packages")
        packages = {p["name"]: p for p in r.json()["packages"]}

        assert packages["Starter"]["credits"] == 10
        assert float(packages["Starter"]["price_eur"]) == 15.0

        assert packages["Standard"]["credits"] == 50
        assert float(packages["Standard"]["price_eur"]) == 50.0
        assert packages["Standard"]["is_popular"] is True

        assert packages["Agency"]["credits"] == 250
        assert float(packages["Agency"]["price_eur"]) == 175.0

    async def test_get_promotion_tiers(self, client):
        """Public endpoint returns featured and premium tiers."""
        r = await client.get("/api/promotions/tiers")
        assert r.status_code == 200
        tiers = r.json()["tiers"]
        assert len(tiers) == 2
        tier_names = [t["tier"] for t in tiers]
        assert "featured" in tier_names
        assert "premium" in tier_names

    async def test_promotion_tier_costs(self, client):
        """Verify tier credit costs match expected values."""
        r = await client.get("/api/promotions/tiers")
        tiers = {t["tier"]: t for t in r.json()["tiers"]}

        assert tiers["featured"]["credit_cost"] == 5
        assert tiers["featured"]["duration_days"] == 30

        assert tiers["premium"]["credit_cost"] == 15
        assert tiers["premium"]["duration_days"] == 30


# ==========================================================================
# PURCHASE CREDITS
# ==========================================================================

class TestPurchaseCredits:

    async def test_purchase_credits(self, client, registered_agent, admin_user):
        """Agent buys a credit package → balance increases."""
        agent_cookies, _ = await setup_agent_with_listing(client, registered_agent, admin_user)
        headers, cookies = await auth_headers_and_cookies(agent_cookies)

        # Get the Starter package ID
        pkgs = await client.get("/api/promotions/packages")
        starter = next(p for p in pkgs.json()["packages"] if p["name"] == "Starter")

        r = await client.post("/api/promotions/purchase", json={
            "package_id": starter["id"],
        }, headers=headers, cookies=cookies)
        assert r.status_code == 200
        assert r.json()["new_balance"] == 10  # Starter = 10 credits

    async def test_purchase_invalid_package(self, client, registered_agent, admin_user):
        agent_cookies, _ = await setup_agent_with_listing(client, registered_agent, admin_user)
        headers, cookies = await auth_headers_and_cookies(agent_cookies)

        r = await client.post("/api/promotions/purchase", json={
            "package_id": str(uuid.uuid4()),
        }, headers=headers, cookies=cookies)
        assert r.status_code in (400, 404)

    async def test_buyer_cannot_purchase_credits(self, client, registered_buyer):
        """Only agents can purchase credits."""
        cookies = await login_user(client, registered_buyer["email"], registered_buyer["password"])
        headers, cookies = await auth_headers_and_cookies(cookies)

        r = await client.post("/api/promotions/purchase", json={
            "package_id": str(uuid.uuid4()),
        }, headers=headers, cookies=cookies)
        assert r.status_code == 403


# ==========================================================================
# PROMOTE LISTING
# ==========================================================================

class TestPromoteListing:

    async def test_promote_to_featured(self, client, registered_agent, admin_user):
        """Standard → Featured costs 5 credits."""
        agent_cookies, listing_id = await setup_agent_with_listing(client, registered_agent, admin_user)
        await give_credits(registered_agent["id"], 20)

        headers, cookies = await auth_headers_and_cookies(agent_cookies)
        r = await client.post(f"/api/promotions/{listing_id}/promote", json={
            "tier": "featured",
        }, headers=headers, cookies=cookies)
        assert r.status_code == 200
        assert r.json()["credits_deducted"] == 5
        assert r.json()["new_balance"] == 15  # 20 - 5
        assert r.json()["listing_tier"] == "featured"

    async def test_promote_to_premium(self, client, registered_agent, admin_user):
        """Standard → Premium costs 15 credits."""
        agent_cookies, listing_id = await setup_agent_with_listing(client, registered_agent, admin_user)
        await give_credits(registered_agent["id"], 20)

        headers, cookies = await auth_headers_and_cookies(agent_cookies)
        r = await client.post(f"/api/promotions/{listing_id}/promote", json={
            "tier": "premium",
        }, headers=headers, cookies=cookies)
        assert r.status_code == 200
        assert r.json()["credits_deducted"] == 15
        assert r.json()["new_balance"] == 5  # 20 - 15

    async def test_upgrade_featured_to_premium(self, client, registered_agent, admin_user):
        """Featured → Premium costs only 10 credits (difference)."""
        agent_cookies, listing_id = await setup_agent_with_listing(client, registered_agent, admin_user)
        await give_credits(registered_agent["id"], 30)

        headers, cookies = await auth_headers_and_cookies(agent_cookies)

        # First promote to featured
        await client.post(f"/api/promotions/{listing_id}/promote", json={
            "tier": "featured",
        }, headers=headers, cookies=cookies)

        # Upgrade to premium
        r = await client.post(f"/api/promotions/{listing_id}/promote", json={
            "tier": "premium",
        }, headers=headers, cookies=cookies)
        assert r.status_code == 200
        assert r.json()["credits_deducted"] == 10  # 15 - 5 = 10 difference
        assert r.json()["listing_tier"] == "premium"

    async def test_insufficient_credits(self, client, registered_agent, admin_user):
        """Cannot promote without enough credits."""
        agent_cookies, listing_id = await setup_agent_with_listing(client, registered_agent, admin_user)
        # No credits given

        headers, cookies = await auth_headers_and_cookies(agent_cookies)
        r = await client.post(f"/api/promotions/{listing_id}/promote", json={
            "tier": "featured",
        }, headers=headers, cookies=cookies)
        assert r.status_code == 402

    async def test_promote_nonexistent_listing(self, client, registered_agent, admin_user):
        agent_cookies, _ = await setup_agent_with_listing(client, registered_agent, admin_user)
        await give_credits(registered_agent["id"], 20)

        headers, cookies = await auth_headers_and_cookies(agent_cookies)
        r = await client.post(f"/api/promotions/{uuid.uuid4()}/promote", json={
            "tier": "featured",
        }, headers=headers, cookies=cookies)
        assert r.status_code in (400, 404)


# ==========================================================================
# CANCEL PROMOTION
# ==========================================================================

class TestCancelPromotion:

    async def test_cancel_promotion_resets_tier(self, client, registered_agent, admin_user):
        """Cancelling promotion resets listing to standard. No refund."""
        agent_cookies, listing_id = await setup_agent_with_listing(client, registered_agent, admin_user)
        await give_credits(registered_agent["id"], 20)

        headers, cookies = await auth_headers_and_cookies(agent_cookies)

        # Promote
        await client.post(f"/api/promotions/{listing_id}/promote", json={
            "tier": "featured",
        }, headers=headers, cookies=cookies)

        # Cancel
        r = await client.post(f"/api/promotions/{listing_id}/cancel", headers=headers, cookies=cookies)
        assert r.status_code == 200

        # Verify listing tier is back to standard
        listing_r = await client.get(f"/api/listings/{listing_id}", cookies=agent_cookies)
        assert listing_r.json()["listing"]["promotion_tier"] == "standard"

        # Verify NO refund — balance should still be 15 (20 - 5 for featured)
        credits_r = await client.get("/api/promotions/credits", cookies=agent_cookies)
        assert credits_r.json()["credit_balance"] == 15


# ==========================================================================
# AGENT CREDITS & HISTORY
# ==========================================================================

class TestAgentCredits:

    async def test_get_agent_credits(self, client, registered_agent, admin_user):
        agent_cookies, _ = await setup_agent_with_listing(client, registered_agent, admin_user)
        await give_credits(registered_agent["id"], 50)

        r = await client.get("/api/promotions/credits", cookies=agent_cookies)
        assert r.status_code == 200
        assert r.json()["credit_balance"] == 50
        # Should have transaction history
        assert len(r.json()["transactions"]) >= 1

    async def test_get_active_promotions(self, client, registered_agent, admin_user):
        agent_cookies, listing_id = await setup_agent_with_listing(client, registered_agent, admin_user)
        await give_credits(registered_agent["id"], 20)

        headers, cookies = await auth_headers_and_cookies(agent_cookies)

        # Promote
        await client.post(f"/api/promotions/{listing_id}/promote", json={
            "tier": "featured",
        }, headers=headers, cookies=cookies)

        r = await client.get("/api/promotions/active", cookies=agent_cookies)
        assert r.status_code == 200
        assert len(r.json()["promotions"]) >= 1

    async def test_buyer_cannot_access_credits(self, client, registered_buyer):
        cookies = await login_user(client, registered_buyer["email"], registered_buyer["password"])
        r = await client.get("/api/promotions/credits", cookies=cookies)
        assert r.status_code == 403
