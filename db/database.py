from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import config


class Database:
    """Lazy database engine and session factory wrapper."""

    def __init__(self) -> None:
        self._engine = None
        self._session_factory: Optional[async_sessionmaker[AsyncSession]] = None

    def _ensure_engine(self):
        if self._engine is None:
            from sqlalchemy.ext.asyncio import create_async_engine

            self._engine = create_async_engine(
                config.database_url,
                echo=config.log_level.upper() == "DEBUG",
                pool_pre_ping=True,
            )
            self._session_factory = async_sessionmaker(
                self._engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )

    @property
    def engine(self):
        self._ensure_engine()
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        self._ensure_engine()
        return self._session_factory  # type: ignore[return-value]

    async def close(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None


db = Database()


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session as a context manager."""
    async with db.session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
