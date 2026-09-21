"""Warstwa dostępu do bazy danych (SQLite + SQLAlchemy 2.0)."""
from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    """Bazowa klasa deklaratywna dla wszystkich modeli."""


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None
_lock = threading.RLock()


def _configure_sqlite(dbapi_connection, _connection_record) -> None:
    """Włącza klucze obce oraz tryb WAL dla większej odporności zapisu."""
    if not isinstance(dbapi_connection, sqlite3.Connection):  # pragma: no cover
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=10000")
    cursor.close()


def _build_engine() -> Engine:
    settings.ensure_directories()
    engine = create_engine(
        settings.database_url,
        echo=False,
        future=True,
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    event.listen(engine, "connect", _configure_sqlite)
    return engine


def get_engine() -> Engine:
    global _engine, _session_factory
    with _lock:
        if _engine is None:
            _engine = _build_engine()
            _session_factory = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False, future=True)
        return _engine


def get_session_factory() -> sessionmaker[Session]:
    get_engine()
    assert _session_factory is not None
    return _session_factory


def reset_engine() -> None:
    """Zamyka pulę połączeń i wymusza ponowne otwarcie pliku bazy.

    Używane po przywróceniu kopii zapasowej, gdy plik SQLite został podmieniony
    pod działającą aplikacją.
    """
    global _engine, _session_factory
    with _lock:
        if _engine is not None:
            _engine.dispose()
        _engine = None
        _session_factory = None


@contextmanager
def session_scope() -> Iterator[Session]:
    """Kontekst transakcyjny z automatycznym commit/rollback."""
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Iterator[Session]:
    """Zależność FastAPI dostarczająca sesję bazodanową."""
    factory = get_session_factory()
    session = factory()
    try:
        yield session
    finally:
        session.close()


def create_all() -> None:
    """Tworzy schemat bazy danych (idempotentnie)."""
    from . import models  # noqa: F401  - rejestracja modeli w metadanych

    Base.metadata.create_all(bind=get_engine())
