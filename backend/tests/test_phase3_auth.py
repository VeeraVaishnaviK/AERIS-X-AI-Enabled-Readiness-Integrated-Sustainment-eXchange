import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.synthetic.seed_users import DEMO_PASSWORD


@pytest.mark.asyncio
async def test_auth_login_success():
    """Verify login returns JWT access and refresh tokens."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/login",
            json={"username_or_email": "admin", "password": DEMO_PASSWORD},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["role"] == "ADMIN"
        assert data["username"] == "admin"


@pytest.mark.asyncio
async def test_auth_login_failure():
    """Verify failed login returns 401 structured error."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/login",
            json={"username_or_email": "admin", "password": "WrongPassword123!"},
        )
        assert response.status_code == 401
        data = response.json()
        assert data["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_auth_refresh_token():
    """Verify token refresh yields valid new access token."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        login_res = await client.post(
            "/api/v1/auth/login",
            json={"username_or_email": "engineer", "password": DEMO_PASSWORD},
        )
        refresh_token = login_res.json()["refresh_token"]

        refresh_res = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert refresh_res.status_code == 200
        data = refresh_res.json()
        assert "access_token" in data
        assert data["role"] == "MAINTENANCE_ENGINEER"


@pytest.mark.asyncio
async def test_rbac_matrix_isolation():
    """Verify RBAC role-permission matrix restricts unauthorized access and permits authorized roles."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Obtain tokens for each role
        tokens = {}
        for role_user in ["admin", "commander", "engineer", "logistics", "technician", "auditor"]:
            res = await client.post(
                "/api/v1/auth/login",
                json={"username_or_email": role_user, "password": DEMO_PASSWORD},
            )
            assert res.status_code == 200
            tokens[role_user] = res.json()["access_token"]

        # 1. Commander can access commander endpoint, but technician cannot
        res_cmd = await client.get(
            "/api/v1/rbac/commander-only",
            headers={"Authorization": f"Bearer {tokens['commander']}"},
        )
        assert res_cmd.status_code == 200

        res_tech_denied = await client.get(
            "/api/v1/rbac/commander-only",
            headers={"Authorization": f"Bearer {tokens['technician']}"},
        )
        assert res_tech_denied.status_code == 403
        assert res_tech_denied.json()["error"]["code"] == "FORBIDDEN"

        # 2. Logistics Officer can access logistics endpoint, but engineer cannot
        res_log = await client.get(
            "/api/v1/rbac/logistics-only",
            headers={"Authorization": f"Bearer {tokens['logistics']}"},
        )
        assert res_log.status_code == 200

        res_eng_denied = await client.get(
            "/api/v1/rbac/logistics-only",
            headers={"Authorization": f"Bearer {tokens['engineer']}"},
        )
        assert res_eng_denied.status_code == 403

        # 3. Technician can access technician endpoint
        res_tech = await client.get(
            "/api/v1/rbac/technician-only",
            headers={"Authorization": f"Bearer {tokens['technician']}"},
        )
        assert res_tech.status_code == 200

        # 4. Auditor can access auditor endpoint
        res_aud = await client.get(
            "/api/v1/rbac/auditor-only",
            headers={"Authorization": f"Bearer {tokens['auditor']}"},
        )
        assert res_aud.status_code == 200

        # 5. Admin can access all endpoints (role override)
        for ep in ["admin-only", "commander-only", "engineer-only", "logistics-only", "technician-only", "auditor-only"]:
            res_admin = await client.get(
                f"/api/v1/rbac/{ep}",
                headers={"Authorization": f"Bearer {tokens['admin']}"},
            )
            assert res_admin.status_code == 200


@pytest.mark.asyncio
async def test_auth_me_endpoint():
    """Verify /me returns the current profile."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        login_res = await client.post(
            "/api/v1/auth/login",
            json={"username_or_email": "commander", "password": DEMO_PASSWORD},
        )
        token = login_res.json()["access_token"]

        me_res = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert me_res.status_code == 200
        data = me_res.json()
        assert data["username"] == "commander"
        assert data["role"] == "COMMANDER"
