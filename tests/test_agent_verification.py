"""
Agent verification lifecycle tests.

Covers the full flow:
1. Agent registers → status "pending"
2. Pending agent CANNOT create listings
3. Admin rejects agent → status "rejected" + reason stored
4. Rejected agent CANNOT create listings
5. Agent re-uploads documents → status back to "pending"
6. Admin approves agent → status "approved"
7. Approved agent CAN create listings
8. Verification status endpoint returns correct data at each step
"""

from tests.conftest import (
    login_user, auth_headers_and_cookies, approve_agent, TestSessionLocal,
)


SAMPLE_LISTING = {
    "country_code": "al",
    "real_business_name": "Test Cafe",
    "real_location_address": "Rruga Test 123, Tirana",
    "public_title_en": "Charming Cafe in Tirana",
    "public_description_en": "A beautiful cafe with loyal customers and great location in the city center.",
    "category": "cafe",
    "public_location_city_en": "Tirana",
    "asking_price_eur": 50000,
    "monthly_revenue_eur": 5000,
    "images": [{"url": "https://test-bucket.s3.amazonaws.com/fake/img.jpg", "order": 0}],
}


class TestAgentVerificationFlow:

    async def test_new_agent_is_pending(self, client, registered_agent):
        """After registration, agent verification_status = 'pending'."""
        cookies = await login_user(client, registered_agent["email"], registered_agent["password"])
        r = await client.get("/api/users/me/verification-status", cookies=cookies)
        assert r.status_code == 200
        data = r.json()["status"]
        assert data["verification_status"] == "pending"
        assert data["can_create_listings"] is False

    async def test_pending_agent_cannot_create_listing(self, client, registered_agent):
        """Pending agent should be blocked from creating listings."""
        cookies = await login_user(client, registered_agent["email"], registered_agent["password"])
        headers, cookies = await auth_headers_and_cookies(cookies)

        r = await client.post(
            "/api/listings", json=SAMPLE_LISTING,
            headers=headers, cookies=cookies,
        )
        assert r.status_code == 403

    async def test_admin_rejects_agent(self, client, registered_agent, admin_user):
        """Admin rejects agent with a reason."""
        admin_cookies = await login_user(client, admin_user["email"], admin_user["password"])
        admin_headers, admin_cookies = await auth_headers_and_cookies(admin_cookies)

        r = await client.post(
            f"/api/admin/agents/{registered_agent['id']}/reject",
            json={"rejection_reason": "Documents are blurry, please re-upload."},
            headers=admin_headers, cookies=admin_cookies,
        )
        assert r.status_code == 200

        # Verify agent sees rejected status
        agent_cookies = await login_user(client, registered_agent["email"], registered_agent["password"])
        r2 = await client.get("/api/users/me/verification-status", cookies=agent_cookies)
        assert r2.status_code == 200
        data = r2.json()["status"]
        assert data["verification_status"] == "rejected"
        assert "blurry" in data["rejection_reason"].lower()

    async def test_rejected_agent_cannot_create_listing(self, client, registered_agent, admin_user):
        """Rejected agent should also be blocked from creating listings."""
        # Reject first
        admin_cookies = await login_user(client, admin_user["email"], admin_user["password"])
        admin_headers, admin_cookies = await auth_headers_and_cookies(admin_cookies)
        await client.post(
            f"/api/admin/agents/{registered_agent['id']}/reject",
            json={"rejection_reason": "Incomplete docs."},
            headers=admin_headers, cookies=admin_cookies,
        )

        # Try creating listing as rejected agent
        agent_cookies = await login_user(client, registered_agent["email"], registered_agent["password"])
        agent_headers, agent_cookies = await auth_headers_and_cookies(agent_cookies)
        r = await client.post(
            "/api/listings", json=SAMPLE_LISTING,
            headers=agent_headers, cookies=agent_cookies,
        )
        assert r.status_code == 403

    async def test_agent_reupload_documents_resets_to_pending(self, client, registered_agent, admin_user):
        """After rejection, agent re-uploads docs → status goes back to 'pending'."""
        # Reject first
        admin_cookies = await login_user(client, admin_user["email"], admin_user["password"])
        admin_headers, admin_cookies = await auth_headers_and_cookies(admin_cookies)
        await client.post(
            f"/api/admin/agents/{registered_agent['id']}/reject",
            json={"rejection_reason": "Bad docs."},
            headers=admin_headers, cookies=admin_cookies,
        )

        # Re-upload a document
        agent_cookies = await login_user(client, registered_agent["email"], registered_agent["password"])
        agent_headers, agent_cookies = await auth_headers_and_cookies(agent_cookies)

        files = {"file": ("new_license.pdf", b"new-fake-pdf-content", "application/pdf")}
        r = await client.post(
            "/api/upload/direct/document",
            params={"document_type": "license"},
            files=files,
            headers=agent_headers,
            cookies=agent_cookies,
        )
        assert r.status_code == 200

        # Status should be back to pending
        r2 = await client.get("/api/users/me/verification-status", cookies=agent_cookies)
        assert r2.status_code == 200
        assert r2.json()["status"]["verification_status"] == "pending"

    async def test_admin_approves_agent(self, client, registered_agent, admin_user):
        """Admin approves agent → status 'approved', can_create_listings = True."""
        admin_cookies = await login_user(client, admin_user["email"], admin_user["password"])
        await approve_agent(client, admin_cookies, registered_agent["id"])

        # Check status
        agent_cookies = await login_user(client, registered_agent["email"], registered_agent["password"])
        r = await client.get("/api/users/me/verification-status", cookies=agent_cookies)
        assert r.status_code == 200
        data = r.json()["status"]
        assert data["verification_status"] == "approved"
        assert data["can_create_listings"] is True

    async def test_approved_agent_can_create_listing(self, client, registered_agent, admin_user):
        """After approval, agent can successfully create a listing."""
        admin_cookies = await login_user(client, admin_user["email"], admin_user["password"])
        await approve_agent(client, admin_cookies, registered_agent["id"])

        agent_cookies = await login_user(client, registered_agent["email"], registered_agent["password"])
        agent_headers, agent_cookies = await auth_headers_and_cookies(agent_cookies)

        r = await client.post(
            "/api/listings", json=SAMPLE_LISTING,
            headers=agent_headers, cookies=agent_cookies,
        )
        assert r.status_code == 201
        assert r.json()["success"] is True
        assert r.json()["listing"]["public_title_en"] == SAMPLE_LISTING["public_title_en"]

    async def test_document_upload_status(self, client, registered_agent):
        """Agent can see their document upload status."""
        cookies = await login_user(client, registered_agent["email"], registered_agent["password"])
        r = await client.get("/api/users/me/documents", cookies=cookies)
        assert r.status_code == 200

    async def test_buyer_cannot_access_verification_status(self, client, registered_buyer):
        """Buyer role should not access agent-specific endpoints."""
        cookies = await login_user(client, registered_buyer["email"], registered_buyer["password"])
        r = await client.get("/api/users/me/verification-status", cookies=cookies)
        assert r.status_code == 403
