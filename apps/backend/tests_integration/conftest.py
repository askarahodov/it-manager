import os
import uuid
import asyncio
import sys
from pathlib import Path

import httpx
import pytest
import pytest_asyncio


@pytest.fixture(scope="session")
def event_loop():
    """
    Важно для интеграционных тестов:
    - SQLAlchemy/asyncpg пул соединений привязывается к event loop.
    - pytest-asyncio по умолчанию может создавать новый loop на каждый тест,
      что приводит к ошибке вида "Future attached to a different loop".
    Поэтому используем один loop на всю сессию тестов.
    """

    loop = asyncio.new_event_loop()
    try:
        yield loop
    finally:
        loop.close()


# Гарантируем, что `import app` работает независимо от текущей директории запуска pytest.
repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))


@pytest_asyncio.fixture(scope="session", autouse=True)
async def bootstrap_admin_user():
    """Гарантирует наличие admin пользователя в тестовой БД.

    Важно: httpx.ASGITransport не управляет lifespan FastAPI, поэтому bootstrap из lifespan
    в интеграционных тестах не выполнится автоматически.
    """
    assert os.environ.get("DATABASE_URL"), "DATABASE_URL должен быть задан для integration тестов"

    from sqlalchemy import select

    from app.core.hash import get_password_hash
    from app.db import async_session
    from app.db.models import User, UserRole

    async with async_session() as db:
        res = await db.execute(select(User).where(User.email == "admin@it.local").limit(1))
        existing = res.scalar_one_or_none()
        if existing is None:
            db.add(User(email="admin@it.local", password_hash=get_password_hash("admin123"), role=UserRole.admin))
            await db.commit()


@pytest_asyncio.fixture
async def client() -> httpx.AsyncClient:
    # Важно: DATABASE_URL должен быть задан снаружи (скриптом), чтобы app.db.engine создался корректно.
    assert os.environ.get("DATABASE_URL"), "DATABASE_URL должен быть задан для integration тестов"

    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def admin_token(client: httpx.AsyncClient) -> str:
    resp = await client.post("/api/v1/auth/login", json={"email": "admin@it.local", "password": "admin123"})
    resp.raise_for_status()
    return resp.json()["access_token"]


@pytest.fixture
def uniq() -> str:
    return uuid.uuid4().hex[:8]
