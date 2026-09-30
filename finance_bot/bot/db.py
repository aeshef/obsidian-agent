from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy import event

from .config import get_settings


Base = declarative_base()


def get_engine():
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, echo=False, future=True)
    if engine.url.get_backend_name() == "sqlite":
        @event.listens_for(engine.sync_engine, "connect")
        def _foreign_keys(connection, _record):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    return engine


_engine = get_engine()
AsyncSessionLocal = async_sessionmaker(bind=_engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
