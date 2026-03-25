"""Async SQLAlchemy engine and session factory for PostgreSQL."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config.settings import get_settings


class Base(DeclarativeBase):
    """Declarative base for all SQLAlchemy ORM models."""


_settings = get_settings()

engine = create_async_engine(
    _settings.database_url,
    echo=False,
    pool_size=5,
    max_overflow=10,
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncSession:  # type: ignore[misc]
    """FastAPI dependency that yields an async DB session."""
    async with async_session() as session:
        yield session
