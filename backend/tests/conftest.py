import os
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.config import get_settings
from app.db import engine as engine_module
from app.db import session as session_module
from app.db.base import Base
from app.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def db_client(monkeypatch):
    """Client backed by TEST_DATABASE_URL; skips when it is not configured."""
    url = os.getenv("TEST_DATABASE_URL") or get_settings().test_database_url
    if not url:
        pytest.skip("TEST_DATABASE_URL not set — skipping DB-backed tests")

    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    engine_module.reset_engine()
    session_module.reset_sessionmaker()

    engine = engine_module.get_engine()
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    # Remove only rows created by this suite (marked by the email domain / slug prefix).
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM users WHERE email LIKE '%@plauda-test.com'"))
        await conn.execute(text("DELETE FROM merchants WHERE slug LIKE 'pytest-%'"))
    await engine.dispose()
    engine_module.reset_engine()
    session_module.reset_sessionmaker()
    get_settings.cache_clear()


async def register_merchant(db_client: AsyncClient, store_name: str | None = None) -> dict:
    """Register a fresh merchant and return auth headers + merchant payload."""
    name = store_name or f"Pytest Store {uuid.uuid4().hex[:6]}"
    email = f"ada-{uuid.uuid4().hex[:10]}@plauda-test.com"
    resp = await db_client.post(
        "/auth/register",
        json={"store_name": name, "email": email, "password": "s3cret-pass"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return {
        "headers": {"Authorization": f"Bearer {body['access_token']}"},
        "merchant": body["user"]["merchant"],
        "email": email,
    }


@pytest.fixture
async def merchant_auth(db_client):
    return await register_merchant(db_client)


@pytest.fixture
async def db_session(db_client):
    """Direct session on the test database (same engine as db_client)."""
    async with session_module.get_sessionmaker()() as session:
        yield session
