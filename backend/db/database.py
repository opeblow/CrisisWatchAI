from __future__ import annotations

import os
from typing import AsyncGenerator

from sqlalchemy import create_engine, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./crisiswatch.db",
)

ASYNC_DATABASE_URL = DATABASE_URL
if DATABASE_URL.startswith("postgresql://"):
    ASYNC_DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("sqlite://"):
    ASYNC_DATABASE_URL = DATABASE_URL.replace("sqlite://", "sqlite+aiosqlite://", 1)

SYNC_DATABASE_URL = DATABASE_URL
if "asyncpg" in SYNC_DATABASE_URL:
    SYNC_DATABASE_URL = SYNC_DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://", 1)
elif "aiosqlite" in SYNC_DATABASE_URL:
    SYNC_DATABASE_URL = SYNC_DATABASE_URL.replace("sqlite+aiosqlite://", "sqlite://", 1)


class Base(DeclarativeBase):
    pass


async_engine = create_async_engine(
    ASYNC_DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    **({"pool_size": 20, "max_overflow": 10} if "postgresql" in DATABASE_URL else {}),
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

sync_engine = create_engine(
    SYNC_DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    **({"pool_size": 10, "max_overflow": 5} if "postgresql" in DATABASE_URL else {}),
)

SyncSessionLocal = sessionmaker(bind=sync_engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_sync_db():
    db = SyncSessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


async def init_db() -> None:
    async with async_engine.begin() as conn:
        from db.models import (  # noqa: F401
            CrisisAlert,
            CrisisEvent,
            Forecast,
            Prediction,
            Report,
        )

        await conn.run_sync(Base.metadata.create_all)


def init_db_sync() -> None:
    from db.models import (  # noqa: F401
        CrisisAlert,
        CrisisEvent,
        Forecast,
        Prediction,
        Report,
    )

    Base.metadata.create_all(bind=sync_engine)
