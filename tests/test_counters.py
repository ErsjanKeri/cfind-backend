"""
Counter tests — verify that aggregate counters are updated correctly.

Covers:
- AgentProfile.listings_count increments on listing creation
- AgentProfile.listings_count decrements on listing deletion
- AgentProfile.deals_completed increments when demand status → "fulfilled"
- PromotionHistory.views_during_promotion increments on promoted listing view
- PromotionHistory.leads_during_promotion increments on lead for promoted listing
"""

import uuid

from sqlalchemy import select

from tests.conftest import login_user, auth_headers_and_cookies, approve_agent, TestSessionLocal
from app.models.user import AgentProfile
from app.models.promotion import PromotionHistory


def make_listing(**overrides):
    base = {
        "country_code": "al",
        "real_business_name": "Counter Test Biz",
        "real_location_address": "Rruga Counter 1, Tirana",
        "public_title_en": "Business For Counter Testing",
        "public_description_en": "A business to test that aggregate counters update correctly.",
        "category": "restaurant",
        "public_location_city_en": "Tirana",
        "asking_price_eur": 100000,
        "monthly_revenue_eur": 10000,
        "images": [{"url": "https://test-bucket.s3.amazonaws.com/fake/img.jpg", "order": 0}],
    }
    base.update(overrides)
    return base


def make_demand(**overrides):
    base = {
        "country_code": "al",
        "budget_min_eur": 50000,
        "budget_max_eur": 200000,
        "category": "restaurant",
        "preferred_city_en": "Tirana",
        "description": "Looking for a profitable restaurant in Tirana with good foot traffic.",
        "demand_type": "investor",
    }
    base.update(overrides)
    return base


async def get_agent_profile(agent_id: str) -> AgentProfile:
    """Read agent profile directly from DB."""
    async with TestSessionLocal() as session:
        result = await session.execute(
            select(AgentProfile).where(AgentProfile.user_id == uuid.UUID(agent_id))
        )
        return result.scalar_one()


async def get_active_promotion(listing_id: str) -> PromotionHistory:
    """Read active promotion for a listing directly from DB."""
    async with TestSessionLocal() as session:
        result = await session.execute(
            select(PromotionHistory).where(
                PromotionHistory.listing_id == uuid.UUID(listing_id),
                PromotionHistory.status == "active"
            )
        )
        return result.scalar_one_or_none()


async def give_credits(agent_id: str, amount: int):
    """Give credits to an agent directly via DB."""
    from sqlalchemy import update as sa_update
    async with TestSessionLocal() as session:
        from app.models.promotion import CreditTransaction
        session.add(CreditTransaction(
            id=uuid.uuid4(),
            agent_id=uuid.UUID(agent_id),
            amount=amount,
            type="bonus",
            description="Test credits",
        ))
        await session.execute(
            sa_update(AgentProfile)
            .where(AgentProfile.user_id == uuid.UUID(agent_id))
            .values(credit_balance=AgentProfile.credit_balance + amount)
        )
        await session.commit()


# ==========================================================================
# LISTINGS COUNT
# ==========================================================================

class TestListingsCount:

    async def test_listings_count_increments_on_create(self, client, registered_agent, admin_user):
        """Creating a listing should increment AgentProfile.listings_count."""
        admin_cookies = await login_user(client, admin_user["email"], admin_user["password"])
        await approve_agent(client, admin_cookies, registered_agent["id"])

        agent_cookies = await login_user(client, registered_agent["email"], registered_agent["password"])
        headers, cookies = await auth_headers_and_cookies(agent_cookies)

        # Before: listings_count should be 0
        profile = await get_agent_profile(registered_agent["id"])
        assert profile.listings_count == 0

        # Create first listing
        r = await client.post("/api/listings", json=make_listing(), headers=headers, cookies=cookies)
        assert r.status_code == 201

        profile = await get_agent_profile(registered_agent["id"])
        assert profile.listings_count == 1

        # Create second listing
        r2 = await client.post(
            "/api/listings",
            json=make_listing(public_title_en="Second Counter Test Business"),
            headers=headers, cookies=cookies,
        )
        assert r2.status_code == 201

        profile = await get_agent_profile(registered_agent["id"])
        assert profile.listings_count == 2

    async def test_listings_count_decrements_on_delete(self, client, registered_agent, admin_user):
        """Deleting a listing should decrement AgentProfile.listings_count."""
        admin_cookies = await login_user(client, admin_user["email"], admin_user["password"])
        await approve_agent(client, admin_cookies, registered_agent["id"])

        agent_cookies = await login_user(client, registered_agent["email"], registered_agent["password"])
        headers, cookies = await auth_headers_and_cookies(agent_cookies)

        # Create a listing
        r = await client.post("/api/listings", json=make_listing(), headers=headers, cookies=cookies)
        assert r.status_code == 201
        listing_id = r.json()["listing"]["id"]

        profile = await get_agent_profile(registered_agent["id"])
        assert profile.listings_count == 1

        # Delete it
        r2 = await client.delete(f"/api/listings/{listing_id}", headers=headers, cookies=cookies)
        assert r2.status_code == 200

        profile = await get_agent_profile(registered_agent["id"])
        assert profile.listings_count == 0


# ==========================================================================
# DEALS COMPLETED
# ==========================================================================

class TestDealsCompleted:

    async def test_deals_completed_increments_on_fulfilled(self, client, registered_buyer, registered_agent, admin_user):
        """Marking demand as fulfilled should increment agent's deals_completed."""
        # Create demand
        buyer_cookies = await login_user(client, registered_buyer["email"], registered_buyer["password"])
        bh, bc = await auth_headers_and_cookies(buyer_cookies)
        r = await client.post("/api/demands", json=make_demand(), headers=bh, cookies=bc)
        assert r.status_code == 201
        demand_id = r.json()["demand"]["id"]

        # Approve agent and claim
        admin_cookies = await login_user(client, admin_user["email"], admin_user["password"])
        await approve_agent(client, admin_cookies, registered_agent["id"])
        agent_cookies = await login_user(client, registered_agent["email"], registered_agent["password"])
        ah, ac = await auth_headers_and_cookies(agent_cookies)
        r2 = await client.post(f"/api/demands/{demand_id}/claim", headers=ah, cookies=ac)
        assert r2.status_code == 200

        # Before fulfillment
        profile = await get_agent_profile(registered_agent["id"])
        assert profile.deals_completed == 0

        # Buyer marks fulfilled
        r3 = await client.put(
            f"/api/demands/{demand_id}/status",
            json={"status": "fulfilled"},
            headers=bh, cookies=bc,
        )
        assert r3.status_code == 200

        # After fulfillment
        profile = await get_agent_profile(registered_agent["id"])
        assert profile.deals_completed == 1

    async def test_deals_completed_not_incremented_on_closed(self, client, registered_buyer, registered_agent, admin_user):
        """Closing a demand should NOT increment deals_completed."""
        buyer_cookies = await login_user(client, registered_buyer["email"], registered_buyer["password"])
        bh, bc = await auth_headers_and_cookies(buyer_cookies)
        r = await client.post("/api/demands", json=make_demand(), headers=bh, cookies=bc)
        demand_id = r.json()["demand"]["id"]

        admin_cookies = await login_user(client, admin_user["email"], admin_user["password"])
        await approve_agent(client, admin_cookies, registered_agent["id"])
        agent_cookies = await login_user(client, registered_agent["email"], registered_agent["password"])
        ah, ac = await auth_headers_and_cookies(agent_cookies)
        await client.post(f"/api/demands/{demand_id}/claim", headers=ah, cookies=ac)

        # Buyer closes (not fulfilled)
        r2 = await client.put(
            f"/api/demands/{demand_id}/status",
            json={"status": "closed"},
            headers=bh, cookies=bc,
        )
        assert r2.status_code == 200

        profile = await get_agent_profile(registered_agent["id"])
        assert profile.deals_completed == 0


# ==========================================================================
# PROMOTION COUNTERS
# ==========================================================================

class TestPromotionCounters:

    async def test_views_during_promotion_increments(self, client, registered_agent, admin_user):
        """Viewing a promoted listing should increment views_during_promotion."""
        admin_cookies = await login_user(client, admin_user["email"], admin_user["password"])
        await approve_agent(client, admin_cookies, registered_agent["id"])

        agent_cookies = await login_user(client, registered_agent["email"], registered_agent["password"])
        headers, cookies = await auth_headers_and_cookies(agent_cookies)

        # Create listing
        r = await client.post("/api/listings", json=make_listing(), headers=headers, cookies=cookies)
        listing_id = r.json()["listing"]["id"]

        # Give credits and promote
        await give_credits(registered_agent["id"], 50)
        r2 = await client.post(
            f"/api/promotions/{listing_id}/promote",
            json={"tier": "featured"},
            headers=headers, cookies=cookies,
        )
        assert r2.status_code == 200

        # Check initial promotion counter
        promo = await get_active_promotion(listing_id)
        assert promo is not None
        assert promo.views_during_promotion == 0

        # View the listing anonymously (public view increments count)
        client.cookies.clear()
        await client.get(f"/api/listings/{listing_id}")
        await client.get(f"/api/listings/{listing_id}")

        # Check views_during_promotion incremented
        promo = await get_active_promotion(listing_id)
        assert promo.views_during_promotion == 2

    async def test_leads_during_promotion_increments(self, client, registered_agent, admin_user, registered_buyer):
        """Creating a lead on a promoted listing should increment leads_during_promotion."""
        admin_cookies = await login_user(client, admin_user["email"], admin_user["password"])
        await approve_agent(client, admin_cookies, registered_agent["id"])

        agent_cookies = await login_user(client, registered_agent["email"], registered_agent["password"])
        headers, cookies = await auth_headers_and_cookies(agent_cookies)

        # Create listing
        r = await client.post("/api/listings", json=make_listing(), headers=headers, cookies=cookies)
        listing_id = r.json()["listing"]["id"]

        # Give credits and promote
        await give_credits(registered_agent["id"], 50)
        r2 = await client.post(
            f"/api/promotions/{listing_id}/promote",
            json={"tier": "featured"},
            headers=headers, cookies=cookies,
        )
        assert r2.status_code == 200

        # Create a lead on the promoted listing
        buyer_cookies = await login_user(client, registered_buyer["email"], registered_buyer["password"])
        bh, bc = await auth_headers_and_cookies(buyer_cookies)
        r3 = await client.post("/api/leads", json={
            "listing_id": listing_id,
            "interaction_type": "whatsapp",
        }, headers=bh, cookies=bc)
        assert r3.status_code == 201

        # Check leads_during_promotion incremented
        promo = await get_active_promotion(listing_id)
        assert promo.leads_during_promotion == 1

        # Create another lead (different interaction type)
        r4 = await client.post("/api/leads", json={
            "listing_id": listing_id,
            "interaction_type": "phone",
        }, headers=bh, cookies=bc)
        assert r4.status_code == 201

        promo = await get_active_promotion(listing_id)
        assert promo.leads_during_promotion == 2

    async def test_counters_not_incremented_without_promotion(self, client, registered_agent, admin_user, registered_buyer):
        """Views and leads on non-promoted listings should NOT create promotion records."""
        admin_cookies = await login_user(client, admin_user["email"], admin_user["password"])
        await approve_agent(client, admin_cookies, registered_agent["id"])

        agent_cookies = await login_user(client, registered_agent["email"], registered_agent["password"])
        headers, cookies = await auth_headers_and_cookies(agent_cookies)

        # Create listing (no promotion)
        r = await client.post("/api/listings", json=make_listing(), headers=headers, cookies=cookies)
        listing_id = r.json()["listing"]["id"]

        # View it
        client.cookies.clear()
        await client.get(f"/api/listings/{listing_id}")

        # Create a lead
        buyer_cookies = await login_user(client, registered_buyer["email"], registered_buyer["password"])
        bh, bc = await auth_headers_and_cookies(buyer_cookies)
        await client.post("/api/leads", json={
            "listing_id": listing_id,
            "interaction_type": "whatsapp",
        }, headers=bh, cookies=bc)

        # No promotion record should exist
        promo = await get_active_promotion(listing_id)
        assert promo is None
