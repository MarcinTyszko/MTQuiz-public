"""Endpointy sesji nauki i statystyk pulpitu."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from ..deps import DbSession, UnlockedUser
from ..models import StudySession, StudySet
from ..schemas import DashboardStats, StudySessionIn, StudySessionOut
from ..services import can_view, dashboard_stats

router = APIRouter(prefix="/api/study", tags=["study"])


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

    return StudySessionOut(
        id=session.id,
        set_id=session.set_id,
        set_title=study_set.title,
        mode=session.mode,
        score=session.score,
        total=session.total,
        duration_seconds=session.duration_seconds,
        accuracy=session.accuracy,
        created_at=session.created_at,
    )


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

    return [
        StudySessionOut(
            id=row.id,
            set_id=row.set_id,
            set_title=titles.get(row.set_id, "—"),
            mode=row.mode,
            score=row.score,
            total=row.total,
            duration_seconds=row.duration_seconds,
            accuracy=row.accuracy,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.get("/stats", response_model=DashboardStats)
def stats(user: UnlockedUser, db: DbSession) -> DashboardStats:
    return dashboard_stats(db, user)
