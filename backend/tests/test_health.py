"""
Health endpoint tests.

Uses httpx.AsyncClient with ASGITransport so we exercise the real FastAPI
routing stack without starting a server. init_db is patched to a no-op so
the test doesn't write a .db file to disk.
"""

import pytest
from unittest.mock import AsyncMock, patch

from httpx import ASGITransport, AsyncClient

from backend.app.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def _client() -> AsyncClient:
    """Return an async test client with init_db patched out."""
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_health_returns_200() -> None:
    with patch("backend.app.db.session.init_db", new_callable=AsyncMock), \
         patch("backend.app.db.session.close_db_engine", new_callable=AsyncMock):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            r = await ac.get("/health")

    assert r.status_code == 200


@pytest.mark.asyncio
async def test_health_body() -> None:
    with patch("backend.app.db.session.init_db", new_callable=AsyncMock), \
         patch("backend.app.db.session.close_db_engine", new_callable=AsyncMock):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            r = await ac.get("/health")

    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "scamslayer"


@pytest.mark.asyncio
async def test_unknown_route_returns_404() -> None:
    with patch("backend.app.db.session.init_db", new_callable=AsyncMock), \
         patch("backend.app.db.session.close_db_engine", new_callable=AsyncMock):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            r = await ac.get("/this-route-does-not-exist")

    assert r.status_code == 404


@pytest.mark.asyncio
async def test_openapi_schema_accessible() -> None:
    """Sanity-check that the auto-generated OpenAPI schema includes our routes."""
    with patch("backend.app.db.session.init_db", new_callable=AsyncMock), \
         patch("backend.app.db.session.close_db_engine", new_callable=AsyncMock):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            r = await ac.get("/openapi.json")

    assert r.status_code == 200
    schema = r.json()
    paths = schema["paths"]
    assert "/health" in paths
    assert "/calls" in paths
    assert "/personas" in paths
    assert "/clips" in paths
