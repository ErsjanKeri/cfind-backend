"""
Lead and saved listing tests.

Covers:
- Create lead (whatsapp, phone, email)
- Duplicate lead prevention (same buyer + listing + interaction_type → 409)
- Same buyer, different interaction types → all succeed
- Get agent leads (agent sees buyer contact info)
- Get buyer leads (buyer sees agent contact info)
- Lead on non-existent listing → 404
- Toggle saved listing (save/unsave)
- Get saved listings
- Role enforcement (only buyer can save, only buyer/agent can see own leads)
"""

import uuid

from tests.conftest import login_user, auth_headers_and_cookies, approve_agent


def make_listing(**overrides):
    base = {
        "country_code": "al",
        "real_business_name": "Lead Test Business",
        "real_location_address": "Rruga Leads 1, Tirana",
        "public_title_en": "Business For Lead Testing",
        "public_description_en": "A great business to test lead creation and interaction tracking flows.",
        "category": "restaurant",
        "public_location_city_en": "Tirana",
        "asking_price_eur": 100000,
        "monthly_revenue_eur": 10000,
        "images": [{"url": "https://test-bucket.s3.amazonaws.com/fake/img.jpg", "order": 0}],
    }
    base.update(overrides)
    return base


async def setup_listing(client, registered_agent, admin_user):
    """Helper: approve agent and create a listing. Returns listing_id."""
    admin_cookies = await login_user(client, admin_user["email"], admin_user["password"])
    await approve_agent(client, admin_cookies, registered_agent["id"])

    agent_cookies = await login_user(client, registered_agent["email"], registered_agent["password"])
    headers, cookies = await auth_headers_and_cookies(agent_cookies)

    r = await client.post("/api/listings", json=make_listing(), headers=headers, cookies=cookies)
    assert r.status_code == 201
    return r.json()["listing"]["id"]


# ==========================================================================
# CREATE LEADS
# ==========================================================================

class TestCreateLead:

    async def test_create_lead_whatsapp(self, client, registered_agent, admin_user, registered_buyer):
        listing_id = await setup_listing(client, registered_agent, admin_user)

        buyer_cookies = await login_user(client, registered_buyer["email"], registered_buyer["password"])
        headers, cookies = await auth_headers_and_cookies(buyer_cookies)

        r = await client.post("/api/leads", json={
            "listing_id": listing_id,
            "interaction_type": "whatsapp",
        }, headers=headers, cookies=cookies)
        assert r.status_code == 201

    async def test_create_lead_phone(self, client, registered_agent, admin_user, registered_buyer):
        listing_id = await setup_listing(client, registered_agent, admin_user)

        buyer_cookies = await login_user(client, registered_buyer["email"], registered_buyer["password"])
        headers, cookies = await auth_headers_and_cookies(buyer_cookies)

        r = await client.post("/api/leads", json={
            "listing_id": listing_id,
            "interaction_type": "phone",
        }, headers=headers, cookies=cookies)
        assert r.status_code == 201

    async def test_create_lead_email(self, client, registered_agent, admin_user, registered_buyer):
        listing_id = await setup_listing(client, registered_agent, admin_user)

        buyer_cookies = await login_user(client, registered_buyer["email"], registered_buyer["password"])
        headers, cookies = await auth_headers_and_cookies(buyer_cookies)

        r = await client.post("/api/leads", json={
            "listing_id": listing_id,
            "interaction_type": "email",
        }, headers=headers, cookies=cookies)
        assert r.status_code == 201

    async def test_duplicate_lead_rejected(self, client, registered_agent, admin_user, registered_buyer):
        """Same buyer + same listing + same interaction_type → 409."""
        listing_id = await setup_listing(client, registered_agent, admin_user)

        buyer_cookies = await login_user(client, registered_buyer["email"], registered_buyer["password"])
        headers, cookies = await auth_headers_and_cookies(buyer_cookies)

        # First lead succeeds
        r1 = await client.post("/api/leads", json={
            "listing_id": listing_id, "interaction_type": "whatsapp",
        }, headers=headers, cookies=cookies)
        assert r1.status_code == 201

        # Duplicate fails
        r2 = await client.post("/api/leads", json={
            "listing_id": listing_id, "interaction_type": "whatsapp",
        }, headers=headers, cookies=cookies)
        assert r2.status_code == 409

    async def test_same_buyer_different_interaction_types(self, client, registered_agent, admin_user, registered_buyer):
        """Same buyer can create leads via all 3 interaction types for same listing."""
        listing_id = await setup_listing(client, registered_agent, admin_user)

        buyer_cookies = await login_user(client, registered_buyer["email"], registered_buyer["password"])
        headers, cookies = await auth_headers_and_cookies(buyer_cookies)

        for itype in ["whatsapp", "phone", "email"]:
            r = await client.post("/api/leads", json={
                "listing_id": listing_id, "interaction_type": itype,
            }, headers=headers, cookies=cookies)
            assert r.status_code == 201, f"Lead creation failed for {itype}: {r.text}"

    async def test_lead_on_nonexistent_listing(self, client, registered_buyer):
        buyer_cookies = await login_user(client, registered_buyer["email"], registered_buyer["password"])
        headers, cookies = await auth_headers_and_cookies(buyer_cookies)

        r = await client.post("/api/leads", json={
            "listing_id": str(uuid.uuid4()),
            "interaction_type": "whatsapp",
        }, headers=headers, cookies=cookies)
        assert r.status_code in (400, 404)


# ==========================================================================
# GET LEADS
# ==========================================================================

class TestGetLeads:

    async def test_agent_sees_leads_with_buyer_info(self, client, registered_agent, admin_user, registered_buyer):
        """Agent's lead list includes buyer name/email."""
        listing_id = await setup_listing(client, registered_agent, admin_user)

        # Buyer creates a lead
        buyer_cookies = await login_user(client, registered_buyer["email"], registered_buyer["password"])
        bh, bc = await auth_headers_and_cookies(buyer_cookies)
        await client.post("/api/leads", json={
            "listing_id": listing_id, "interaction_type": "whatsapp",
        }, headers=bh, cookies=bc)

        # Agent views leads
        agent_cookies = await login_user(client, registered_agent["email"], registered_agent["password"])
        r = await client.get(f"/api/leads/agent/{registered_agent['id']}", cookies=agent_cookies)
        assert r.status_code == 200
        leads = r.json()["leads"]
        assert len(leads) >= 1
        assert leads[0]["buyer_name"] is not None

    async def test_buyer_sees_leads_with_agent_info(self, client, registered_agent, admin_user, registered_buyer):
        """Buyer's lead list includes agent contact details."""
        listing_id = await setup_listing(client, registered_agent, admin_user)

        buyer_cookies = await login_user(client, registered_buyer["email"], registered_buyer["password"])
        bh, bc = await auth_headers_and_cookies(buyer_cookies)
        await client.post("/api/leads", json={
            "listing_id": listing_id, "interaction_type": "phone",
        }, headers=bh, cookies=bc)

        r = await client.get(f"/api/leads/buyer/{registered_buyer['id']}", cookies=buyer_cookies)
        assert r.status_code == 200
        leads = r.json()["leads"]
        assert len(leads) >= 1
        assert leads[0]["agent_name"] is not None

    async def test_buyer_cannot_see_other_buyer_leads(self, client, registered_buyer):
        """Buyer can't access another buyer's lead list."""
        buyer_cookies = await login_user(client, registered_buyer["email"], registered_buyer["password"])
        fake_buyer_id = str(uuid.uuid4())
        r = await client.get(f"/api/leads/buyer/{fake_buyer_id}", cookies=buyer_cookies)
        assert r.status_code == 403


# ==========================================================================
# SAVED LISTINGS
# ==========================================================================

class TestSavedListings:

    async def test_toggle_save_listing(self, client, registered_agent, admin_user, registered_buyer):
        """Toggle save: first call saves, second call unsaves."""
        listing_id = await setup_listing(client, registered_agent, admin_user)

        buyer_cookies = await login_user(client, registered_buyer["email"], registered_buyer["password"])
        headers, cookies = await auth_headers_and_cookies(buyer_cookies)

        # Save
        r1 = await client.post(f"/api/leads/saved/{listing_id}", headers=headers, cookies=cookies)
        assert r1.status_code == 200
        assert r1.json()["is_saved"] is True

        # Unsave
        r2 = await client.post(f"/api/leads/saved/{listing_id}", headers=headers, cookies=cookies)
        assert r2.status_code == 200
        assert r2.json()["is_saved"] is False

    async def test_get_saved_listings(self, client, registered_agent, admin_user, registered_buyer):
        listing_id = await setup_listing(client, registered_agent, admin_user)

        buyer_cookies = await login_user(client, registered_buyer["email"], registered_buyer["password"])
        headers, cookies = await auth_headers_and_cookies(buyer_cookies)

        # Save a listing
        await client.post(f"/api/leads/saved/{listing_id}", headers=headers, cookies=cookies)

        # Get saved listings
        r = await client.get("/api/leads/saved", cookies=buyer_cookies)
        assert r.status_code == 200
        saved = r.json()["listings"]
        assert len(saved) >= 1
        saved_ids = [s["id"] for s in saved]
        assert listing_id in saved_ids

    async def test_agent_cannot_save_listings(self, client, registered_agent, admin_user):
        """Only buyers can save listings."""
        listing_id = await setup_listing(client, registered_agent, admin_user)

        agent_cookies = await login_user(client, registered_agent["email"], registered_agent["password"])
        headers, cookies = await auth_headers_and_cookies(agent_cookies)

        r = await client.post(f"/api/leads/saved/{listing_id}", headers=headers, cookies=cookies)
        assert r.status_code == 403
