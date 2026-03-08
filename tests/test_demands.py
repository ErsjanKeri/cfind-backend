"""
Buyer demand lifecycle tests.

Covers:
- Create demand (happy path, validation errors)
- Budget validation (max >= min)
- Get active demands (agent view with filters)
- Claim demand (agent claims → status "assigned")
- Double-claim prevention (second agent → 409)
- Status transitions:
  - active → closed (buyer cancels)
  - assigned → fulfilled (buyer marks done)
  - assigned → closed (buyer cancels after assignment)
  - active → fulfilled (INVALID → blocked)
- Delete demand (only active can be deleted)
- Get buyer's demands
- Get agent's claimed demands
- Role enforcement (only buyers create, only agents claim)
"""

import uuid

from tests.conftest import login_user, auth_headers_and_cookies, approve_agent, TestSessionLocal


def make_demand(**overrides):
    base = {
        "country_code": "al",
        "budget_min_eur": 50000,
        "budget_max_eur": 200000,
        "category": "restaurant",
        "preferred_city_en": "Tirana",
        "description": "Looking for a profitable restaurant in Tirana with good foot traffic and loyal clientele.",
        "demand_type": "investor",
    }
    base.update(overrides)
    return base


# ==========================================================================
# CREATE DEMAND
# ==========================================================================

class TestCreateDemand:

    async def test_create_demand_success(self, client, registered_buyer):
        cookies = await login_user(client, registered_buyer["email"], registered_buyer["password"])
        headers, cookies = await auth_headers_and_cookies(cookies)

        r = await client.post("/api/demands", json=make_demand(), headers=headers, cookies=cookies)
        assert r.status_code == 201
        demand = r.json()["demand"]
        assert demand["status"] == "active"
        assert demand["category"] == "restaurant"
        assert float(demand["budget_min_eur"]) == 50000
        assert float(demand["budget_max_eur"]) == 200000

    async def test_create_demand_seeking_funding_type(self, client, registered_buyer):
        cookies = await login_user(client, registered_buyer["email"], registered_buyer["password"])
        headers, cookies = await auth_headers_and_cookies(cookies)

        r = await client.post("/api/demands", json=make_demand(demand_type="seeking_funding"),
                              headers=headers, cookies=cookies)
        assert r.status_code == 201
        assert r.json()["demand"]["demand_type"] == "seeking_funding"

    async def test_create_demand_budget_max_less_than_min(self, client, registered_buyer):
        """budget_max_eur < budget_min_eur should fail validation."""
        cookies = await login_user(client, registered_buyer["email"], registered_buyer["password"])
        headers, cookies = await auth_headers_and_cookies(cookies)

        r = await client.post("/api/demands", json=make_demand(
            budget_min_eur=200000, budget_max_eur=50000,
        ), headers=headers, cookies=cookies)
        assert r.status_code == 422

    async def test_create_demand_short_description(self, client, registered_buyer):
        """Description must be at least 20 characters."""
        cookies = await login_user(client, registered_buyer["email"], registered_buyer["password"])
        headers, cookies = await auth_headers_and_cookies(cookies)

        r = await client.post("/api/demands", json=make_demand(description="Too short"),
                              headers=headers, cookies=cookies)
        assert r.status_code == 422

    async def test_agent_cannot_create_demand(self, client, registered_agent):
        """Only buyers can create demands."""
        cookies = await login_user(client, registered_agent["email"], registered_agent["password"])
        headers, cookies = await auth_headers_and_cookies(cookies)

        r = await client.post("/api/demands", json=make_demand(), headers=headers, cookies=cookies)
        assert r.status_code == 403

    async def test_create_demand_with_optional_area(self, client, registered_buyer):
        cookies = await login_user(client, registered_buyer["email"], registered_buyer["password"])
        headers, cookies = await auth_headers_and_cookies(cookies)

        r = await client.post("/api/demands", json=make_demand(preferred_area="Blloku"),
                              headers=headers, cookies=cookies)
        assert r.status_code == 201
        assert r.json()["demand"]["preferred_area"] == "Blloku"


# ==========================================================================
# GET DEMANDS (Agent view)
# ==========================================================================

class TestGetActiveDemands:

    async def test_verified_agent_sees_active_demands(self, client, registered_buyer, registered_agent, admin_user):
        """Verified agent can see active demands."""
        # Buyer creates a demand
        buyer_cookies = await login_user(client, registered_buyer["email"], registered_buyer["password"])
        bh, bc = await auth_headers_and_cookies(buyer_cookies)
        await client.post("/api/demands", json=make_demand(), headers=bh, cookies=bc)

        # Approve agent
        admin_cookies = await login_user(client, admin_user["email"], admin_user["password"])
        await approve_agent(client, admin_cookies, registered_agent["id"])

        # Agent searches demands
        agent_cookies = await login_user(client, registered_agent["email"], registered_agent["password"])
        r = await client.get("/api/demands", params={"country_code": "al"}, cookies=agent_cookies)
        assert r.status_code == 200
        assert r.json()["total"] >= 1

    async def test_filter_demands_by_category(self, client, registered_buyer, registered_agent, admin_user):
        buyer_cookies = await login_user(client, registered_buyer["email"], registered_buyer["password"])
        bh, bc = await auth_headers_and_cookies(buyer_cookies)
        await client.post("/api/demands", json=make_demand(category="bar"), headers=bh, cookies=bc)

        admin_cookies = await login_user(client, admin_user["email"], admin_user["password"])
        await approve_agent(client, admin_cookies, registered_agent["id"])

        agent_cookies = await login_user(client, registered_agent["email"], registered_agent["password"])

        # Search for bar — should find it
        r = await client.get("/api/demands", params={"country_code": "al", "category": "bar"},
                             cookies=agent_cookies)
        assert r.status_code == 200
        assert r.json()["total"] >= 1

        # Search for gym — should not find it
        r2 = await client.get("/api/demands", params={"country_code": "al", "category": "gym"},
                              cookies=agent_cookies)
        assert r2.status_code == 200
        assert r2.json()["total"] == 0


# ==========================================================================
# CLAIM DEMAND
# ==========================================================================

class TestClaimDemand:

    async def _create_demand_and_approve_agent(self, client, registered_buyer, registered_agent, admin_user):
        """Helper: create a demand and approve the agent. Returns demand_id."""
        buyer_cookies = await login_user(client, registered_buyer["email"], registered_buyer["password"])
        bh, bc = await auth_headers_and_cookies(buyer_cookies)
        r = await client.post("/api/demands", json=make_demand(), headers=bh, cookies=bc)
        demand_id = r.json()["demand"]["id"]

        admin_cookies = await login_user(client, admin_user["email"], admin_user["password"])
        await approve_agent(client, admin_cookies, registered_agent["id"])

        return demand_id

    async def test_agent_claims_demand(self, client, registered_buyer, registered_agent, admin_user):
        demand_id = await self._create_demand_and_approve_agent(
            client, registered_buyer, registered_agent, admin_user
        )

        agent_cookies = await login_user(client, registered_agent["email"], registered_agent["password"])
        headers, cookies = await auth_headers_and_cookies(agent_cookies)

        r = await client.post(f"/api/demands/{demand_id}/claim", headers=headers, cookies=cookies)
        assert r.status_code == 200
        assert r.json()["demand"]["status"] == "assigned"
        assert r.json()["demand"]["assigned_agent_id"] == registered_agent["id"]

    async def test_double_claim_rejected(self, client, registered_buyer, registered_agent, admin_user, test_password):
        """Second agent trying to claim an already-claimed demand gets 409."""
        demand_id = await self._create_demand_and_approve_agent(
            client, registered_buyer, registered_agent, admin_user
        )

        # First agent claims
        agent_cookies = await login_user(client, registered_agent["email"], registered_agent["password"])
        ah, ac = await auth_headers_and_cookies(agent_cookies)
        r1 = await client.post(f"/api/demands/{demand_id}/claim", headers=ah, cookies=ac)
        assert r1.status_code == 200

        # Create and approve a second agent
        email2 = f"agent2_{uuid.uuid4().hex[:8]}@test.com"
        files = {
            "license_document": ("license.pdf", b"fake-pdf", "application/pdf"),
            "company_document": ("company.pdf", b"fake-pdf", "application/pdf"),
            "id_document": ("id.pdf", b"fake-pdf", "application/pdf"),
        }
        reg2 = await client.post("/api/auth/register", data={
            "name": "Agent Two", "email": email2, "password": test_password,
            "role": "agent", "company_name": "Agency Two", "operating_country": "al",
            "license_number": "LIC-TWO", "phone": "+355690000001", "whatsapp": "+355690000001",
        }, files=files)
        agent2_id = reg2.json()["user_id"]

        # Verify email + approve
        from sqlalchemy import update
        from app.models.user import User
        async with TestSessionLocal() as session:
            await session.execute(
                update(User).where(User.id == uuid.UUID(agent2_id)).values(email_verified=True)
            )
            await session.commit()
        admin_cookies = await login_user(client, admin_user["email"], admin_user["password"])
        await approve_agent(client, admin_cookies, agent2_id)

        # Second agent tries to claim — should fail
        agent2_cookies = await login_user(client, email2, test_password)
        ah2, ac2 = await auth_headers_and_cookies(agent2_cookies)
        r2 = await client.post(f"/api/demands/{demand_id}/claim", headers=ah2, cookies=ac2)
        assert r2.status_code == 409

    async def test_buyer_cannot_claim_demand(self, client, registered_buyer, registered_agent, admin_user):
        """Buyer role cannot claim demands."""
        demand_id = await self._create_demand_and_approve_agent(
            client, registered_buyer, registered_agent, admin_user
        )

        buyer_cookies = await login_user(client, registered_buyer["email"], registered_buyer["password"])
        headers, cookies = await auth_headers_and_cookies(buyer_cookies)

        r = await client.post(f"/api/demands/{demand_id}/claim", headers=headers, cookies=cookies)
        assert r.status_code == 403


# ==========================================================================
# STATUS TRANSITIONS
# ==========================================================================

class TestDemandStatusTransitions:

    async def _setup(self, client, registered_buyer, registered_agent, admin_user):
        """Create demand + approve agent. Returns (demand_id, buyer_cookies, agent_cookies)."""
        buyer_cookies = await login_user(client, registered_buyer["email"], registered_buyer["password"])
        bh, bc = await auth_headers_and_cookies(buyer_cookies)
        r = await client.post("/api/demands", json=make_demand(), headers=bh, cookies=bc)
        demand_id = r.json()["demand"]["id"]

        admin_cookies = await login_user(client, admin_user["email"], admin_user["password"])
        await approve_agent(client, admin_cookies, registered_agent["id"])

        agent_cookies = await login_user(client, registered_agent["email"], registered_agent["password"])

        return demand_id, buyer_cookies, agent_cookies

    async def test_active_to_closed(self, client, registered_buyer, registered_agent, admin_user):
        """Buyer cancels active demand → closed."""
        demand_id, buyer_cookies, _ = await self._setup(
            client, registered_buyer, registered_agent, admin_user
        )
        headers, cookies = await auth_headers_and_cookies(buyer_cookies)

        r = await client.put(f"/api/demands/{demand_id}/status",
                             json={"status": "closed"}, headers=headers, cookies=cookies)
        assert r.status_code == 200
        assert r.json()["demand"]["status"] == "closed"

    async def test_assigned_to_fulfilled(self, client, registered_buyer, registered_agent, admin_user):
        """Buyer marks assigned demand as fulfilled."""
        demand_id, buyer_cookies, agent_cookies = await self._setup(
            client, registered_buyer, registered_agent, admin_user
        )

        # Agent claims
        ah, ac = await auth_headers_and_cookies(agent_cookies)
        await client.post(f"/api/demands/{demand_id}/claim", headers=ah, cookies=ac)

        # Buyer marks fulfilled
        bh, bc = await auth_headers_and_cookies(buyer_cookies)
        r = await client.put(f"/api/demands/{demand_id}/status",
                             json={"status": "fulfilled"}, headers=bh, cookies=bc)
        assert r.status_code == 200
        assert r.json()["demand"]["status"] == "fulfilled"

    async def test_assigned_to_closed(self, client, registered_buyer, registered_agent, admin_user):
        """Buyer cancels assigned demand → closed."""
        demand_id, buyer_cookies, agent_cookies = await self._setup(
            client, registered_buyer, registered_agent, admin_user
        )

        # Agent claims
        ah, ac = await auth_headers_and_cookies(agent_cookies)
        await client.post(f"/api/demands/{demand_id}/claim", headers=ah, cookies=ac)

        # Buyer closes
        bh, bc = await auth_headers_and_cookies(buyer_cookies)
        r = await client.put(f"/api/demands/{demand_id}/status",
                             json={"status": "closed"}, headers=bh, cookies=bc)
        assert r.status_code == 200
        assert r.json()["demand"]["status"] == "closed"

    async def test_invalid_transition_active_to_fulfilled(self, client, registered_buyer, registered_agent, admin_user):
        """Cannot go from active → fulfilled (must be assigned first)."""
        demand_id, buyer_cookies, _ = await self._setup(
            client, registered_buyer, registered_agent, admin_user
        )
        headers, cookies = await auth_headers_and_cookies(buyer_cookies)

        r = await client.put(f"/api/demands/{demand_id}/status",
                             json={"status": "fulfilled"}, headers=headers, cookies=cookies)
        assert r.status_code == 400
        assert "cannot transition" in r.json()["detail"].lower()


# ==========================================================================
# DELETE DEMAND
# ==========================================================================

class TestDeleteDemand:

    async def test_delete_active_demand(self, client, registered_buyer):
        cookies = await login_user(client, registered_buyer["email"], registered_buyer["password"])
        headers, cookies = await auth_headers_and_cookies(cookies)

        r = await client.post("/api/demands", json=make_demand(), headers=headers, cookies=cookies)
        demand_id = r.json()["demand"]["id"]

        r2 = await client.delete(f"/api/demands/{demand_id}", headers=headers, cookies=cookies)
        assert r2.status_code == 200

    async def test_delete_assigned_demand_blocked(self, client, registered_buyer, registered_agent, admin_user):
        """Cannot delete an assigned demand (for historical tracking)."""
        buyer_cookies = await login_user(client, registered_buyer["email"], registered_buyer["password"])
        bh, bc = await auth_headers_and_cookies(buyer_cookies)
        r = await client.post("/api/demands", json=make_demand(), headers=bh, cookies=bc)
        demand_id = r.json()["demand"]["id"]

        # Agent claims
        admin_cookies = await login_user(client, admin_user["email"], admin_user["password"])
        await approve_agent(client, admin_cookies, registered_agent["id"])
        agent_cookies = await login_user(client, registered_agent["email"], registered_agent["password"])
        ah, ac = await auth_headers_and_cookies(agent_cookies)
        await client.post(f"/api/demands/{demand_id}/claim", headers=ah, cookies=ac)

        # Buyer tries to delete — should fail
        r2 = await client.delete(f"/api/demands/{demand_id}", headers=bh, cookies=bc)
        assert r2.status_code == 400

    async def test_non_owner_cannot_delete_demand(self, client, registered_buyer, test_password):
        """Buyer cannot delete another buyer's demand."""
        # First buyer creates demand
        buyer_cookies = await login_user(client, registered_buyer["email"], registered_buyer["password"])
        bh, bc = await auth_headers_and_cookies(buyer_cookies)
        r = await client.post("/api/demands", json=make_demand(), headers=bh, cookies=bc)
        demand_id = r.json()["demand"]["id"]

        # Register a second buyer
        email2 = f"buyer2_{uuid.uuid4().hex[:8]}@test.com"
        await client.post("/api/auth/register", data={
            "name": "Buyer Two", "email": email2, "password": test_password, "role": "buyer",
        })
        from sqlalchemy import update
        from app.models.user import User
        async with TestSessionLocal() as session:
            await session.execute(
                update(User).where(User.email == email2).values(email_verified=True)
            )
            await session.commit()

        buyer2_cookies = await login_user(client, email2, test_password)
        bh2, bc2 = await auth_headers_and_cookies(buyer2_cookies)
        r2 = await client.delete(f"/api/demands/{demand_id}", headers=bh2, cookies=bc2)
        assert r2.status_code == 403


# ==========================================================================
# GET BUYER/AGENT DEMANDS
# ==========================================================================

class TestGetDemandLists:

    async def test_buyer_sees_own_demands(self, client, registered_buyer):
        cookies = await login_user(client, registered_buyer["email"], registered_buyer["password"])
        headers, cookies = await auth_headers_and_cookies(cookies)

        # Create two demands
        await client.post("/api/demands", json=make_demand(), headers=headers, cookies=cookies)
        await client.post("/api/demands", json=make_demand(category="bar"), headers=headers, cookies=cookies)

        r = await client.get(f"/api/demands/buyer/{registered_buyer['id']}", cookies=cookies)
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 2
        assert data["page"] == 1
        assert data["limit"] == 20
        assert data["total_pages"] == 1

    async def test_buyer_demands_pagination(self, client, registered_buyer):
        """Buyer demands endpoint respects page/limit params."""
        cookies = await login_user(client, registered_buyer["email"], registered_buyer["password"])
        headers, cookies = await auth_headers_and_cookies(cookies)

        # Create 3 demands
        for cat in ["restaurant", "bar", "cafe"]:
            await client.post("/api/demands", json=make_demand(category=cat), headers=headers, cookies=cookies)

        # Page 1, limit 2
        r = await client.get(
            f"/api/demands/buyer/{registered_buyer['id']}",
            params={"page": 1, "limit": 2},
            cookies=cookies,
        )
        assert r.status_code == 200
        data = r.json()
        assert len(data["demands"]) == 2
        assert data["total"] == 3
        assert data["total_pages"] == 2

        # Page 2
        r2 = await client.get(
            f"/api/demands/buyer/{registered_buyer['id']}",
            params={"page": 2, "limit": 2},
            cookies=cookies,
        )
        assert r2.status_code == 200
        assert len(r2.json()["demands"]) == 1

    async def test_agent_sees_claimed_demands(self, client, registered_buyer, registered_agent, admin_user):
        buyer_cookies = await login_user(client, registered_buyer["email"], registered_buyer["password"])
        bh, bc = await auth_headers_and_cookies(buyer_cookies)
        r = await client.post("/api/demands", json=make_demand(), headers=bh, cookies=bc)
        demand_id = r.json()["demand"]["id"]

        admin_cookies = await login_user(client, admin_user["email"], admin_user["password"])
        await approve_agent(client, admin_cookies, registered_agent["id"])

        agent_cookies = await login_user(client, registered_agent["email"], registered_agent["password"])
        ah, ac = await auth_headers_and_cookies(agent_cookies)
        await client.post(f"/api/demands/{demand_id}/claim", headers=ah, cookies=ac)

        r2 = await client.get(f"/api/demands/agent/{registered_agent['id']}", cookies=agent_cookies)
        assert r2.status_code == 200
        data = r2.json()
        assert data["total"] >= 1
        assert data["page"] == 1
        assert data["limit"] == 20
        assert "total_pages" in data
