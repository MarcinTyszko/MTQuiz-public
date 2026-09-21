"""Endpointy uwierzytelniania i zarządzania własnym kontem."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import func, select

from ..config import settings
from ..deps import CurrentUser, DbSession, OptionalUser, clear_session_cookie, issue_session_cookie
from ..models import User, UserRole, utcnow
from ..schemas import (
    ChangePasswordRequest,
    LoginRequest,
    MessageOut,
    RegisterRequest,
    UserOut,
)
from ..security import (
    hash_password,
    needs_rehash,
    validate_password_strength,
    validate_username,
    verify_password,
)
from ..services import log_action

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, response: Response, db: DbSession) -> UserOut:
    if not settings.allow_registration:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Rejestracja nowych kont jest wyłączona.")

    try:
        username = validate_username(payload.username)
        password = validate_password_strength(payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    existing = db.scalar(select(User).where(func.lower(User.username) == username.lower()))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ta nazwa użytkownika jest już zajęta.")

    if payload.email:
        email_taken = db.scalar(select(User).where(func.lower(User.email) == payload.email.lower()))
        if email_taken is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ten adres e-mail jest już używany.")

    user = User(
        username=username,
        email=payload.email,
        display_name=(payload.display_name or "").strip() or None,
        password_hash=hash_password(password),
        role=UserRole.USER,
        is_active=True,
        must_change_password=False,
        last_login_at=utcnow(),
    )
    db.add(user)
    log_action(db, user, "user.register", f"Utworzono konto {username}.")
    db.commit()
    db.refresh(user)

    issue_session_cookie(response, user)
    return UserOut.model_validate(user)


@router.post("/login", response_model=UserOut)
def login(payload: LoginRequest, response: Response, db: DbSession) -> UserOut:
    username = payload.username.strip()
    user = db.scalar(select(User).where(func.lower(User.username) == username.lower()))
    if user is None and "@" in username:
        user = db.scalar(select(User).where(func.lower(User.email) == username.lower()))

    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Nieprawidłowa nazwa użytkownika lub hasło."
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Konto zostało dezaktywowane.")

    # Odświeżenie hashu, gdy zmieniły się parametry Argon2.
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(payload.password)

    user.last_login_at = utcnow()
    db.commit()
    db.refresh(user)

    issue_session_cookie(response, user, remember=payload.remember)
    return UserOut.model_validate(user)


@router.post("/logout", response_model=MessageOut)
def logout(response: Response) -> MessageOut:
    clear_session_cookie(response)
    return MessageOut(ok=True, message="Wylogowano.")


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.get("/session", response_model=UserOut | None)
def session_state(user: OptionalUser) -> UserOut | None:
    return UserOut.model_validate(user) if user else None


@router.post("/change-password", response_model=UserOut)
def change_password(
    payload: ChangePasswordRequest,
    response: Response,
    user: CurrentUser,
    db: DbSession,
) -> UserOut:
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Obecne hasło jest nieprawidłowe.")

    try:
        new_password = validate_password_strength(payload.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    if verify_password(new_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Nowe hasło musi różnić się od obecnego.",
        )

    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    log_action(db, user, "user.password_changed", f"Użytkownik {user.username} zmienił hasło.")
    db.commit()
    db.refresh(user)

    # Nowy hash unieważnia stare tokeny — wydajemy świeże ciasteczko.
    issue_session_cookie(response, user)
    return UserOut.model_validate(user)
