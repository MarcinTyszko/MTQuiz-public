"""Rankingi nauki: ogólny (od początku) i tygodniowy.

Punkt = jeden przerobiony element: rozwiązane pytanie quizu albo powtórzona
fiszka (``StudySession.total``). Tydzień rankingowy trwa od poniedziałku
00:00 do niedzieli 23:59 w strefie aplikacji, więc rywalizacja zeruje się co
tydzień o tej samej porze dla wszystkich.

Ranking liczy jedno zapytanie agregujące po ``user_id``; miejsca (z remisami
w stylu „1, 2, 2, 4”) nadaje Python, bo uczestników jest najwyżej tylu, ile
kont na instancji.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from .activity import format_range, local_midnight_utc, local_today
from .models import StudyMode, StudySession, User

DEFAULT_LIMIT = 50


class Period(str, enum.Enum):
    WEEK = "week"
    ALL = "all"


PERIOD_LABELS = {Period.WEEK: "Ten tydzień", Period.ALL: "Od początku"}


@dataclass(frozen=True)
class WeekWindow:
    start: date
    end: date
    starts_at: datetime
    resets_at: datetime

    @property
    def label(self) -> str:
        return format_range(self.start, self.end)

    def days_left(self, now: datetime | None = None) -> int:
        """Pełne dni do resetu, licząc dzisiejszy (w niedzielę: 1)."""
        today = local_today(now)
        return (self.end - today).days + 1


def current_week(now: datetime | None = None) -> WeekWindow:
    today = local_today(now)
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return WeekWindow(
        start=monday,
        end=sunday,
        starts_at=local_midnight_utc(monday),
        resets_at=local_midnight_utc(sunday + timedelta(days=1)),
    )


@dataclass
class LeaderboardEntry:
    rank: int
    user_id: int
    username: str
    label: str
    points: int
    quiz_items: int
    card_items: int
    sessions: int
    quiz_accuracy: float | None
    is_viewer: bool = False

    @property
    def initial(self) -> str:
        return (self.label[:1] or "?").upper()


@dataclass
class Leaderboard:
    period: Period
    entries: list[LeaderboardEntry]
    viewer: LeaderboardEntry | None
    participants: int
    total_points: int
    week: WeekWindow | None = None

    @property
    def podium(self) -> list[LeaderboardEntry]:
        return [entry for entry in self.entries if entry.rank <= 3][:3]

    @property
    def viewer_outside_list(self) -> bool:
        return self.viewer is not None and all(not entry.is_viewer for entry in self.entries)

    @property
    def label(self) -> str:
        return PERIOD_LABELS[self.period]


def build_leaderboard(
    db: Session,
    period: Period,
    viewer: User | None = None,
    *,
    limit: int = DEFAULT_LIMIT,
    now: datetime | None = None,
) -> Leaderboard:
    is_quiz = StudySession.mode == StudyMode.QUIZ
    # Najpierw agregacja samych sesji (odczyt z indeksu pokrywającego
    # ``ix_study_sessions_activity``), dopiero potem złączenie z kontami.
    totals = (
        select(
            StudySession.user_id.label("user_id"),
            func.sum(StudySession.total).label("points"),
            func.sum(case((is_quiz, StudySession.total), else_=0)).label("quiz_items"),
            func.sum(case((is_quiz, StudySession.score), else_=0)).label("quiz_score"),
            func.count().label("sessions"),
        )
        .group_by(StudySession.user_id)
        .having(func.sum(StudySession.total) > 0)
    )

    week = None
    if period == Period.WEEK:
        week = current_week(now)
        totals = totals.where(StudySession.created_at >= week.starts_at, StudySession.created_at < week.resets_at)

    per_user = totals.subquery()
    stmt = (
        select(per_user, User.username, User.display_name)
        .join(User, User.id == per_user.c.user_id)
        .where(User.is_active.is_(True))
    )
    rows = list(db.execute(stmt))
    # Kolejność: punkty, potem skuteczność quizów, na końcu nazwa — wynik deterministyczny.
    rows.sort(
        key=lambda row: (
            -int(row.points or 0),
            -((row.quiz_score or 0) / row.quiz_items if row.quiz_items else 0),
            (row.display_name or row.username).casefold(),
        )
    )

    ranked: list[LeaderboardEntry] = []
    previous_points: int | None = None
    rank = 0
    for position, row in enumerate(rows, start=1):
        row_points = int(row.points or 0)
        # Remis punktowy oznacza to samo miejsce; kolejne miejsce przeskakuje (1, 2, 2, 4).
        if row_points != previous_points:
            rank = position
            previous_points = row_points
        quiz_total = int(row.quiz_items or 0)
        ranked.append(
            LeaderboardEntry(
                rank=rank,
                user_id=row.user_id,
                username=row.username,
                label=row.display_name or row.username,
                points=row_points,
                quiz_items=quiz_total,
                card_items=row_points - quiz_total,
                sessions=int(row.sessions or 0),
                quiz_accuracy=round(100 * (row.quiz_score or 0) / quiz_total, 1) if quiz_total else None,
                is_viewer=viewer is not None and row.user_id == viewer.id,
            )
        )

    viewer_entry = next((entry for entry in ranked if entry.is_viewer), None)
    return Leaderboard(
        period=period,
        entries=ranked[: max(1, limit)],
        viewer=viewer_entry,
        participants=len(ranked),
        total_points=sum(entry.points for entry in ranked),
        week=week,
    )
