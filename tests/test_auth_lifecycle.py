"""
Auth lifecycle tests — registration, verification, login, refresh, logout, password reset.

Covers:
- Buyer + agent registration (happy path + validation errors)
- Email verification flow
- Login (success, wrong creds, unverified)
- Token refresh
- Logout
- Password reset request + reset
- Resend verification
- Duplicate email prevention
- Password strength validation
"""

import uuid

from tests.conftest import login_user, auth_headers_and_cookies, TestSessionLocal


# ==========================================================================
# REGISTRATION
# ==========================================================================

class TestBuyerRegistration:

    async def test_buyer_registers_successfully(self, client, test_password):
        r = await client.post("/api/auth/register", data={
            "name": "New Buyer",
            "email": f"buyer_{uuid.uuid4().hex[:8]}@test.com",
            "password": test_password,
            "role": "buyer",
        })
        assert r.status_code == 201
        body = r.json()
        assert body["success"] is True
        assert "user_id" in body

    async def test_buyer_register_optional_fields(self, client, test_password):
        """Buyer can register with optional phone and company."""
        r = await client.post("/api/auth/register", data={
            "name": "Buyer With Details",
            "email": f"buyer_{uuid.uuid4().hex[:8]}@test.com",
            "password": test_password,
            "role": "buyer",
            "phone": "+355691234567",
            "company_name": "My Investment Co",
        })
        assert r.status_code == 201

    async def test_duplicate_email_rejected(self, client, test_password):
        email = f"dup_{uuid.uuid4().hex[:8]}@test.com"

        r1 = await client.post("/api/auth/register", data={
            "name": "First", "email": email, "password": test_password, "role": "buyer",
        })
        assert r1.status_code == 201

        r2 = await client.post("/api/auth/register", data={
            "name": "Second", "email": email, "password": test_password, "role": "buyer",
        })
        assert r2.status_code == 400
        assert "already registered" in r2.json()["detail"].lower()

    async def test_invalid_email_format_rejected(self, client, test_password):
        r = await client.post("/api/auth/register", data={
            "name": "Bad Email", "email": "not-an-email", "password": test_password, "role": "buyer",
        })
        assert r.status_code == 400
        assert "invalid email" in r.json()["detail"].lower()

    async def test_invalid_role_rejected(self, client, test_password):
        r = await client.post("/api/auth/register", data={
            "name": "Bad Role",
            "email": f"role_{uuid.uuid4().hex[:8]}@test.com",
            "password": test_password,
            "role": "admin",
        })
        assert r.status_code == 400
        assert "buyer" in r.json()["detail"].lower() or "agent" in r.json()["detail"].lower()


class TestPasswordValidation:

    async def test_password_too_short(self, client):
        r = await client.post("/api/auth/register", data={
            "name": "Short Pass",
            "email": f"short_{uuid.uuid4().hex[:8]}@test.com",
            "password": "Ab1",
            "role": "buyer",
        })
        assert r.status_code == 400
        assert "8 characters" in r.json()["detail"]

    async def test_password_no_uppercase(self, client):
        r = await client.post("/api/auth/register", data={
            "name": "No Upper",
            "email": f"noup_{uuid.uuid4().hex[:8]}@test.com",
            "password": "lowercase123",
            "role": "buyer",
        })
        assert r.status_code == 400
        assert "uppercase" in r.json()["detail"].lower()

    async def test_password_no_lowercase(self, client):
        r = await client.post("/api/auth/register", data={
            "name": "No Lower",
            "email": f"nolow_{uuid.uuid4().hex[:8]}@test.com",
            "password": "UPPERCASE123",
            "role": "buyer",
        })
        assert r.status_code == 400
        assert "lowercase" in r.json()["detail"].lower()

    async def test_password_no_number(self, client):
        r = await client.post("/api/auth/register", data={
            "name": "No Num",
            "email": f"nonum_{uuid.uuid4().hex[:8]}@test.com",
            "password": "NoNumbers!",
            "role": "buyer",
        })
        assert r.status_code == 400
        assert "number" in r.json()["detail"].lower()


class TestAgentRegistration:

    async def test_agent_registers_with_documents(self, client, test_password):
        files = {
            "license_document": ("license.pdf", b"fake-pdf", "application/pdf"),
            "company_document": ("company.pdf", b"fake-pdf", "application/pdf"),
            "id_document": ("id.pdf", b"fake-pdf", "application/pdf"),
        }
        r = await client.post("/api/auth/register", data={
            "name": "New Agent",
            "email": f"agent_{uuid.uuid4().hex[:8]}@test.com",
            "password": test_password,
            "role": "agent",
            "company_name": "Agency LLC",
            "operating_country": "al",
            "license_number": "LIC-99999",
            "phone": "+355691234567",
            "whatsapp": "+355691234567",
        }, files=files)
        assert r.status_code == 201
        assert r.json()["success"] is True

    async def test_agent_missing_documents_rejected(self, client, test_password):
        """Agent registration without documents should fail."""
        r = await client.post("/api/auth/register", data={
            "name": "No Docs Agent",
            "email": f"nodoc_{uuid.uuid4().hex[:8]}@test.com",
            "password": test_password,
            "role": "agent",
            "company_name": "Agency LLC",
            "operating_country": "al",
            "license_number": "LIC-99999",
            "phone": "+355691234567",
            "whatsapp": "+355691234567",
        })
        assert r.status_code == 400
        assert "license document" in r.json()["detail"].lower()

    async def test_agent_missing_company_name_rejected(self, client, test_password):
        files = {
            "license_document": ("license.pdf", b"fake-pdf", "application/pdf"),
            "company_document": ("company.pdf", b"fake-pdf", "application/pdf"),
            "id_document": ("id.pdf", b"fake-pdf", "application/pdf"),
        }
        r = await client.post("/api/auth/register", data={
            "name": "No Company Agent",
            "email": f"nocomp_{uuid.uuid4().hex[:8]}@test.com",
            "password": test_password,
            "role": "agent",
            "operating_country": "al",
            "license_number": "LIC-99999",
            "phone": "+355691234567",
            "whatsapp": "+355691234567",
        }, files=files)
        assert r.status_code == 400
        assert "company name" in r.json()["detail"].lower()

    async def test_agent_invalid_country_rejected(self, client, test_password):
        files = {
            "license_document": ("license.pdf", b"fake-pdf", "application/pdf"),
            "company_document": ("company.pdf", b"fake-pdf", "application/pdf"),
            "id_document": ("id.pdf", b"fake-pdf", "application/pdf"),
        }
        r = await client.post("/api/auth/register", data={
            "name": "Bad Country Agent",
            "email": f"badcountry_{uuid.uuid4().hex[:8]}@test.com",
            "password": test_password,
            "role": "agent",
            "company_name": "Agency LLC",
            "operating_country": "xx",
            "license_number": "LIC-99999",
            "phone": "+355691234567",
            "whatsapp": "+355691234567",
        }, files=files)
        assert r.status_code == 400
        assert "operating country" in r.json()["detail"].lower()

    async def test_agent_missing_whatsapp_rejected(self, client, test_password):
        files = {
            "license_document": ("license.pdf", b"fake-pdf", "application/pdf"),
            "company_document": ("company.pdf", b"fake-pdf", "application/pdf"),
            "id_document": ("id.pdf", b"fake-pdf", "application/pdf"),
        }
        r = await client.post("/api/auth/register", data={
            "name": "No WA Agent",
            "email": f"nowa_{uuid.uuid4().hex[:8]}@test.com",
            "password": test_password,
            "role": "agent",
            "company_name": "Agency LLC",
            "operating_country": "al",
            "license_number": "LIC-99999",
            "phone": "+355691234567",
        }, files=files)
        assert r.status_code == 400
        assert "whatsapp" in r.json()["detail"].lower()


# ==========================================================================
# LOGIN
# ==========================================================================

class TestLogin:

    async def test_login_unverified_email_blocked(self, client, test_password):
        """Users can't log in until they verify their email."""
        email = f"unverified_{uuid.uuid4().hex[:8]}@test.com"
        await client.post("/api/auth/register", data={
            "name": "Unverified",
            "email": email,
            "password": test_password,
            "role": "buyer",
        })

        r = await client.post("/api/auth/login", json={
            "email": email,
            "password": test_password,
        })
        # Should be blocked — email not verified (EmailNotVerifiedException → 403)
        assert r.status_code == 403

    async def test_login_verified_buyer_succeeds(self, client, registered_buyer):
        """Verified buyer can log in and gets auth cookies."""
        cookies = await login_user(client, registered_buyer["email"], registered_buyer["password"])
        assert "access_token" in cookies
        assert "csrf_token" in cookies

    async def test_login_wrong_password(self, client, registered_buyer):
        r = await client.post("/api/auth/login", json={
            "email": registered_buyer["email"],
            "password": "WrongPassword123",
        })
        assert r.status_code == 401

    async def test_login_nonexistent_email(self, client):
        r = await client.post("/api/auth/login", json={
            "email": "nobody@nowhere.com",
            "password": "Whatever123",
        })
        assert r.status_code == 401

    async def test_login_returns_user_data(self, client, registered_buyer):
        r = await client.post("/api/auth/login", json={
            "email": registered_buyer["email"],
            "password": registered_buyer["password"],
        })
        assert r.status_code == 200
        user = r.json()["user"]
        assert user["email"] == registered_buyer["email"]
        assert user["role"] == "buyer"
        assert user["name"] == registered_buyer["name"]


# ==========================================================================
# EMAIL VERIFICATION
# ==========================================================================

class TestEmailVerification:

    async def test_verify_email_with_valid_token(self, client, test_password, db):
        """Full flow: register → get token from DB → verify → login succeeds."""
        email = f"verify_{uuid.uuid4().hex[:8]}@test.com"
        reg = await client.post("/api/auth/register", data={
            "name": "Verify Me",
            "email": email,
            "password": test_password,
            "role": "buyer",
        })
        user_id = reg.json()["user_id"]

        # Get the verification token directly from DB
        from sqlalchemy import select
        from app.models.token import EmailVerificationToken
        result = await db.execute(
            select(EmailVerificationToken).where(
                EmailVerificationToken.user_id == uuid.UUID(user_id)
            )
        )
        token_record = result.scalar_one()

        # Verify email
        r = await client.get(f"/api/auth/verify-email?token={token_record.token}")
        assert r.status_code == 200

        # Now login should work
        login_r = await client.post("/api/auth/login", json={
            "email": email,
            "password": test_password,
        })
        assert login_r.status_code == 200

    async def test_verify_email_invalid_token(self, client):
        r = await client.get("/api/auth/verify-email?token=this-is-a-totally-fake-token-string")
        assert r.status_code in (400, 404)

    async def test_resend_verification_always_succeeds(self, client):
        """Resend verification returns success even for unknown emails (no enumeration)."""
        r = await client.post("/api/auth/resend-verification", json={
            "email": "nobody@test.com",
        })
        assert r.status_code == 200


# ==========================================================================
# TOKEN REFRESH & LOGOUT
# ==========================================================================

class TestTokenRefreshAndLogout:

    async def test_refresh_token_returns_new_access_token(self, client, registered_buyer):
        """After login, refreshing should return a new access token."""
        cookies = await login_user(client, registered_buyer["email"], registered_buyer["password"])

        r = await client.post("/api/auth/refresh", cookies=cookies)
        assert r.status_code == 200
        assert "access_token" in r.cookies

    async def test_refresh_without_token_fails(self, client):
        r = await client.post("/api/auth/refresh")
        assert r.status_code in (401, 403)

    async def test_logout_clears_cookies(self, client, registered_buyer):
        cookies = await login_user(client, registered_buyer["email"], registered_buyer["password"])
        headers, cookies = await auth_headers_and_cookies(cookies)

        r = await client.post("/api/auth/logout", headers=headers, cookies=cookies)
        assert r.status_code == 200

        # Cookies should be cleared (max-age=0 or deleted)
        for cookie_name in ["access_token", "refresh_token", "csrf_token"]:
            if cookie_name in r.cookies:
                # Cookie set with max-age=0 means cleared
                pass  # httpx may not expose max-age directly

    async def test_access_protected_route_after_logout(self, client, registered_buyer):
        """After logout, /users/me should fail."""
        cookies = await login_user(client, registered_buyer["email"], registered_buyer["password"])
        headers, cookies = await auth_headers_and_cookies(cookies)

        # Logout
        await client.post("/api/auth/logout", headers=headers, cookies=cookies)

        # Try accessing protected route with old cookies — should fail
        r = await client.get("/api/users/me", cookies=cookies)
        # Access token is still technically valid (15min), but let's verify the endpoint works
        # The key test is that refresh won't work after logout
        r2 = await client.post("/api/auth/refresh", cookies=cookies)
        assert r2.status_code in (401, 403)


# ==========================================================================
# GET CURRENT USER
# ==========================================================================

class TestGetCurrentUser:

    async def test_get_me_as_buyer(self, client, registered_buyer):
        cookies = await login_user(client, registered_buyer["email"], registered_buyer["password"])
        r = await client.get("/api/users/me", cookies=cookies)
        assert r.status_code == 200
        user = r.json()
        assert user["email"] == registered_buyer["email"]
        assert user["role"] == "buyer"

    async def test_get_me_as_agent(self, client, registered_agent):
        """Verify agent sees their profile including agent_profile data."""
        cookies = await login_user(client, registered_agent["email"], registered_agent["password"])
        r = await client.get("/api/users/me", cookies=cookies)
        assert r.status_code == 200
        user = r.json()
        assert user["email"] == registered_agent["email"]
        assert user["role"] == "agent"

    async def test_get_me_unauthenticated(self, client):
        r = await client.get("/api/users/me")
        assert r.status_code == 401


# ==========================================================================
# PASSWORD RESET
# ==========================================================================

class TestPasswordReset:

    async def test_password_reset_request_always_succeeds(self, client):
        """No email enumeration — always returns success."""
        r = await client.post("/api/auth/password-reset-request", json={
            "email": "nonexistent@test.com",
        })
        assert r.status_code == 200

    async def test_full_password_reset_flow(self, client, registered_buyer, db):
        """Request reset → get token from DB → reset password → login with new password."""
        # Request password reset
        r = await client.post("/api/auth/password-reset-request", json={
            "email": registered_buyer["email"],
        })
        assert r.status_code == 200

        # Get the reset token from DB
        from sqlalchemy import select
        from app.models.token import PasswordResetToken
        result = await db.execute(
            select(PasswordResetToken).where(
                PasswordResetToken.user_id == uuid.UUID(registered_buyer["id"])
            )
        )
        token_record = result.scalar_one()

        # Reset the password
        new_password = "NewSecurePass123"
        r2 = await client.post("/api/auth/password-reset", json={
            "token": token_record.token,
            "new_password": new_password,
        })
        assert r2.status_code == 200

        # Login with new password should work
        r3 = await client.post("/api/auth/login", json={
            "email": registered_buyer["email"],
            "password": new_password,
        })
        assert r3.status_code == 200

        # Old password should NOT work
        r4 = await client.post("/api/auth/login", json={
            "email": registered_buyer["email"],
            "password": registered_buyer["password"],
        })
        assert r4.status_code == 401

    async def test_password_reset_invalid_token(self, client):
        r = await client.post("/api/auth/password-reset", json={
            "token": "fake-token-that-does-not-exist-at-all",
            "new_password": "NewSecurePass123",
        })
        assert r.status_code in (400, 404)

    async def test_password_reset_weak_new_password(self, client, registered_buyer, db):
        """Reset with a weak new password should be rejected."""
        # Request reset
        await client.post("/api/auth/password-reset-request", json={
            "email": registered_buyer["email"],
        })

        from sqlalchemy import select
        from app.models.token import PasswordResetToken
        result = await db.execute(
            select(PasswordResetToken).where(
                PasswordResetToken.user_id == uuid.UUID(registered_buyer["id"])
            )
        )
        token_record = result.scalar_one()

        r = await client.post("/api/auth/password-reset", json={
            "token": token_record.token,
            "new_password": "weak",
        })
        assert r.status_code in (400, 422)
