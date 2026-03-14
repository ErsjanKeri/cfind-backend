"""
Geography endpoint tests.

Covers:
- Public: List countries, cities, neighbourhoods (no auth)
- Admin: Create city, update city, create neighbourhood
- Access control: Non-admin users blocked from admin geography endpoints
- Delete endpoints removed (should return 404/405)
"""

from tests.conftest import login_user, auth_headers_and_cookies


# ==========================================================================
# PUBLIC ENDPOINTS (no auth required)
# ==========================================================================

class TestListCountries:

    async def test_list_countries_returns_seeded_data(self, client):
        r = await client.get("/api/countries")
        assert r.status_code == 200

        data = r.json()
        assert data["success"] is True
        assert len(data["countries"]) == 2

        codes = {c["code"] for c in data["countries"]}
        assert codes == {"al", "ae"}

    async def test_list_countries_includes_cities(self, client):
        r = await client.get("/api/countries")
        countries = r.json()["countries"]

        al = next(c for c in countries if c["code"] == "al")
        assert len(al["cities"]) > 0
        city_names = [c["name"] for c in al["cities"]]
        assert "Tirana" in city_names


class TestListCities:

    async def test_list_cities_for_albania(self, client):
        r = await client.get("/api/countries/al/cities")
        assert r.status_code == 200

        data = r.json()
        assert data["success"] is True
        assert len(data["cities"]) >= 10
        names = [c["name"] for c in data["cities"]]
        assert "Tirana" in names
        assert "Durrës" in names

    async def test_list_cities_for_uae(self, client):
        r = await client.get("/api/countries/ae/cities")
        assert r.status_code == 200

        names = [c["name"] for c in r.json()["cities"]]
        assert "Dubai" in names
        assert "Abu Dhabi" in names

    async def test_list_cities_invalid_country_returns_404(self, client):
        r = await client.get("/api/countries/xx/cities")
        assert r.status_code == 404


class TestListNeighbourhoods:

    async def test_list_neighbourhoods_for_valid_city(self, client):
        # Get a city ID first
        r = await client.get("/api/countries/al/cities")
        city_id = r.json()["cities"][0]["id"]

        r2 = await client.get(f"/api/countries/cities/{city_id}/neighbourhoods")
        assert r2.status_code == 200
        data = r2.json()
        assert data["success"] is True
        assert isinstance(data["neighbourhoods"], list)

    async def test_list_neighbourhoods_invalid_city_returns_404(self, client):
        r = await client.get("/api/countries/cities/999999/neighbourhoods")
        assert r.status_code == 404


# ==========================================================================
# ADMIN: CREATE CITY
# ==========================================================================

class TestAdminCreateCity:

    async def test_admin_creates_city(self, client, admin_user):
        cookies = await login_user(client, admin_user["email"], admin_user["password"])
        headers, cookies = await auth_headers_and_cookies(cookies)

        r = await client.post(
            "/api/admin/geography/al/cities",
            json={"name": "Pogradec"},
            headers=headers,
            cookies=cookies,
        )
        assert r.status_code == 201
        data = r.json()
        assert data["city"]["name"] == "Pogradec"
        assert data["city"]["country_code"] == "al"

        # Verify it appears in the public list
        r2 = await client.get("/api/countries/al/cities")
        names = [c["name"] for c in r2.json()["cities"]]
        assert "Pogradec" in names

    async def test_create_city_invalid_country_returns_404(self, client, admin_user):
        cookies = await login_user(client, admin_user["email"], admin_user["password"])
        headers, cookies = await auth_headers_and_cookies(cookies)

        r = await client.post(
            "/api/admin/geography/xx/cities",
            json={"name": "Nowhere"},
            headers=headers,
            cookies=cookies,
        )
        assert r.status_code == 404

    async def test_buyer_cannot_create_city(self, client, registered_buyer):
        cookies = await login_user(client, registered_buyer["email"], registered_buyer["password"])
        headers, cookies = await auth_headers_and_cookies(cookies)

        r = await client.post(
            "/api/admin/geography/al/cities",
            json={"name": "Hack City"},
            headers=headers,
            cookies=cookies,
        )
        assert r.status_code == 403

    async def test_agent_cannot_create_city(self, client, registered_agent):
        cookies = await login_user(client, registered_agent["email"], registered_agent["password"])
        headers, cookies = await auth_headers_and_cookies(cookies)

        r = await client.post(
            "/api/admin/geography/al/cities",
            json={"name": "Hack City"},
            headers=headers,
            cookies=cookies,
        )
        assert r.status_code == 403


# ==========================================================================
# ADMIN: UPDATE CITY
# ==========================================================================

class TestAdminUpdateCity:

    async def test_admin_renames_city(self, client, admin_user):
        cookies = await login_user(client, admin_user["email"], admin_user["password"])
        headers, cookies = await auth_headers_and_cookies(cookies)

        # Create a city to rename
        r = await client.post(
            "/api/admin/geography/al/cities",
            json={"name": "OldName"},
            headers=headers,
            cookies=cookies,
        )
        assert r.status_code == 201
        city_id = r.json()["city"]["id"]

        # Rename it
        r2 = await client.put(
            f"/api/admin/geography/cities/{city_id}",
            json={"name": "NewName"},
            headers=headers,
            cookies=cookies,
        )
        assert r2.status_code == 200
        assert r2.json()["city"]["name"] == "NewName"

    async def test_update_nonexistent_city_returns_404(self, client, admin_user):
        cookies = await login_user(client, admin_user["email"], admin_user["password"])
        headers, cookies = await auth_headers_and_cookies(cookies)

        r = await client.put(
            "/api/admin/geography/cities/999999",
            json={"name": "Ghost"},
            headers=headers,
            cookies=cookies,
        )
        assert r.status_code == 404


# ==========================================================================
# ADMIN: CREATE NEIGHBOURHOOD
# ==========================================================================

class TestAdminCreateNeighbourhood:

    async def test_admin_creates_neighbourhood(self, client, admin_user):
        cookies = await login_user(client, admin_user["email"], admin_user["password"])
        headers, cookies = await auth_headers_and_cookies(cookies)

        # Get a city ID
        r = await client.get("/api/countries/al/cities")
        city_id = r.json()["cities"][0]["id"]

        # Create neighbourhood
        r2 = await client.post(
            f"/api/admin/geography/cities/{city_id}/neighbourhoods",
            json={"name": "Blloku"},
            headers=headers,
            cookies=cookies,
        )
        assert r2.status_code == 201
        data = r2.json()
        assert data["neighbourhood"]["name"] == "Blloku"
        assert data["neighbourhood"]["city_id"] == city_id

        # Verify it appears in the public list
        r3 = await client.get(f"/api/countries/cities/{city_id}/neighbourhoods")
        names = [n["name"] for n in r3.json()["neighbourhoods"]]
        assert "Blloku" in names

    async def test_create_neighbourhood_invalid_city_returns_404(self, client, admin_user):
        cookies = await login_user(client, admin_user["email"], admin_user["password"])
        headers, cookies = await auth_headers_and_cookies(cookies)

        r = await client.post(
            "/api/admin/geography/cities/999999/neighbourhoods",
            json={"name": "Nowhere"},
            headers=headers,
            cookies=cookies,
        )
        assert r.status_code == 404


# ==========================================================================
# DELETE ENDPOINTS REMOVED
# ==========================================================================

class TestDeleteEndpointsRemoved:

    async def test_delete_city_endpoint_does_not_exist(self, client, admin_user):
        cookies = await login_user(client, admin_user["email"], admin_user["password"])
        headers, cookies = await auth_headers_and_cookies(cookies)

        r = await client.delete(
            "/api/admin/geography/cities/1",
            headers=headers,
            cookies=cookies,
        )
        assert r.status_code == 405  # Method Not Allowed

    async def test_delete_neighbourhood_endpoint_does_not_exist(self, client, admin_user):
        cookies = await login_user(client, admin_user["email"], admin_user["password"])
        headers, cookies = await auth_headers_and_cookies(cookies)

        r = await client.delete(
            "/api/admin/geography/neighbourhoods/1",
            headers=headers,
            cookies=cookies,
        )
        assert r.status_code == 405  # Method Not Allowed
