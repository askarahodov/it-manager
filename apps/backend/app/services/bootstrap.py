from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hash import get_password_hash
from app.db.models import Project, User, UserRole

logger = logging.getLogger(__name__)


async def ensure_bootstrap_admin(db: AsyncSession, email: str, password: str) -> None:
    """Создаёт admin-пользователя при первом старте (best-effort).

    Важно: используем только если в БД ещё нет ни одного пользователя.
    Это обеспечивает UX "вошёл и работаешь" в dev окружении, но не мешает
    нормальной эксплуатации/миграции в проде.
    """
    email = (email or "").strip().lower()
    if not email or not password:
        logger.warning("Bootstrap admin пропущен: пустой email/password")
        return

    existing_any = await db.execute(select(User.id).limit(1))
    if existing_any.scalar_one_or_none() is not None:
        return

    admin = User(email=email, password_hash=get_password_hash(password), role=UserRole.admin)
    db.add(admin)
    await db.commit()
    logger.info("Bootstrap admin создан email=%s", email)


async def ensure_default_project(db: AsyncSession, *, name: str = "default") -> None:
    """Создаёт проект по умолчанию (best-effort).

    Важно:
    - не ломаем старт приложения, если миграции ещё не применены;
    - если проекты уже есть — ничего не делаем.
    """

    try:
        existing_any = await db.execute(select(Project.id).limit(1))
        if existing_any.scalar_one_or_none() is not None:
            return
        db.add(Project(name=name, description="Проект по умолчанию (dev)"))
        await db.commit()
        logger.info("Создан default project name=%s", name)
    except Exception as exc:  # noqa: BLE001
        try:
            await db.rollback()
        except Exception:
            pass
        logger.debug("ensure_default_project skipped: %s", exc)
