from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.models import Base  # noqa: F401

engine = create_async_engine(settings.database_url, future=True)

async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
