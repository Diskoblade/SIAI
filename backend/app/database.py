"""Database engine, session factory, and declarative base.

The engine is configured so that migrating from SQLite to PostgreSQL later is
a one-line change (the DATABASE_URL). The SQLite-only `check_same_thread`
argument is applied conditionally so it does not leak into a Postgres setup.
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

# SQLite needs `check_same_thread=False` for use with FastAPI's threadpool.
# Other databases (e.g. PostgreSQL) must not receive this argument.
_connect_args = (
    {"check_same_thread": False}
    if settings.database_url.startswith("sqlite")
    else {}
)

engine = create_engine(
    settings.database_url,
    connect_args=_connect_args,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Declarative base class for all ORM models."""


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables. Import models first so they register on the metadata.

    For the prototype this is sufficient. A production migration to PostgreSQL
    would introduce Alembic; the model definitions remain unchanged.
    """
    # Imported for their side effect of registering with Base.metadata.
    from app.models import (  # noqa: F401
        approval_note,
        audit,
        conversation,
        department,
        document,
        ide_code_project,
        ide_workspace,
        user,
    )
    from app.schema_compat import ensure_private_knowledge_columns

    Base.metadata.create_all(bind=engine)
    ensure_private_knowledge_columns(engine)
