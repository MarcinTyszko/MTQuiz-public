"""Zależności FastAPI: bieżący użytkownik, kontrola ról, obsługa ciasteczka sesji."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import User
from .security import create_session_token, decode_session_token, token_version_for

DbSession = Annotated[Session, Depends(get_db)]


def _load_user_from_request(request: Request, db: Session) -> User | None:
    token = request.cookies.get(settings.cookie_name)
    if not token:
        header = request.headers.get("Authorization", "")
        if header.lower().startswith("bearer "):
            token = header[7:].strip()
    if not token:
        return None

    payload = decode_session_token(token)
    if not payload:
        return None

    try:
        user_id = int(payload.get("sub", ""))
    except (TypeError, ValueError):
        return None

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        return None
    # Zmiana hasła unieważnia wszystkie wcześniejsze tokeny.
    if payload.get("ver") != token_version_for(user.password_hash):
        return None
    return user


def get_optional_user(request: Request, db: DbSession) -> User | None:
    user = getattr(request.state, "user", None)
    if user is not None:
        return user
    user = _load_user_from_request(request, db)
    request.state.user = user
    return user


OptionalUser = Annotated[User | None, Depends(get_optional_user)]


def get_current_user(user: OptionalUser) -> User:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Wymagane zalogowanie.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_unlocked_user(user: CurrentUser) -> User:
    """Użytkownik z aktywną sesją, który nie musi zmieniać hasła.

    Blokuje dostęp do funkcji aplikacji do czasu ustawienia własnego hasła
    (dotyczy startowego konta ``admin``/``admin``).
    """
    if user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Zanim przejdziesz dalej, ustaw nowe hasło.",
        )
    return user


UnlockedUser = Annotated[User, Depends(get_unlocked_user)]


def get_admin_user(user: UnlockedUser) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Wymagane uprawnienia administratora.")
    return user


AdminUser = Annotated[User, Depends(get_admin_user)]


def issue_session_cookie(response: Response, user: User, *, remember: bool = True) -> str:
    """Ustawia ciasteczko sesyjne HttpOnly z tokenem JWT."""
    ttl = settings.session_ttl_minutes if remember else 60 * 12
    token = create_session_token(user.id, token_version=token_version_for(user.password_hash), expires_minutes=ttl)
    response.set_cookie(
        key=settings.cookie_name,
        value=token,
        max_age=ttl * 60 if remember else None,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
    )
    return token


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=settings.cookie_name, path="/")
