from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from .config import get_settings


Base = declarative_base()


def get_engine():
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, echo=False, future=True)
    return engine


_engine = get_engine()
AsyncSessionLocal = async_sessionmaker(bind=_engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session

