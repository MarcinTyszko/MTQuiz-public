"""Kalendarz aktywności i rankingi nauki."""
from __future__ import annotations

from fastapi import APIRouter, Query

from ..activity import MAX_WEEKS, MIN_WEEKS, build_heatmap
from ..config import settings
from ..deps import DbSession, UnlockedUser
from ..leaderboard import DEFAULT_LIMIT, Leaderboard, LeaderboardEntry, Period, build_leaderboard
from ..schemas import HeatmapDayOut, HeatmapOut, LeaderboardEntryOut, LeaderboardOut

router = APIRouter(prefix="/api/activity", tags=["activity"])


@router.get("/heatmap", response_model=HeatmapOut)
def heatmap(
    user: UnlockedUser,
    db: DbSession,
    weeks: int = Query(default=MAX_WEEKS, ge=MIN_WEEKS, le=MAX_WEEKS),
) -> HeatmapOut:
    """Dzienna liczba przerobionych elementów zalogowanego konta."""
    data = build_heatmap(db, user, weeks)
    return HeatmapOut(
        start=data.start,
        end=data.end,
        timezone=settings.timezone,
        total_items=data.total_items,
        total_sessions=data.total_sessions,
        active_days=data.active_days,
        current_streak=data.current_streak,
        longest_streak=data.longest_streak,
        studied_today=data.studied_today,
        days=[
            HeatmapDayOut(date=day.day, items=day.items, sessions=day.sessions, level=day.level)
            for day in data.days
        ],
    )


def _entry_out(entry: LeaderboardEntry) -> LeaderboardEntryOut:
    return LeaderboardEntryOut(
        rank=entry.rank,
        user_id=entry.user_id,
        username=entry.username,
        label=entry.label,
        points=entry.points,
        quiz_items=entry.quiz_items,
        card_items=entry.card_items,
        sessions=entry.sessions,
        quiz_accuracy=entry.quiz_accuracy,
        is_viewer=entry.is_viewer,
    )


def leaderboard_out(board: Leaderboard) -> LeaderboardOut:
    return LeaderboardOut(
        period=board.period.value,
        participants=board.participants,
        total_points=board.total_points,
        week_start=board.week.start if board.week else None,
        week_end=board.week.end if board.week else None,
        resets_at=board.week.resets_at if board.week else None,
        entries=[_entry_out(entry) for entry in board.entries],
        viewer=_entry_out(board.viewer) if board.viewer else None,
    )


@router.get("/leaderboard", response_model=LeaderboardOut)
def leaderboard(
    user: UnlockedUser,
    db: DbSession,
    period: Period = Period.WEEK,
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=200),
) -> LeaderboardOut:
    """Ranking tygodniowy (od poniedziałku) albo ogólny wraz z pozycją pytającego."""
    return leaderboard_out(build_leaderboard(db, period, user, limit=limit))
