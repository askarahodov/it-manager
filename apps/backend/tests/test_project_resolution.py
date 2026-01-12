from dataclasses import dataclass

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Project
from app.services.projects import (
    ProjectAccessDenied,
    ProjectNotFound,
    resolve_current_project_id,
)


pytestmark = pytest.mark.asyncio


async def _make_db() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Project.__table__.create)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return async_session()


@dataclass(frozen=True, slots=True)
class _Principal:
    allowed_project_ids: list[int] | None


def _principal(*, allowed_project_ids):
    return _Principal(allowed_project_ids=allowed_project_ids)


async def test_resolve_explicit_project_ok():
    db = await _make_db()
    async with db:
        db.add_all([Project(id=1, name="default"), Project(id=2, name="p2")])
        await db.commit()

        pid = await resolve_current_project_id(db, _principal(allowed_project_ids=[2]), 2)
        assert pid == 2


async def test_resolve_explicit_project_not_found():
    db = await _make_db()
    async with db:
        with pytest.raises(ProjectNotFound):
            await resolve_current_project_id(db, _principal(allowed_project_ids=None), 999)


async def test_resolve_explicit_project_denied():
    db = await _make_db()
    async with db:
        db.add(Project(id=1, name="default"))
        await db.commit()

        with pytest.raises(ProjectAccessDenied):
            await resolve_current_project_id(db, _principal(allowed_project_ids=[]), 1)


async def test_resolve_implicit_allowlist_prefers_default_when_allowed():
    db = await _make_db()
    async with db:
        db.add_all([Project(id=1, name="default"), Project(id=2, name="p2")])
        await db.commit()

        pid = await resolve_current_project_id(db, _principal(allowed_project_ids=[1, 2]), None)
        assert pid == 1


async def test_resolve_implicit_allowlist_picks_first_allowed_when_default_denied():
    db = await _make_db()
    async with db:
        db.add_all([Project(id=1, name="default"), Project(id=2, name="p2"), Project(id=3, name="p3")])
        await db.commit()

        pid = await resolve_current_project_id(db, _principal(allowed_project_ids=[3, 2]), None)
        assert pid == 2


async def test_resolve_implicit_allowlist_empty_denied():
    db = await _make_db()
    async with db:
        db.add(Project(id=1, name="default"))
        await db.commit()

        with pytest.raises(ProjectAccessDenied):
            await resolve_current_project_id(db, _principal(allowed_project_ids=[]), None)


async def test_resolve_implicit_allowlist_no_existing_projects_denied():
    db = await _make_db()
    async with db:
        db.add(Project(id=1, name="default"))
        await db.commit()

        with pytest.raises(ProjectAccessDenied):
            await resolve_current_project_id(db, _principal(allowed_project_ids=[999]), None)


async def test_resolve_implicit_no_allowlist_prefers_default():
    db = await _make_db()
    async with db:
        db.add_all([Project(id=1, name="default"), Project(id=2, name="p2")])
        await db.commit()

        pid = await resolve_current_project_id(db, _principal(allowed_project_ids=None), None)
        assert pid == 1


async def test_resolve_implicit_no_allowlist_falls_back_to_first_project():
    db = await _make_db()
    async with db:
        db.add_all([Project(id=2, name="p2"), Project(id=3, name="p3")])
        await db.commit()

        pid = await resolve_current_project_id(db, _principal(allowed_project_ids=None), None)
        assert pid == 2
