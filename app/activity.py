"""Aktywność nauki: kalendarz w stylu GitHuba i serie dni nauki.

Jednostką aktywności jest liczba przerobionych elementów — fiszek w sesji
fiszek i pytań w sesji quizu (pole ``StudySession.total``).

Agregacja przebiega dwuetapowo. Baza grupuje sesje w godzinowe kubełki UTC
(zapytanie obsługiwane w całości z indeksu ``user_id, created_at, total``),
a Python przypisuje każdy kubełek do lokalnego dnia kalendarzowego. Dzięki
temu granice dni zgadzają się ze strefą użytkownika także w dniach zmiany
czasu, a do aplikacji trafia najwyżej kilka tysięcy wierszy rocznie.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone, tzinfo
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import settings
from .models import StudySession, User

logger = logging.getLogger("mtquiz")

MONTHS_SHORT = ("sty", "lut", "mar", "kwi", "maj", "cze", "lip", "sie", "wrz", "paź", "lis", "gru")
MONTHS_GENITIVE = (
    "stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca",
    "lipca", "sierpnia", "września", "października", "listopada", "grudnia",
)
WEEKDAYS_SHORT = ("pon", "wt", "śr", "czw", "pt", "sob", "nd")

MIN_WEEKS = 4
MAX_WEEKS = 53


@lru_cache(maxsize=8)
def _zone(name: str) -> tzinfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        logger.warning("Nieznana strefa czasowa „%s” — kalendarz aktywności liczony w UTC.", name)
        return timezone.utc


def local_zone() -> tzinfo:
    """Strefa wyznaczająca granice dni i tygodni (``QUIZAPP_TIMEZONE`` / ``TZ``)."""
    return _zone(settings.timezone)


def local_today(now: datetime | None = None) -> date:
    return (now or datetime.now(timezone.utc)).astimezone(local_zone()).date()


def local_midnight_utc(day: date) -> datetime:
    """Początek lokalnego dnia wyrażony w UTC — do porównań z ``created_at``."""
    return datetime.combine(day, datetime.min.time(), tzinfo=local_zone()).astimezone(timezone.utc)


def format_day(day: date) -> str:
    return f"{day.day} {MONTHS_GENITIVE[day.month - 1]} {day.year}"


def format_range(start: date, end: date) -> str:
    """Zakres dat po polsku, np. „6–12 października” albo „29 września – 5 października”."""
    if start.month == end.month and start.year == end.year:
        return f"{start.day}–{end.day} {MONTHS_GENITIVE[end.month - 1]}"
    return f"{start.day} {MONTHS_GENITIVE[start.month - 1]} – {end.day} {MONTHS_GENITIVE[end.month - 1]}"


def daily_totals(db: Session, user_id: int, start: date, end: date) -> dict[date, tuple[int, int]]:
    """Zwraca ``{dzień lokalny: (elementy, sesje)}`` dla dni z zakresu [start, end]."""
    since = local_midnight_utc(start)
    until = local_midnight_utc(end + timedelta(days=1))
    hour = func.strftime("%Y-%m-%d %H", StudySession.created_at).label("hour")
    rows = db.execute(
        select(hour, func.sum(StudySession.total), func.count(StudySession.id))
        .where(
            StudySession.user_id == user_id,
            StudySession.created_at >= since,
            StudySession.created_at < until,
        )
        .group_by(hour)
    )

    zone = local_zone()
    totals: dict[date, tuple[int, int]] = {}
    for bucket, items, sessions in rows:
        if not bucket:
            continue
        moment = datetime.strptime(bucket, "%Y-%m-%d %H").replace(tzinfo=timezone.utc)
        day = moment.astimezone(zone).date()
        previous_items, previous_sessions = totals.get(day, (0, 0))
        totals[day] = (previous_items + int(items or 0), previous_sessions + int(sessions or 0))
    return totals


def intensity_thresholds(values: list[int]) -> tuple[int, int, int]:
    """Progi poziomów 2–4 jako kwartyle dni aktywnych (jak w kalendarzu GitHuba).

    Kwartyle zamiast ułamka maksimum: jeden rekordowy dzień nie spłaszcza
    całej reszty kalendarza do najjaśniejszego odcienia.
    """
    positive = sorted(value for value in values if value > 0)
    if not positive:
        return (1, 1, 1)

    def quantile(fraction: float) -> int:
        # Indeks liczony od (n - 1): maksimum zawsze przekracza trzeci kwartyl,
        # więc rekordowy dzień dostaje najciemniejszy odcień.
        return positive[int(fraction * (len(positive) - 1))]

    return (quantile(0.25), quantile(0.5), quantile(0.75))


def intensity_level(items: int, sessions: int, thresholds: tuple[int, int, int]) -> int:
    if items <= 0:
        # Sesja bez elementów (np. przerwana na starcie) to wciąż ślad nauki.
        return 1 if sessions else 0
    q1, q2, q3 = thresholds
    if items > q3:
        return 4
    if items > q2:
        return 3
    if items > q1:
        return 2
    return 1


@dataclass
class HeatmapDay:
    day: date
    items: int = 0
    sessions: int = 0
    level: int = 0
    is_future: bool = False

    @property
    def date_label(self) -> str:
        return format_day(self.day)


@dataclass
class Heatmap:
    start: date
    end: date
    weeks: list[list[HeatmapDay]]
    month_labels: list[str]
    total_items: int = 0
    total_sessions: int = 0
    active_days: int = 0
    best_day: HeatmapDay | None = None
    current_streak: int = 0
    longest_streak: int = 0
    studied_today: bool = False
    weekdays: tuple[str, ...] = field(default=WEEKDAYS_SHORT)

    @property
    def days(self) -> list[HeatmapDay]:
        return [day for week in self.weeks for day in week if not day.is_future]


def _streaks(active: set[date], today: date, start: date) -> tuple[int, int]:
    """Bieżąca i najdłuższa seria kolejnych dni nauki w oknie kalendarza.

    Seria bieżąca nie przepada o północy: dzień dzisiejszy bez nauki jeszcze
    jej nie zrywa, jeżeli wczoraj była aktywność.
    """
    current = 0
    cursor = today if today in active else today - timedelta(days=1)
    while cursor in active and cursor >= start:
        current += 1
        cursor -= timedelta(days=1)

    longest = run = 0
    cursor = start
    while cursor <= today:
        run = run + 1 if cursor in active else 0
        longest = max(longest, run)
        cursor += timedelta(days=1)
    return current, longest


def build_heatmap(db: Session, user: User, weeks: int = MAX_WEEKS, *, now: datetime | None = None) -> Heatmap:
    """Kalendarz ostatnich ``weeks`` tygodni; kolumny to tygodnie od poniedziałku."""
    weeks = max(MIN_WEEKS, min(MAX_WEEKS, weeks))
    today = local_today(now)
    start = today - timedelta(days=today.weekday()) - timedelta(weeks=weeks - 1)

    totals = daily_totals(db, user.id, start, today)
    thresholds = intensity_thresholds([items for items, _ in totals.values()])

    grid: list[list[HeatmapDay]] = []
    month_labels: list[str] = []
    previous_month = None
    for week_index in range(weeks):
        monday = start + timedelta(weeks=week_index)
        column: list[HeatmapDay] = []
        for offset in range(7):
            day = monday + timedelta(days=offset)
            items, sessions = totals.get(day, (0, 0))
            column.append(
                HeatmapDay(
                    day=day,
                    items=items,
                    sessions=sessions,
                    level=intensity_level(items, sessions, thresholds),
                    is_future=day > today,
                )
            )
        grid.append(column)
        # Podpis miesiąca nad pierwszym tygodniem, który w nim się zaczyna. Pierwsza
        # kolumna dostaje podpis tylko wtedy, gdy miesiąc zajmie jeszcze kilka kolumn —
        # inaczej dwa podpisy nachodziłyby na siebie.
        label = ""
        if monday.month != previous_month:
            if week_index > 0 or monday.day <= 14:
                label = MONTHS_SHORT[monday.month - 1]
            previous_month = monday.month
        month_labels.append(label)

    active = {day for day, (_, sessions) in totals.items() if sessions}
    current, longest = _streaks(active, today, start)
    visible = [day for column in grid for day in column if not day.is_future]
    best = max((day for day in visible if day.items), key=lambda day: day.items, default=None)

    return Heatmap(
        start=start,
        end=today,
        weeks=grid,
        month_labels=month_labels,
        total_items=sum(day.items for day in visible),
        total_sessions=sum(day.sessions for day in visible),
        active_days=len(active),
        best_day=best,
        current_streak=current,
        longest_streak=longest,
        studied_today=today in active,
    )
