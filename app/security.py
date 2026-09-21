"""Hashowanie haseł (Argon2id) oraz obsługa tokenów sesyjnych JWT."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError, VerificationError

from .config import settings

# Parametry dobrane pod samohostowaną instancję: bezpieczne, a zarazem szybkie
# na maszynie klasy NAS/mini-PC.
_hasher = PasswordHasher(time_cost=2, memory_cost=64 * 1024, parallelism=2, hash_len=32, salt_len=16)

USERNAME_RE = re.compile(r"^[a-zA-Z0-9._-]{3,32}$")
MIN_PASSWORD_LENGTH = 8


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        _hasher.verify(password_hash, password)
        return True
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """Informuje, czy hash należy odświeżyć po zmianie parametrów Argon2."""
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def validate_username(username: str) -> str:
    username = (username or "").strip()
    if not USERNAME_RE.match(username):
        raise ValueError(
            "Nazwa użytkownika musi mieć 3-32 znaki i zawierać wyłącznie litery, cyfry oraz znaki . _ -"
        )
    return username


def validate_password_strength(password: str) -> str:
    """Sprawdza minimalne wymagania hasła i zwraca je bez zmian."""
    password = password or ""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Hasło musi mieć co najmniej {MIN_PASSWORD_LENGTH} znaków.")
    if len(password) > 256:
        raise ValueError("Hasło nie może przekraczać 256 znaków.")
    if password.lower() in {"admin", "password", "haslo", "12345678", "qwerty123"}:
        raise ValueError("To hasło jest zbyt popularne. Wybierz trudniejsze.")
    if password.strip() == "":
        raise ValueError("Hasło nie może składać się wyłącznie ze spacji.")
    return password


def create_session_token(user_id: int, *, token_version: str, expires_minutes: int | None = None) -> str:
    """Tworzy token JWT reprezentujący sesję użytkownika.

    ``token_version`` jest pochodną hashu hasła, dzięki czemu zmiana hasła
    automatycznie unieważnia wszystkie wcześniej wydane tokeny.
    """
    now = datetime.now(timezone.utc)
    ttl = expires_minutes if expires_minutes is not None else settings.session_ttl_minutes
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "ver": token_version,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ttl)).timestamp()),
        "iss": settings.app_name,
    }
    return jwt.encode(payload, settings.resolve_secret_key(), algorithm=settings.jwt_algorithm)


def decode_session_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(
            token,
            settings.resolve_secret_key(),
            algorithms=[settings.jwt_algorithm],
            issuer=settings.app_name,
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError:
        return None


def token_version_for(password_hash: str) -> str:
    """Skrót hashu hasła używany jako wersja tokenu."""
    import hashlib

    return hashlib.sha256(password_hash.encode("utf-8")).hexdigest()[:16]
