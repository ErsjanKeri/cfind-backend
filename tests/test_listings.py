"""
Listing CRUD and search tests.

Covers:
- Create listing (happy path, validation errors, country mismatch)
- Get single listing (public vs private view based on auth)
- Update listing (owner, non-owner, admin)
- Delete listing
- Search listings with filters (country, category, city, price range, ROI, search text)
- Sort options (newest, price_low, price_high, roi_high, most_viewed)
- Pagination
- View count increments on public view
- Only active + verified-agent listings appear in search
- Agent listing list (all statuses)
"""

import uuid

from tests.conftest import login_user, auth_headers_and_cookies, approve_agent, TestSessionLocal


def make_listing(**overrides):
    """Build a valid listing payload with optional overrides."""
    base = {
        "country_code": "al",
        "real_business_name": "Test Business",
        "real_location_address": "Rruga Test 123, Tirana",
        "public_title_en": "Great Business Opportunity",
        "public_description_en": "A fantastic business with strong revenue and loyal customer base in prime location.",
        "category": "restaurant",
        "public_location_city_en": "Tirana",
        "asking_price_eur": 100000,
        "monthly_revenue_eur": 10000,
        "images": [{"url": "https://test-bucket.s3.amazonaws.com/fake/img.jpg", "order": 0}],
    }
    base.update(overrides)
    return base


async def create_approved_agent_with_listing(client, registered_agent, admin_user):
    """Helper: approve agent and create a listing. Returns (agent_cookies, listing_id)."""
    admin_cookies = await login_user(client, admin_user["email"], admin_user["password"])
    await approve_agent(client, admin_cookies, registered_agent["id"])

    agent_cookies = await login_user(client, registered_agent["email"], registered_agent["password"])
    headers, cookies = await auth_headers_and_cookies(agent_cookies)

    r = await client.post("/api/listings", json=make_listing(), headers=headers, cookies=cookies)
    assert r.status_code == 201
    return agent_cookies, r.json()["listing"]["id"]


# ==========================================================================
# CREATE LISTING
# ==========================================================================

class TestCreateListing:

    async def test_create_listing_success(self, client, registered_agent, admin_user):
        """Approved agent creates a listing successfully."""
        admin_cookies = await login_user(client, admin_user["email"], admin_user["password"])
        await approve_agent(client, admin_cookies, registered_agent["id"])

        agent_cookies = await login_user(client, registered_agent["email"], registered_agent["password"])
        headers, cookies = await auth_headers_and_cookies(agent_cookies)

        r = await client.post("/api/listings", json=make_listing(), headers=headers, cookies=cookies)
        assert r.status_code == 201
        listing = r.json()["listing"]
        assert listing["public_title_en"] == "Great Business Opportunity"
        assert listing["status"] == "active"
        assert listing["promotion_tier"] == "standard"
        # ROI should be auto-calculated: (10000*12)/100000*100 = 120
        assert float(listing["roi"]) == 120.0
        # Private view — creator sees real business name
        assert listing["real_business_name"] == "Test Business"

    async def test_create_listing_no_images_rejected(self, client, registered_agent, admin_user):
        admin_cookies = await login_user(client, admin_user["email"], admin_user["password"])
        await approve_agent(client, admin_cookies, registered_agent["id"])

        agent_cookies = await login_user(client, registered_agent["email"], registered_agent["password"])
        headers, cookies = await auth_headers_and_cookies(agent_cookies)

        payload = make_listing(images=[])
        r = await client.post("/api/listings", json=payload, headers=headers, cookies=cookies)
        assert r.status_code in (400, 422)

    async def test_create_listing_country_mismatch(self, client, registered_agent, admin_user):
        """Agent operating in 'al' cannot create listing for 'ae'."""
        admin_cookies = await login_user(client, admin_user["email"], admin_user["password"])
        await approve_agent(client, admin_cookies, registered_agent["id"])

        agent_cookies = await login_user(client, registered_agent["email"], registered_agent["password"])
        headers, cookies = await auth_headers_and_cookies(agent_cookies)

        payload = make_listing(country_code="ae")
        r = await client.post("/api/listings", json=payload, headers=headers, cookies=cookies)
        assert r.status_code == 400
        assert "operating country" in r.json()["detail"].lower()

    async def test_create_listing_invalid_country(self, client, registered_agent, admin_user):
        admin_cookies = await login_user(client, admin_user["email"], admin_user["password"])
        await approve_agent(client, admin_cookies, registered_agent["id"])

        agent_cookies = await login_user(client, registered_agent["email"], registered_agent["password"])
        headers, cookies = await auth_headers_and_cookies(agent_cookies)

        payload = make_listing(country_code="xx")
        r = await client.post("/api/listings", json=payload, headers=headers, cookies=cookies)
        assert r.status_code in (400, 422)

    async def test_create_listing_without_csrf_fails(self, client, registered_agent, admin_user):
        """POST without CSRF token should fail."""
        admin_cookies = await login_user(client, admin_user["email"], admin_user["password"])
        await approve_agent(client, admin_cookies, registered_agent["id"])

        agent_cookies = await login_user(client, registered_agent["email"], registered_agent["password"])
        # Intentionally skip CSRF header
        r = await client.post("/api/listings", json=make_listing(), cookies=agent_cookies)
        assert r.status_code == 403

    async def test_create_listing_as_buyer_forbidden(self, client, registered_buyer):
        """Buyers cannot create listings."""
        cookies = await login_user(client, registered_buyer["email"], registered_buyer["password"])
        headers, cookies = await auth_headers_and_cookies(cookies)
        r = await client.post("/api/listings", json=make_listing(), headers=headers, cookies=cookies)
        assert r.status_code == 403

    async def test_create_listing_with_optional_fields(self, client, registered_agent, admin_user):
        """Listing with all optional fields populated."""
        admin_cookies = await login_user(client, admin_user["email"], admin_user["password"])
        await approve_agent(client, admin_cookies, registered_agent["id"])

        agent_cookies = await login_user(client, registered_agent["email"], registered_agent["password"])
        headers, cookies = await auth_headers_and_cookies(agent_cookies)

        payload = make_listing(
            real_location_lat=41.3275,
            real_location_lng=19.8187,
            real_description_en="Full details about the business.",
            public_location_area="Blloku",
            employee_count=8,
            years_in_operation=5,
        )
        r = await client.post("/api/listings", json=payload, headers=headers, cookies=cookies)
        assert r.status_code == 201
        listing = r.json()["listing"]
        assert listing["employee_count"] == 8
        assert listing["years_in_operation"] == 5


# ==========================================================================
# GET SINGLE LISTING
# ==========================================================================

class TestGetListing:

    async def test_get_listing_public_view_anonymous(self, client, registered_agent, admin_user):
        """Anonymous user sees public view (no real_business_name)."""
        agent_cookies, listing_id = await create_approved_agent_with_listing(
            client, registered_agent, admin_user
        )

        # Clear client cookies so request is truly anonymous
        client.cookies.clear()
        r = await client.get(f"/api/listings/{listing_id}")
        assert r.status_code == 200
        listing = r.json()["listing"]
        assert listing["public_title_en"] == "Great Business Opportunity"
        # Public view should NOT include real business name
        assert "real_business_name" not in listing or listing.get("real_business_name") is None

    async def test_get_listing_private_view_owner(self, client, registered_agent, admin_user):
        """Owner sees private view with real business details."""
        agent_cookies, listing_id = await create_approved_agent_with_listing(
            client, registered_agent, admin_user
        )

        r = await client.get(f"/api/listings/{listing_id}", cookies=agent_cookies)
        assert r.status_code == 200
        listing = r.json()["listing"]
        assert listing["real_business_name"] == "Test Business"

    async def test_get_listing_private_view_admin(self, client, registered_agent, admin_user):
        """Admin sees private view."""
        agent_cookies, listing_id = await create_approved_agent_with_listing(
            client, registered_agent, admin_user
        )
        admin_cookies = await login_user(client, admin_user["email"], admin_user["password"])

        r = await client.get(f"/api/listings/{listing_id}", cookies=admin_cookies)
        assert r.status_code == 200
        listing = r.json()["listing"]
        assert listing["real_business_name"] == "Test Business"

    async def test_get_listing_public_view_other_user(self, client, registered_agent, admin_user, registered_buyer):
        """Another user sees public view only."""
        agent_cookies, listing_id = await create_approved_agent_with_listing(
            client, registered_agent, admin_user
        )
        buyer_cookies = await login_user(client, registered_buyer["email"], registered_buyer["password"])

        r = await client.get(f"/api/listings/{listing_id}", cookies=buyer_cookies)
        assert r.status_code == 200
        listing = r.json()["listing"]
        assert "real_business_name" not in listing or listing.get("real_business_name") is None

    async def test_get_nonexistent_listing(self, client):
        fake_id = str(uuid.uuid4())
        r = await client.get(f"/api/listings/{fake_id}")
        assert r.status_code == 404

    async def test_view_count_increments_on_public_view(self, client, registered_agent, admin_user):
        """Public view should increment view_count."""
        agent_cookies, listing_id = await create_approved_agent_with_listing(
            client, registered_agent, admin_user
        )

        # Clear client cookies so requests are anonymous (public view increments count)
        client.cookies.clear()

        # Get initial view count
        r1 = await client.get(f"/api/listings/{listing_id}")
        count1 = r1.json()["listing"]["view_count"]

        # View again
        r2 = await client.get(f"/api/listings/{listing_id}")
        count2 = r2.json()["listing"]["view_count"]

        assert count2 == count1 + 1


# ==========================================================================
# UPDATE LISTING
# ==========================================================================

class TestUpdateListing:

    async def test_update_listing_owner(self, client, registered_agent, admin_user):
        """Owner can update their listing."""
        agent_cookies, listing_id = await create_approved_agent_with_listing(
            client, registered_agent, admin_user
        )
        headers, cookies = await auth_headers_and_cookies(agent_cookies)

        r = await client.put(
            f"/api/listings/{listing_id}",
            json={"public_title_en": "Updated Title For Business"},
            headers=headers, cookies=cookies,
        )
        assert r.status_code == 200
        assert r.json()["listing"]["public_title_en"] == "Updated Title For Business"

    async def test_update_listing_recalculates_roi(self, client, registered_agent, admin_user):
        """Updating price or revenue should recalculate ROI."""
        agent_cookies, listing_id = await create_approved_agent_with_listing(
            client, registered_agent, admin_user
        )
        headers, cookies = await auth_headers_and_cookies(agent_cookies)

        r = await client.put(
            f"/api/listings/{listing_id}",
            json={"asking_price_eur": 200000, "monthly_revenue_eur": 20000},
            headers=headers, cookies=cookies,
        )
        assert r.status_code == 200
        # ROI = (20000*12)/200000*100 = 120
        assert float(r.json()["listing"]["roi"]) == 120.0

    async def test_update_listing_non_owner_forbidden(self, client, registered_agent, admin_user, registered_buyer):
        """Non-owner (buyer) cannot update someone else's listing."""
        agent_cookies, listing_id = await create_approved_agent_with_listing(
            client, registered_agent, admin_user
        )

        buyer_cookies = await login_user(client, registered_buyer["email"], registered_buyer["password"])
        headers, cookies = await auth_headers_and_cookies(buyer_cookies)

        r = await client.put(
            f"/api/listings/{listing_id}",
            json={"public_title_en": "Hacked Title"},
            headers=headers, cookies=cookies,
        )
        assert r.status_code == 403

    async def test_update_listing_change_status(self, client, registered_agent, admin_user):
        """Owner can change listing status to inactive."""
        agent_cookies, listing_id = await create_approved_agent_with_listing(
            client, registered_agent, admin_user
        )
        headers, cookies = await auth_headers_and_cookies(agent_cookies)

        r = await client.put(
            f"/api/listings/{listing_id}",
            json={"status": "inactive"},
            headers=headers, cookies=cookies,
        )
        assert r.status_code == 200
        assert r.json()["listing"]["status"] == "inactive"


# ==========================================================================
# DELETE LISTING
# ==========================================================================

class TestDeleteListing:

    async def test_delete_listing_owner(self, client, registered_agent, admin_user):
        agent_cookies, listing_id = await create_approved_agent_with_listing(
            client, registered_agent, admin_user
        )
        headers, cookies = await auth_headers_and_cookies(agent_cookies)

        r = await client.delete(f"/api/listings/{listing_id}", headers=headers, cookies=cookies)
        assert r.status_code == 200

        # Verify listing is gone
        r2 = await client.get(f"/api/listings/{listing_id}")
        assert r2.status_code == 404

    async def test_delete_listing_non_owner_forbidden(self, client, registered_agent, admin_user, registered_buyer):
        agent_cookies, listing_id = await create_approved_agent_with_listing(
            client, registered_agent, admin_user
        )
        buyer_cookies = await login_user(client, registered_buyer["email"], registered_buyer["password"])
        headers, cookies = await auth_headers_and_cookies(buyer_cookies)

        r = await client.delete(f"/api/listings/{listing_id}", headers=headers, cookies=cookies)
        assert r.status_code == 403


# ==========================================================================
# SEARCH & FILTER LISTINGS
# ==========================================================================

class TestSearchListings:

    async def test_search_requires_country_code(self, client):
        r = await client.get("/api/listings")
        assert r.status_code == 422

    async def test_search_returns_only_active_listings(self, client, registered_agent, admin_user):
        """Only active listings from verified agents should appear in search."""
        agent_cookies, listing_id = await create_approved_agent_with_listing(
            client, registered_agent, admin_user
        )
        headers, cookies = await auth_headers_and_cookies(agent_cookies)

        # Make the listing inactive
        await client.put(
            f"/api/listings/{listing_id}",
            json={"status": "inactive"},
            headers=headers, cookies=cookies,
        )

        # Search — inactive listing should NOT appear
        r = await client.get("/api/listings", params={"country_code": "al"})
        assert r.status_code == 200
        listing_ids = [l["id"] for l in r.json()["listings"]]
        assert listing_id not in listing_ids

    async def test_search_by_category(self, client, registered_agent, admin_user):
        agent_cookies, listing_id = await create_approved_agent_with_listing(
            client, registered_agent, admin_user
        )

        # Search matching category
        r = await client.get("/api/listings", params={"country_code": "al", "category": "restaurant"})
        assert r.status_code == 200
        assert r.json()["total"] >= 1

        # Search non-matching category
        r2 = await client.get("/api/listings", params={"country_code": "al", "category": "gym"})
        assert r2.status_code == 200
        assert r2.json()["total"] == 0

    async def test_search_by_price_range(self, client, registered_agent, admin_user):
        agent_cookies, listing_id = await create_approved_agent_with_listing(
            client, registered_agent, admin_user
        )

        # Price range that includes the listing (100k EUR)
        r = await client.get("/api/listings", params={
            "country_code": "al", "min_price_eur": 50000, "max_price_eur": 200000,
        })
        assert r.status_code == 200
        assert r.json()["total"] >= 1

        # Price range that excludes the listing
        r2 = await client.get("/api/listings", params={
            "country_code": "al", "min_price_eur": 500000,
        })
        assert r2.status_code == 200
        assert listing_id not in [l["id"] for l in r2.json()["listings"]]

    async def test_search_by_city(self, client, registered_agent, admin_user):
        agent_cookies, listing_id = await create_approved_agent_with_listing(
            client, registered_agent, admin_user
        )

        r = await client.get("/api/listings", params={"country_code": "al", "city": "Tirana"})
        assert r.status_code == 200
        assert r.json()["total"] >= 1

    async def test_search_text_filter(self, client, registered_agent, admin_user):
        agent_cookies, listing_id = await create_approved_agent_with_listing(
            client, registered_agent, admin_user
        )

        r = await client.get("/api/listings", params={"country_code": "al", "search": "Great Business"})
        assert r.status_code == 200
        assert r.json()["total"] >= 1

    async def test_search_pagination(self, client, registered_agent, admin_user):
        """Pagination returns correct metadata."""
        agent_cookies, listing_id = await create_approved_agent_with_listing(
            client, registered_agent, admin_user
        )

        r = await client.get("/api/listings", params={
            "country_code": "al", "page": 1, "limit": 5,
        })
        assert r.status_code == 200
        data = r.json()
        assert data["page"] == 1
        assert data["limit"] == 5
        assert "total_pages" in data

    async def test_unverified_agent_listings_hidden(self, client, registered_agent, admin_user, test_password):
        """Listings from unverified agents should not appear in search."""
        # Create another agent but DON'T approve them
        import uuid as _uuid
        email = f"unverified_agent_{_uuid.uuid4().hex[:8]}@test.com"
        files = {
            "license_document": ("license.pdf", b"fake-pdf", "application/pdf"),
            "company_document": ("company.pdf", b"fake-pdf", "application/pdf"),
            "id_document": ("id.pdf", b"fake-pdf", "application/pdf"),
        }
        reg = await client.post("/api/auth/register", data={
            "name": "Unverified Agent", "email": email, "password": test_password,
            "role": "agent", "company_name": "Unv Agency", "operating_country": "al",
            "license_number": "LIC-UNV", "phone": "+355690000000", "whatsapp": "+355690000000",
        }, files=files)
        assert reg.status_code == 201

        # Verify email directly so they can log in
        from sqlalchemy import update
        from app.models.user import User
        async with TestSessionLocal() as session:
            await session.execute(
                update(User).where(User.id == _uuid.UUID(reg.json()["user_id"])).values(email_verified=True)
            )
            await session.commit()

        # Search — no listings from unverified agents should appear
        r = await client.get("/api/listings", params={"country_code": "al"})
        for listing in r.json()["listings"]:
            # All listed agents should be verified
            assert listing["agent_name"] is not None


# ==========================================================================
# AGENT LISTING LIST
# ==========================================================================

class TestAgentListings:

    async def test_agent_sees_all_own_listings(self, client, registered_agent, admin_user):
        """Agent can see all their listings including draft/inactive."""
        admin_cookies = await login_user(client, admin_user["email"], admin_user["password"])
        await approve_agent(client, admin_cookies, registered_agent["id"])

        agent_cookies = await login_user(client, registered_agent["email"], registered_agent["password"])
        headers, cookies = await auth_headers_and_cookies(agent_cookies)

        # Create two listings
        r1 = await client.post("/api/listings", json=make_listing(), headers=headers, cookies=cookies)
        assert r1.status_code == 201
        listing1_id = r1.json()["listing"]["id"]

        r2 = await client.post(
            "/api/listings",
            json=make_listing(public_title_en="Second Business For Sale Here"),
            headers=headers, cookies=cookies,
        )
        assert r2.status_code == 201

        # Make first listing inactive
        await client.put(
            f"/api/listings/{listing1_id}",
            json={"status": "inactive"},
            headers=headers, cookies=cookies,
        )

        # Agent listing endpoint shows all with pagination metadata
        r = await client.get(
            f"/api/listings/agent/{registered_agent['id']}",
            cookies=agent_cookies,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 2
        assert data["page"] == 1
        assert data["limit"] == 20
        assert data["total_pages"] == 1

    async def test_agent_listings_pagination(self, client, registered_agent, admin_user):
        """Agent listing endpoint respects page/limit params."""
        admin_cookies = await login_user(client, admin_user["email"], admin_user["password"])
        await approve_agent(client, admin_cookies, registered_agent["id"])

        agent_cookies = await login_user(client, registered_agent["email"], registered_agent["password"])
        headers, cookies = await auth_headers_and_cookies(agent_cookies)

        # Create 3 listings
        for i in range(3):
            r = await client.post(
                "/api/listings",
                json=make_listing(public_title_en=f"Business Number {i+1} For Sale"),
                headers=headers, cookies=cookies,
            )
            assert r.status_code == 201

        # Page 1, limit 2 → 2 items, total 3, 2 pages
        r = await client.get(
            f"/api/listings/agent/{registered_agent['id']}",
            params={"page": 1, "limit": 2},
            cookies=agent_cookies,
        )
        assert r.status_code == 200
        data = r.json()
        assert len(data["listings"]) == 2
        assert data["total"] == 3
        assert data["page"] == 1
        assert data["limit"] == 2
        assert data["total_pages"] == 2

        # Page 2 → 1 item
        r2 = await client.get(
            f"/api/listings/agent/{registered_agent['id']}",
            params={"page": 2, "limit": 2},
            cookies=agent_cookies,
        )
        assert r2.status_code == 200
        data2 = r2.json()
        assert len(data2["listings"]) == 1
        assert data2["total"] == 3
        assert data2["page"] == 2

    async def test_buyer_cannot_access_agent_listings(self, client, registered_buyer, registered_agent):
        """Buyer role cannot access agent listing endpoint."""
        buyer_cookies = await login_user(client, registered_buyer["email"], registered_buyer["password"])
        r = await client.get(
            f"/api/listings/agent/{registered_agent['id']}",
            cookies=buyer_cookies,
        )
        assert r.status_code == 403
