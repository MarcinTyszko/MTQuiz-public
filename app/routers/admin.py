"""Panel administracyjny: konta, moderacja, kopie zapasowe."""
from __future__ import annotations

import secrets

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select

from ..backup import BackupError, create_backup_archive, restore_from_bytes
from ..config import settings
from ..deps import AdminUser, DbSession
from ..models import (
    AuditLog,
    Flashcard,
    Question,
    StudySession,
    StudySet,
    User,
    UserRole,
    Visibility,
)
from ..schemas import (
    AdminPasswordReset,
    AdminSetModeration,
    AdminStats,
    AdminUserUpdate,
    AuditLogOut,
    MessageOut,
    StudySetSummary,
    UserAdminOut,
)
from ..security import hash_password, validate_password_strength
from ..services import counts_for_sets, log_action, set_query_with_relations, to_summary

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _count_admins(db) -> int:
    return db.scalar(
        select(func.count(User.id)).where(User.role == UserRole.ADMIN, User.is_active.is_(True))
    ) or 0


@router.get("/stats", response_model=AdminStats)
def stats(admin: AdminUser, db: DbSession) -> AdminStats:
    database_size = settings.database_path.stat().st_size if settings.database_path.exists() else 0
    return AdminStats(
        users_total=db.scalar(select(func.count(User.id))) or 0,
        users_active=db.scalar(select(func.count(User.id)).where(User.is_active.is_(True))) or 0,
        admins=db.scalar(select(func.count(User.id)).where(User.role == UserRole.ADMIN)) or 0,
        sets_total=db.scalar(select(func.count(StudySet.id))) or 0,
        sets_public=db.scalar(
            select(func.count(StudySet.id)).where(
                StudySet.visibility == Visibility.PUBLIC, StudySet.is_published.is_(True)
            )
        )
        or 0,
        sets_unpublished=db.scalar(
            select(func.count(StudySet.id)).where(StudySet.is_published.is_(False))
        )
        or 0,
        cards_total=db.scalar(select(func.count(Flashcard.id))) or 0,
        questions_total=db.scalar(select(func.count(Question.id))) or 0,
        sessions_total=db.scalar(select(func.count(StudySession.id))) or 0,
        database_size_bytes=database_size,
        database_path=str(settings.database_path),
    )


# --------------------------------------------------------------------------- #
# Użytkownicy
# --------------------------------------------------------------------------- #
@router.get("/users", response_model=list[UserAdminOut])
def list_users(
    admin: AdminUser,
    db: DbSession,
    q: str = Query(default="", max_length=64),
) -> list[UserAdminOut]:
    stmt = select(User)
    if q.strip():
        needle = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(func.lower(User.username).like(needle), func.lower(User.email).like(needle))
        )
    users = list(db.scalars(stmt.order_by(User.created_at.asc())))

    sets_by_user = dict(
        db.execute(select(StudySet.author_id, func.count(StudySet.id)).group_by(StudySet.author_id)).all()
    )
    public_by_user = dict(
        db.execute(
            select(StudySet.author_id, func.count(StudySet.id))
            .where(StudySet.visibility == Visibility.PUBLIC, StudySet.is_published.is_(True))
            .group_by(StudySet.author_id)
        ).all()
    )
    sessions_by_user = dict(
        db.execute(select(StudySession.user_id, func.count(StudySession.id)).group_by(StudySession.user_id)).all()
    )

    return [
        UserAdminOut(
            **{
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "display_name": user.display_name,
                "role": user.role,
                "is_active": user.is_active,
                "must_change_password": user.must_change_password,
                "created_at": user.created_at,
                "last_login_at": user.last_login_at,
                "sets_count": sets_by_user.get(user.id, 0),
                "public_sets_count": public_by_user.get(user.id, 0),
                "sessions_count": sessions_by_user.get(user.id, 0),
            }
        )
        for user in users
    ]


@router.patch("/users/{user_id}", response_model=UserAdminOut)
def update_user(user_id: int, payload: AdminUserUpdate, admin: AdminUser, db: DbSession) -> UserAdminOut:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nie znaleziono użytkownika.")

    if payload.is_active is not None and payload.is_active is False:
        if user.id == admin.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nie możesz dezaktywować własnego konta.")
        if user.role == UserRole.ADMIN and _count_admins(db) <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="To jedyny aktywny administrator — nie można go dezaktywować.",
            )
        user.is_active = False
    elif payload.is_active is True:
        user.is_active = True

    if payload.role is not None and payload.role != user.role:
        if user.id == admin.id and payload.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Nie możesz odebrać uprawnień samemu sobie."
            )
        if user.role == UserRole.ADMIN and payload.role == UserRole.USER and _count_admins(db) <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="W systemie musi pozostać co najmniej jeden administrator.",
            )
        user.role = payload.role

    if payload.must_change_password is not None:
        user.must_change_password = payload.must_change_password

    if payload.display_name is not None:
        user.display_name = payload.display_name.strip() or None

    log_action(db, admin, "admin.user_update", f"Zmodyfikowano konto {user.username} (#{user.id}).")
    db.commit()
    db.refresh(user)

    return UserAdminOut(
        id=user.id,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        is_active=user.is_active,
        must_change_password=user.must_change_password,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


@router.post("/users/{user_id}/reset-password", response_model=MessageOut)
def reset_password(user_id: int, payload: AdminPasswordReset, admin: AdminUser, db: DbSession) -> MessageOut:
    """Ustawia nowe hasło tymczasowe i wymusza jego zmianę przy następnym logowaniu."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nie znaleziono użytkownika.")

    new_password = payload.new_password or secrets.token_urlsafe(9)
    try:
        validate_password_strength(new_password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    user.password_hash = hash_password(new_password)
    user.must_change_password = True
    log_action(db, admin, "admin.password_reset", f"Zresetowano hasło konta {user.username} (#{user.id}).")
    db.commit()

    return MessageOut(
        ok=True,
        message=f"Hasło tymczasowe dla „{user.username}”: {new_password} — przekaż je użytkownikowi bezpiecznym kanałem.",
    )


@router.delete("/users/{user_id}", response_model=MessageOut)
def delete_user(user_id: int, admin: AdminUser, db: DbSession) -> MessageOut:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nie znaleziono użytkownika.")
    if user.id == admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nie możesz usunąć własnego konta.")
    if user.role == UserRole.ADMIN and _count_admins(db) <= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="W systemie musi pozostać co najmniej jeden administrator.",
        )

    username = user.username
    db.delete(user)
    log_action(db, admin, "admin.user_delete", f"Usunięto konto {username} (#{user_id}) wraz z jego zestawami.")
    db.commit()
    return MessageOut(ok=True, message=f"Konto „{username}” zostało usunięte.")


# --------------------------------------------------------------------------- #
# Moderacja zestawów
# --------------------------------------------------------------------------- #
@router.get("/sets", response_model=list[StudySetSummary])
def list_sets(
    admin: AdminUser,
    db: DbSession,
    q: str = Query(default="", max_length=120),
    only_public: bool = False,
    only_hidden: bool = False,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[StudySetSummary]:
    stmt = set_query_with_relations()
    if q.strip():
        needle = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(func.lower(StudySet.title).like(needle), func.lower(StudySet.subject).like(needle))
        )
    if only_public:
        stmt = stmt.where(StudySet.visibility == Visibility.PUBLIC)
    if only_hidden:
        stmt = stmt.where(StudySet.is_published.is_(False))

    rows = list(db.scalars(stmt.order_by(StudySet.updated_at.desc()).limit(limit)).unique())
    counts = counts_for_sets(db, [row.id for row in rows])
    return [to_summary(row, counts=counts.get(row.id), viewer=admin) for row in rows]


@router.patch("/sets/{set_id}", response_model=StudySetSummary)
def moderate_set(set_id: int, payload: AdminSetModeration, admin: AdminUser, db: DbSession) -> StudySetSummary:
    study_set = db.scalar(set_query_with_relations().where(StudySet.id == set_id))
    if study_set is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nie znaleziono zestawu.")

    if payload.is_published is not None:
        study_set.is_published = payload.is_published
    if payload.visibility is not None:
        study_set.visibility = payload.visibility
    if payload.moderation_note is not None:
        study_set.moderation_note = payload.moderation_note.strip() or None

    action = "admin.set_publish" if study_set.is_published else "admin.set_unpublish"
    log_action(db, admin, action, f"Moderacja zestawu #{set_id} „{study_set.title}”.")
    db.commit()

    study_set = db.scalar(set_query_with_relations().where(StudySet.id == set_id))
    assert study_set is not None
    counts = counts_for_sets(db, [set_id])
    return to_summary(study_set, counts=counts.get(set_id), viewer=admin)


@router.delete("/sets/{set_id}", response_model=MessageOut)
def delete_set(set_id: int, admin: AdminUser, db: DbSession) -> MessageOut:
    study_set = db.get(StudySet, set_id)
    if study_set is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nie znaleziono zestawu.")
    title = study_set.title
    db.delete(study_set)
    log_action(db, admin, "admin.set_delete", f"Usunięto zestaw #{set_id} „{title}”.")
    db.commit()
    return MessageOut(ok=True, message=f"Zestaw „{title}” został usunięty.")


# --------------------------------------------------------------------------- #
# Kopie zapasowe
# --------------------------------------------------------------------------- #
@router.post("/backup", response_class=FileResponse)
def download_backup(admin: AdminUser, db: DbSession) -> FileResponse:
    """Generuje i zwraca archiwum ZIP z pełną kopią bazy danych."""
    log_action(db, admin, "admin.backup", "Pobrano kopię zapasową bazy danych.")
    db.commit()

    try:
        archive_path, _manifest = create_backup_archive()
    except Exception as exc:  # pragma: no cover - błąd systemu plików
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Nie udało się utworzyć kopii zapasowej: {exc}",
        ) from exc

    return FileResponse(
        path=archive_path,
        media_type="application/zip",
        filename=archive_path.name,
        headers={"Cache-Control": "no-store"},
    )


@router.post("/restore", response_model=MessageOut)
async def restore_backup(
    admin: AdminUser,
    confirm: str = Query(default="", description="Musi mieć wartość 'PRZYWROC', aby potwierdzić operację."),
    file: UploadFile = File(...),
) -> MessageOut:
    """Przywraca bazę danych z archiwum ZIP lub pliku `.db`.

    Operacja jest nieodwracalna, dlatego wymaga jawnego potwierdzenia oraz
    automatycznie zapisuje kopię bezpieczeństwa stanu sprzed przywrócenia.
    """
    if confirm.strip().upper() != "PRZYWROC":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Operacja niepotwierdzona. Wpisz PRZYWROC, aby nadpisać bieżącą bazę danych.",
        )

    raw = await file.read()
    try:
        summary = restore_from_bytes(raw)
    except BackupError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    users = summary["tables"].get("users", 0)
    sets_total = summary["tables"].get("study_sets", 0)
    safety = summary.get("safety_copy")
    suffix = f" Kopia bezpieczeństwa: {safety}." if safety else ""

    return MessageOut(
        ok=True,
        message=(
            f"Baza została przywrócona: {users} kont, {sets_total} zestawów."
            f"{suffix} Zaloguj się ponownie, aby odświeżyć sesję."
        ),
    )


@router.get("/audit", response_model=list[AuditLogOut])
def audit_log(
    admin: AdminUser,
    db: DbSession,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[AuditLogOut]:
    rows = db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit))
    return [AuditLogOut.model_validate(row) for row in rows]
