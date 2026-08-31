"""Declarative base, engine, and session plumbing."""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator

from sqlalchemy import JSON, DateTime, TypeDecorator, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

# JSONB on Postgres, plain JSON elsewhere so the suite can run on SQLite.
JsonDict = JSON().with_variant(JSONB(), "postgresql")


class UtcDateTime(TypeDecorator):
    """A timestamp that is always timezone-aware UTC on the way in and out.

    Postgres hands back aware datetimes from ``TIMESTAMPTZ``; SQLite hands back
    naive ones. Comparing the two raises ``TypeError``, so without this every
    timestamp comparison is a dialect-dependent landmine — expiry checks most of
    all. Normalizing in the type keeps that concern out of every call site.

    DDL is unchanged (``TIMESTAMP WITH TIME ZONE``), so this needs no migration.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: dt.datetime | None, dialect) -> dt.datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt.timezone.utc)
        return value.astimezone(dt.timezone.utc)

    def process_result_value(self, value: dt.datetime | None, dialect) -> dt.datetime | None:
        if value is None:
            return None
        return value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


_settings = get_settings()
engine = create_engine(_settings.database_url, echo=_settings.sql_echo, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    with SessionLocal() as session:
        yield session
