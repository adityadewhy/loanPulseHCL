"""
tests/conftest.py — Pytest fixtures for testing LoanMaster API.
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.database import AsyncSessionLocal
from app.models import User
from app.auth.utils import hash_password, create_access_token


@pytest_asyncio.fixture
async def async_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def auth_headers():
    """Provides a valid Bearer token for admin user."""
    async with AsyncSessionLocal() as db:
        admin = await db.get(User, 1)
        if not admin:
            admin = User(
                email="test_officer@loanpulse.local",
                hashed_password=hash_password("TestPass123!"),
                full_name="Test Officer",
                role="ADMIN",
            )
            db.add(admin)
            await db.commit()
            await db.refresh(admin)
        token = create_access_token({"sub": str(admin.id), "role": admin.role})
        return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture(autouse=True)
async def cleanup_db_pool():
    yield
    from app.database import engine
    await engine.dispose()

