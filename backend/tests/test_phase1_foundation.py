import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app


@pytest.mark.asyncio
async def test_docs_page_loads():
    """Verify that OpenAPI interactive /docs loads successfully."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/docs")
        assert response.status_code == 200
        assert "swagger" in response.text.lower() or "openapi" in response.text.lower() or "html" in response.text.lower()


@pytest.mark.asyncio
async def test_openapi_json():
    """Verify OpenAPI schema generation."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/openapi.json")
        assert response.status_code == 200
        data = response.json()
        assert "paths" in data
        assert "/api/v1/health/ping" in data["paths"]


@pytest.mark.asyncio
async def test_health_ping_returns_200():
    """Verify /api/v1/health/ping returns 200 and required fields."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health/ping")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "aeris-x-api"
        assert "synthetic_banner" in data
        assert "SYNTHETIC DEMONSTRATION DATA" in data["synthetic_banner"]


@pytest.mark.asyncio
async def test_health_status_annunciators():
    """Verify system annunciators for frontend status bar."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "annunciators" in data
        assert "data_link" in data["annunciators"]
        assert "ai_engine" in data["annunciators"]
        assert "database" in data["annunciators"]


@pytest.mark.asyncio
async def test_structured_error_format_404():
    """Verify 404 returns formatted {error: {code, message, details}}."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/nonexistent-endpoint")
        assert response.status_code == 404
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "NOT_FOUND"
        assert "message" in data["error"]
