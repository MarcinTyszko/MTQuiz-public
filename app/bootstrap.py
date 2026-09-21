"""Inicjalizacja instancji: konto administratora i przykładowy zestaw publiczny."""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import settings
from .database import create_all, session_scope
from .importer import normalise_payload
from .models import StudySet, User, UserRole, Visibility
from .security import hash_password
from .services import create_study_set, log_action

EXAMPLE_FILE = Path(__file__).resolve().parent / "data" / "przyklad_nerwy_czaszkowe.json"


def ensure_admin(db: Session) -> User | None:
    """Tworzy startowe konto administratora, jeżeli w bazie nie ma żadnego."""
    admin_exists = db.scalar(select(func.count(User.id)).where(User.role == UserRole.ADMIN))
    if admin_exists:
        return None

    username = settings.bootstrap_admin_username
    clash = db.scalar(select(User).where(func.lower(User.username) == username.lower()))
    if clash is not None:
        # Konto o tej nazwie istnieje jako zwykły użytkownik — podnosimy uprawnienia.
        clash.role = UserRole.ADMIN
        clash.is_active = True
        log_action(db, None, "bootstrap.admin_promoted", f"Nadano uprawnienia administratora kontu {clash.username}.")
        return clash

    admin = User(
        username=username,
        display_name="Administrator",
        password_hash=hash_password(settings.bootstrap_admin_password),
        role=UserRole.ADMIN,
        is_active=True,
        # Wymuszenie zmiany hasła przy pierwszym logowaniu.
        must_change_password=True,
    )
    db.add(admin)
    db.flush()
    log_action(
        db,
        None,
        "bootstrap.admin_created",
        f"Utworzono startowe konto administratora „{username}” z wymuszoną zmianą hasła.",
    )
    return admin


def ensure_example_set(db: Session, admin: User) -> None:
    """Dodaje przykładowy zestaw pokazowy, aby baza publiczna nie była pusta."""
    if not settings.seed_example_set:
        return
    if db.scalar(select(func.count(StudySet.id))):
        return
    if not EXAMPLE_FILE.exists():  # pragma: no cover - plik jest częścią obrazu
        return

    preview = normalise_payload(json.loads(EXAMPLE_FILE.read_text(encoding="utf-8")))
    if not preview.ok or preview.payload is None:  # pragma: no cover - plik walidowany w testach
        return

    payload = preview.payload.model_copy(update={"visibility": Visibility.PUBLIC})
    study_set = create_study_set(db, admin, payload)
    log_action(db, None, "bootstrap.example_set", f"Dodano przykładowy zestaw #{study_set.id}.")


def initialise() -> None:
    """Pełna inicjalizacja przy starcie aplikacji (idempotentna)."""
    settings.ensure_directories()
    create_all()

    with session_scope() as db:
        admin = ensure_admin(db)
        if admin is None:
            admin = db.scalar(
                select(User).where(User.role == UserRole.ADMIN).order_by(User.id.asc()).limit(1)
            )
        if admin is not None:
            db.flush()
            ensure_example_set(db, admin)
