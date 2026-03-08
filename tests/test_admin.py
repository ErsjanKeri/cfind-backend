"""
Admin endpoint tests.

Covers:
- Platform stats
- List all users (with role filter)
- Admin creates agent directly
- Admin creates buyer directly
- Verify/reject agents
- Delete user (cascade)
- Cannot delete admin user
- Toggle email verification
- Adjust agent credits (bonus/deduction)
- Non-admin access blocked
"""

import uuid

from tests.conftest import login_user, auth_headers_and_cookies, approve_agent, TestSessionLocal


# ==========================================================================
# ACCESS CONTROL
# ==========================================================================

class TestAdminAccessControl:

    async def test_buyer_cannot_access_admin_routes(self, client, registered_buyer):
        cookies = await login_user(client, registered_buyer["email"], registered_buyer["password"])

        r = await client.get("/api/admin/stats", cookies=cookies)
        assert r.status_code == 403

        r2 = await client.get("/api/admin/users", cookies=cookies)
        assert r2.status_code == 403

    async def test_agent_cannot_access_admin_routes(self, client, registered_agent):
        cookies = await login_user(client, registered_agent["email"], registered_agent["password"])

        r = await client.get("/api/admin/stats", cookies=cookies)
        assert r.status_code == 403

    async def test_unauthenticated_cannot_access_admin_routes(self, client):
        r = await client.get("/api/admin/stats")
        assert r.status_code == 401


# ==========================================================================
# PLATFORM STATS
# ==========================================================================

class TestPlatformStats:

    async def test_admin_sees_platform_stats(self, client, admin_user):
        cookies = await login_user(client, admin_user["email"], admin_user["password"])

        r = await client.get("/api/admin/stats", cookies=cookies)
        assert r.status_code == 200
        assert r.json()["success"] is True
        assert "stats" in r.json()


# ==========================================================================
# LIST USERS
# ==========================================================================

class TestListUsers:

    async def test_admin_lists_all_users(self, client, admin_user, registered_buyer, registered_agent):
        cookies = await login_user(client, admin_user["email"], admin_user["password"])

        r = await client.get("/api/admin/users", cookies=cookies)
        assert r.status_code == 200
        users = r.json()["users"]
        # Should include at least the admin, buyer, and agent
        assert len(users) >= 3

    async def test_filter_users_by_role(self, client, admin_user, registered_buyer, registered_agent):
        cookies = await login_user(client, admin_user["email"], admin_user["password"])

        # Filter by buyer role
        r = await client.get("/api/admin/users", params={"role": "buyer"}, cookies=cookies)
        assert r.status_code == 200
        for user in r.json()["users"]:
            assert user["role"] == "buyer"

        # Filter by agent role
        r2 = await client.get("/api/admin/users", params={"role": "agent"}, cookies=cookies)
        assert r2.status_code == 200
        for user in r2.json()["users"]:
            assert user["role"] == "agent"


# ==========================================================================
# CREATE USERS
# ==========================================================================

class TestAdminCreateUsers:

    async def test_admin_creates_agent(self, client, admin_user):
        cookies = await login_user(client, admin_user["email"], admin_user["password"])
        headers, cookies = await auth_headers_and_cookies(cookies)

        r = await client.post("/api/admin/agents", json={
            "name": "Admin-Created Agent",
            "email": f"admin_agent_{uuid.uuid4().hex[:8]}@test.com",
            "password": "SecurePass123",
            "operating_country": "al",
            "company_name": "Admin Agency",
            "license_number": "LIC-ADMIN-001",
            "phone": "+355691111111",
            "whatsapp": "+355691111111",
            "email_verified": True,
            "verification_status": "approved",
        }, headers=headers, cookies=cookies)
        assert r.status_code == 201

    async def test_admin_creates_buyer(self, client, admin_user):
        cookies = await login_user(client, admin_user["email"], admin_user["password"])
        headers, cookies = await auth_headers_and_cookies(cookies)

        r = await client.post("/api/admin/buyers", json={
            "name": "Admin-Created Buyer",
            "email": f"admin_buyer_{uuid.uuid4().hex[:8]}@test.com",
            "password": "SecurePass123",
            "email_verified": True,
        }, headers=headers, cookies=cookies)
        assert r.status_code == 201


# ==========================================================================
# VERIFY / REJECT AGENTS
# ==========================================================================

class TestAgentVerification:

    async def test_admin_approves_agent(self, client, admin_user, registered_agent):
        cookies = await login_user(client, admin_user["email"], admin_user["password"])
        headers, cookies = await auth_headers_and_cookies(cookies)

        r = await client.post(
            f"/api/admin/agents/{registered_agent['id']}/verify",
            headers=headers, cookies=cookies,
        )
        assert r.status_code == 200

    async def test_admin_rejects_agent_with_reason(self, client, admin_user, registered_agent):
        cookies = await login_user(client, admin_user["email"], admin_user["password"])
        headers, cookies = await auth_headers_and_cookies(cookies)

        r = await client.post(
            f"/api/admin/agents/{registered_agent['id']}/reject",
            json={"rejection_reason": "Documents are unclear."},
            headers=headers, cookies=cookies,
        )
        assert r.status_code == 200


# ==========================================================================
# DELETE USER
# ==========================================================================

class TestDeleteUser:

    async def test_admin_deletes_buyer(self, client, admin_user, test_password):
        """Admin can delete a buyer — cascades all related data."""
        admin_cookies = await login_user(client, admin_user["email"], admin_user["password"])
        headers, cookies = await auth_headers_and_cookies(admin_cookies)

        # Create a buyer to delete
        email = f"deleteme_{uuid.uuid4().hex[:8]}@test.com"
        reg = await client.post("/api/auth/register", data={
            "name": "Delete Me", "email": email, "password": test_password, "role": "buyer",
        })
        user_id = reg.json()["user_id"]

        r = await client.delete(f"/api/admin/users/{user_id}", headers=headers, cookies=cookies)
        assert r.status_code == 200

        # Verify user is gone from the list
        r2 = await client.get("/api/admin/users", cookies=cookies)
        user_ids = [u["id"] for u in r2.json()["users"]]
        assert user_id not in user_ids

    async def test_cannot_delete_admin_user(self, client, admin_user):
        """Admin cannot delete another admin (safety guard)."""
        cookies = await login_user(client, admin_user["email"], admin_user["password"])
        headers, cookies = await auth_headers_and_cookies(cookies)

        r = await client.delete(f"/api/admin/users/{admin_user['id']}", headers=headers, cookies=cookies)
        assert r.status_code in (400, 403)


# ==========================================================================
# TOGGLE EMAIL VERIFICATION
# ==========================================================================

class TestToggleEmailVerification:

    async def test_admin_toggles_email_verification(self, client, admin_user, test_password):
        admin_cookies = await login_user(client, admin_user["email"], admin_user["password"])
        headers, cookies = await auth_headers_and_cookies(admin_cookies)

        # Create a buyer (email_verified=false by default)
        email = f"toggle_{uuid.uuid4().hex[:8]}@test.com"
        reg = await client.post("/api/auth/register", data={
            "name": "Toggle User", "email": email, "password": test_password, "role": "buyer",
        })
        user_id = reg.json()["user_id"]

        # Toggle to verified
        r = await client.post(
            f"/api/admin/users/{user_id}/toggle-email-verification",
            json={"email_verified": True},
            headers=headers, cookies=cookies,
        )
        assert r.status_code == 200

        # User should now be able to login
        r2 = await client.post("/api/auth/login", json={
            "email": email, "password": test_password,
        })
        assert r2.status_code == 200


# ==========================================================================
# ADJUST CREDITS
# ==========================================================================

class TestAdjustCredits:

    async def test_admin_gives_bonus_credits(self, client, admin_user, registered_agent):
        admin_cookies = await login_user(client, admin_user["email"], admin_user["password"])
        headers, cookies = await auth_headers_and_cookies(admin_cookies)

        r = await client.post("/api/admin/credits/adjust", json={
            "agent_id": registered_agent["id"],
            "amount": 50,
            "description": "Welcome bonus for new agent",
        }, headers=headers, cookies=cookies)
        assert r.status_code == 200
        assert r.json()["new_balance"] == 50

    async def test_admin_deducts_credits(self, client, admin_user, registered_agent):
        admin_cookies = await login_user(client, admin_user["email"], admin_user["password"])
        headers, cookies = await auth_headers_and_cookies(admin_cookies)

        # Give credits first
        await client.post("/api/admin/credits/adjust", json={
            "agent_id": registered_agent["id"],
            "amount": 100,
            "description": "Initial credits for testing",
        }, headers=headers, cookies=cookies)

        # Deduct some
        r = await client.post("/api/admin/credits/adjust", json={
            "agent_id": registered_agent["id"],
            "amount": -30,
            "description": "Penalty adjustment for policy violation",
        }, headers=headers, cookies=cookies)
        assert r.status_code == 200
        assert r.json()["new_balance"] == 70  # 100 - 30

    async def test_adjust_credits_short_description_rejected(self, client, admin_user, registered_agent):
        """Description must be 5-200 characters."""
        admin_cookies = await login_user(client, admin_user["email"], admin_user["password"])
        headers, cookies = await auth_headers_and_cookies(admin_cookies)

        r = await client.post("/api/admin/credits/adjust", json={
            "agent_id": registered_agent["id"],
            "amount": 10,
            "description": "Hi",
        }, headers=headers, cookies=cookies)
        assert r.status_code == 422
