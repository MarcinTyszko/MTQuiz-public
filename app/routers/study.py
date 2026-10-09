"""Endpointy sesji nauki i statystyk pulpitu."""
from __future__ import annotations

from datetime import timedelta, timezone

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from ..deps import DbSession, UnlockedUser
from ..models import Flashcard, Question, StudyMode, StudySession, StudySet, utcnow
from ..schemas import DashboardStats, StudySessionIn, StudySessionOut, StudySessionProgress
from ..services import can_view, dashboard_stats

router = APIRouter(prefix="/api/study", tags=["study"])

# Jak długo po rozpoczęciu sesję można jeszcze aktualizować. Dłuższa nauka
# i tak zaczyna nową sesję; limit chroni stare wpisy przed dopisywaniem punktów.
SESSION_EDIT_WINDOW = timedelta(hours=24)


def _session_out(session: StudySession, title: str) -> StudySessionOut:
    return StudySessionOut(
        id=session.id,
        set_id=session.set_id,
        set_title=title,
        mode=session.mode,
        score=session.score,
        total=session.total,
        duration_seconds=session.duration_seconds,
        accuracy=session.accuracy,
        created_at=session.created_at,
    )


def _items_in_set(db, set_id: int, mode: StudyMode) -> int:
    """Ile różnych elementów da się przerobić w sesji danego trybu."""
    model = Flashcard if mode == StudyMode.FLASHCARDS else Question
    return db.scalar(select(func.count(model.id)).where(model.set_id == set_id)) or 0


@router.post("/sessions", response_model=StudySessionOut, status_code=status.HTTP_201_CREATED)
def record_session(payload: StudySessionIn, user: UnlockedUser, db: DbSession) -> StudySessionOut:
    study_set = db.get(StudySet, payload.set_id)
    if study_set is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nie znaleziono zestawu.")
    if not can_view(study_set, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Ten zestaw jest prywatny.")

    session = StudySession(
        user_id=user.id,
        set_id=payload.set_id,
        mode=payload.mode,
        score=payload.score,
        total=payload.total,
        duration_seconds=payload.duration_seconds,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return _session_out(session, study_set.title)


@router.patch("/sessions/{session_id}", response_model=StudySessionOut)
def update_session_progress(
    session_id: int, payload: StudySessionProgress, user: UnlockedUser, db: DbSession
) -> StudySessionOut:
    """Aktualizuje postęp trwającej sesji po każdym przerobionym elemencie.

    Dzięki temu punkty, kalendarz aktywności i seria rosną z każdą fiszką
    i każdym pytaniem — także wtedy, gdy nauka zostanie przerwana w połowie.
    """
    session = db.get(StudySession, session_id)
    if session is None or session.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nie znaleziono sesji nauki.")

    started = session.created_at if session.created_at.tzinfo else session.created_at.replace(tzinfo=timezone.utc)
    if utcnow() - started > SESSION_EDIT_WINDOW:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ta sesja nauki jest już zamknięta.")

    # W jednej sesji każdy element liczy się raz — więcej, niż ma zestaw, się nie da.
    limit = _items_in_set(db, session.set_id, session.mode)
    if payload.total > limit:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Sesja nie może obejmować więcej elementów niż zestaw ({limit}).",
        )

    # Liczba przerobionych elementów w sesji tylko rośnie: spóźnione starsze żądanie
    # (np. wysłane tuż przed zamknięciem karty) nie odbierze już zdobytych punktów.
    session.total = max(session.total, payload.total)
    session.score = min(payload.score, session.total)
    session.duration_seconds = max(session.duration_seconds, payload.duration_seconds)
    db.commit()
    db.refresh(session)

    title = db.scalar(select(StudySet.title).where(StudySet.id == session.set_id)) or "—"
    return _session_out(session, title)


@router.get("/sessions", response_model=list[StudySessionOut])
def recent_sessions(
    user: UnlockedUser,
    db: DbSession,
    limit: int = Query(default=20, ge=1, le=200),
    set_id: int | None = None,
) -> list[StudySessionOut]:
    stmt = select(StudySession).where(StudySession.user_id == user.id)
    if set_id is not None:
        stmt = stmt.where(StudySession.set_id == set_id)
    rows = list(db.scalars(stmt.order_by(StudySession.created_at.desc()).limit(limit)))

    titles = {}
    if rows:
        set_ids = {row.set_id for row in rows}
        titles = {
            sid: title
            for sid, title in db.execute(select(StudySet.id, StudySet.title).where(StudySet.id.in_(set_ids)))
        }

    return [_session_out(row, titles.get(row.set_id, "—")) for row in rows]


@router.get("/stats", response_model=DashboardStats)
def stats(user: UnlockedUser, db: DbSession) -> DashboardStats:
    return dashboard_stats(db, user)
