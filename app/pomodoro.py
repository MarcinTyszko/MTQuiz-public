"""Pomodoro: statystyki skupienia, poziomy i odznaki.

Minutnik liczy przeglądarka (działa także bez sieci i przeżywa przejścia między
stronami), a serwer dostaje gotowe wpisy o zakończonych fazach. Tutaj powstają
z nich statystyki dnia, tygodnia, miesiąca i roku z porównaniem do okresu
poprzedniego oraz warstwa grywalizacji: poziom, seria dni i odznaki.

Granice dni liczone są w strefie instancji (``QUIZAPP_TIMEZONE``), tak samo
jak w kalendarzu aktywności nauki.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from enum import Enum

from sqlalchemy import select
from sqlalchemy.orm import Session

from .activity import MONTHS_SHORT, WEEKDAYS_SHORT, format_day, format_range, local_today, local_zone
from .models import PomodoroEntry, User, utcnow

FOCUS = "focus"
KINDS = (FOCUS, "short_break", "long_break")

MONTHS_NOMINATIVE = (
    "styczeń", "luty", "marzec", "kwiecień", "maj", "czerwiec",
    "lipiec", "sierpień", "wrzesień", "październik", "listopad", "grudzień",
)


class StatsPeriod(str, Enum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _local_start(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=local_zone())


def _add_months(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


@dataclass
class PeriodRange:
    period: StatsPeriod
    start: date
    end: date  # wyłącznie
    label: str
    bucket_labels: list[str]
    is_current: bool

    def bucket_of(self, moment: datetime) -> int:
        local = moment.astimezone(local_zone())
        if self.period == StatsPeriod.DAY:
            return local.hour
        if self.period == StatsPeriod.YEAR:
            return local.month - 1
        return (local.date() - self.start).days


def period_range(period: StatsPeriod, offset: int = 0, today: date | None = None) -> PeriodRange:
    """Okres statystyk przesunięty o ``offset`` (0 — bieżący, -1 — poprzedni…)."""
    today = today or local_today()
    if period == StatsPeriod.DAY:
        start = today + timedelta(days=offset)
        end = start + timedelta(days=1)
        if offset == 0:
            label = "Dziś"
        elif offset == -1:
            label = "Wczoraj"
        else:
            label = format_day(start)
        buckets = [f"{hour}" for hour in range(24)]
    elif period == StatsPeriod.WEEK:
        start = today - timedelta(days=today.weekday()) + timedelta(weeks=offset)
        end = start + timedelta(days=7)
        label = format_range(start, end - timedelta(days=1))
        buckets = list(WEEKDAYS_SHORT)
    elif period == StatsPeriod.MONTH:
        start = _add_months(today.replace(day=1), offset)
        end = _add_months(start, 1)
        label = f"{MONTHS_NOMINATIVE[start.month - 1]} {start.year}"
        buckets = [str(day) for day in range(1, (end - start).days + 1)]
    else:
        start = date(today.year + offset, 1, 1)
        end = date(start.year + 1, 1, 1)
        label = str(start.year)
        buckets = list(MONTHS_SHORT)
    return PeriodRange(period, start, end, label, buckets, start <= today < end)


def _entries(db: Session, user: User, since: datetime | None = None, until: datetime | None = None) -> list[PomodoroEntry]:
    stmt = select(PomodoroEntry).where(PomodoroEntry.user_id == user.id)
    if since is not None:
        stmt = stmt.where(PomodoroEntry.ended_at >= since.astimezone(timezone.utc))
    if until is not None:
        stmt = stmt.where(PomodoroEntry.ended_at < until.astimezone(timezone.utc))
    return list(db.scalars(stmt.order_by(PomodoroEntry.ended_at)))


def _totals(entries: list[PomodoroEntry]) -> dict:
    focus = [entry for entry in entries if entry.kind == FOCUS]
    completed = [entry for entry in focus if entry.completed]
    return {
        "focus_seconds": sum(entry.actual_seconds for entry in focus),
        "pomodoros": len(completed),
        "sessions": len(focus),
        "break_seconds": sum(entry.actual_seconds for entry in entries if entry.kind != FOCUS),
        "completion_rate": round(100 * len(completed) / len(focus)) if focus else None,
    }


def _delta(current: float, previous: float) -> int | None:
    """Zmiana procentowa; brak wartości, gdy w okresie poprzednim nie było czego porównać."""
    if not previous:
        return None
    return round(100 * (current - previous) / previous)


def build_stats(db: Session, user: User, period: StatsPeriod, offset: int = 0, *, now: datetime | None = None) -> dict:
    """Statystyki okresu z wykresem i porównaniem do okresu poprzedniego.

    Bieżący okres porównujemy z poprzednim do tego samego momentu (wtorek
    z wtorkiem), a zakończony — w całości z całym poprzednim.
    """
    now = _aware(now or utcnow())
    today = local_today(now)
    current = period_range(period, offset, today)
    previous = period_range(period, offset - 1, today)

    start_at, end_at = _local_start(current.start), _local_start(current.end)
    prev_start_at, prev_end_at = _local_start(previous.start), _local_start(previous.end)
    if current.is_current:
        elapsed = now - start_at
        prev_end_at = min(prev_end_at, prev_start_at + elapsed)
        compare_note = {
            StatsPeriod.DAY: "względem wczoraj o tej porze",
            StatsPeriod.WEEK: "względem tego samego dnia poprzedniego tygodnia",
            StatsPeriod.MONTH: "względem tego samego dnia poprzedniego miesiąca",
            StatsPeriod.YEAR: "względem tego samego dnia poprzedniego roku",
        }[period]
    else:
        compare_note = {
            StatsPeriod.DAY: "względem dnia poprzedniego",
            StatsPeriod.WEEK: "względem tygodnia poprzedniego",
            StatsPeriod.MONTH: "względem miesiąca poprzedniego",
            StatsPeriod.YEAR: "względem roku poprzedniego",
        }[period]

    entries = _entries(db, user, start_at, end_at)
    prev_entries = _entries(db, user, prev_start_at, prev_end_at)
    totals = _totals(entries)
    prev_totals = _totals(prev_entries)

    buckets = [{"label": label, "focus_seconds": 0, "pomodoros": 0} for label in current.bucket_labels]
    labels: dict[str, int] = {}
    active_days: set[date] = set()
    hours = [0] * 24
    for entry in entries:
        if entry.kind != FOCUS:
            continue
        ended = _aware(entry.ended_at)
        index = current.bucket_of(ended)
        if 0 <= index < len(buckets):
            buckets[index]["focus_seconds"] += entry.actual_seconds
            buckets[index]["pomodoros"] += int(entry.completed)
        active_days.add(ended.astimezone(local_zone()).date())
        hours[_aware(entry.started_at).astimezone(local_zone()).hour] += entry.actual_seconds
        if entry.label:
            labels[entry.label] = labels.get(entry.label, 0) + entry.actual_seconds

    if current.is_current:
        if period == StatsPeriod.DAY:
            current_bucket = now.astimezone(local_zone()).hour
        else:
            current_bucket = current.bucket_of(now)
    else:
        current_bucket = None

    best = max(range(len(buckets)), key=lambda i: buckets[i]["focus_seconds"], default=None)
    if best is not None and not buckets[best]["focus_seconds"]:
        best = None
    peak_hour = max(range(24), key=lambda h: hours[h]) if any(hours) else None

    return {
        "period": period.value,
        "offset": offset,
        "label": current.label,
        "is_current": current.is_current,
        "compare_note": compare_note,
        "totals": totals,
        "previous": prev_totals,
        "deltas": {
            "focus_seconds": _delta(totals["focus_seconds"], prev_totals["focus_seconds"]),
            "pomodoros": _delta(totals["pomodoros"], prev_totals["pomodoros"]),
        },
        "active_days": len(active_days),
        "average_per_active_day": round(totals["focus_seconds"] / len(active_days)) if active_days else 0,
        "buckets": buckets,
        "current_bucket": current_bucket,
        "best_bucket": best,
        "peak_hour": peak_hour,
        "top_labels": [
            {"label": label, "focus_seconds": seconds}
            for label, seconds in sorted(labels.items(), key=lambda item: item[1], reverse=True)[:5]
        ],
    }


# --------------------------------------------------------------------------- #
# Grywalizacja                                                                 #
# --------------------------------------------------------------------------- #

# (minuty skupienia potrzebne do poziomu, nazwa) — pierwszy poziom od zera.
LEVELS: tuple[tuple[int, str], ...] = (
    (0, "Nasionko"),
    (60, "Kiełek"),
    (180, "Sadzonka"),
    (360, "Krzaczek"),
    (600, "Kwitnący krzak"),
    (1200, "Zielony pomidor"),
    (2100, "Dojrzały pomidor"),
    (3600, "Ogrodnik skupienia"),
    (6000, "Mistrz Pomodoro"),
    (12000, "Legenda Pomodoro"),
)


def level_for(minutes: int) -> dict:
    index = max(i for i, (threshold, _) in enumerate(LEVELS) if minutes >= threshold)
    threshold, name = LEVELS[index]
    if index + 1 < len(LEVELS):
        next_threshold, next_name = LEVELS[index + 1]
        progress = round(100 * (minutes - threshold) / (next_threshold - threshold))
    else:
        next_threshold, next_name, progress = None, None, 100
    return {
        "number": index + 1,
        "name": name,
        "minutes": minutes,
        "next_name": next_name,
        "next_minutes": next_threshold,
        "progress": progress,
    }


def _streaks(days: set[date], today: date) -> tuple[int, int]:
    current = 0
    cursor = today if today in days else today - timedelta(days=1)
    while cursor in days:
        current += 1
        cursor -= timedelta(days=1)
    longest = run = 0
    previous = None
    for day in sorted(days):
        run = run + 1 if previous is not None and day - previous == timedelta(days=1) else 1
        longest = max(longest, run)
        previous = day
    return current, longest


def build_summary(db: Session, user: User, daily_goal: int, *, now: datetime | None = None) -> dict:
    """Dzisiejszy postęp, seria dni, poziom, rekordy i odznaki."""
    now = _aware(now or utcnow())
    today = local_today(now)
    zone = local_zone()

    per_day: dict[date, dict] = {}
    total_seconds = total_completed = longest_focus = 0
    early = late = False
    for entry in _entries(db, user):
        if entry.kind != FOCUS:
            continue
        ended = _aware(entry.ended_at).astimezone(zone)
        day = per_day.setdefault(ended.date(), {"seconds": 0, "completed": 0})
        day["seconds"] += entry.actual_seconds
        total_seconds += entry.actual_seconds
        if entry.completed:
            day["completed"] += 1
            total_completed += 1
            longest_focus = max(longest_focus, entry.actual_seconds)
            started = _aware(entry.started_at).astimezone(zone)
            early = early or started.hour < 7
            late = late or ended.hour >= 22

    productive = {day for day, values in per_day.items() if values["completed"]}
    current_streak, longest_streak = _streaks(productive, today)
    best_day = max(per_day.items(), key=lambda item: item[1]["seconds"], default=None)
    best_count = max((values["completed"] for values in per_day.values()), default=0)
    goal_days = sum(1 for values in per_day.values() if values["completed"] >= daily_goal)
    today_values = per_day.get(today, {"seconds": 0, "completed": 0})
    total_minutes = total_seconds // 60

    def badge(key: str, name: str, description: str, value: int, target: int) -> dict:
        return {
            "key": key,
            "name": name,
            "description": description,
            "unlocked": value >= target,
            "value": min(value, target),
            "target": target,
        }

    achievements = [
        badge("pierwszy", "Pierwszy pomidor", "Ukończ pierwszy blok skupienia.", total_completed, 1),
        badge("rozgrzewka", "Rozgrzewka", "4 pomidory jednego dnia.", best_count, 4),
        badge("maraton", "Maraton", "8 pomidorów jednego dnia.", best_count, 8),
        badge("cel", "Cel dnia", "Osiągnij dzienny cel.", goal_days, 1),
        badge("cel-10", "Dziesięć celów", "Dzienny cel osiągnięty w 10 dniach.", goal_days, 10),
        badge("seria-3", "Rytm", "3 dni z rzędu z ukończonym pomidorem.", longest_streak, 3),
        badge("seria-7", "Tydzień w rytmie", "7 dni z rzędu.", longest_streak, 7),
        badge("seria-30", "Miesiąc dyscypliny", "30 dni z rzędu.", longest_streak, 30),
        badge("glebia", "Głęboka praca", "Ukończ blok skupienia trwający co najmniej 50 minut.", longest_focus // 60, 50),
        badge("ranny", "Ranny ptaszek", "Ukończ pomidor rozpoczęty przed 7:00.", int(early), 1),
        badge("nocny", "Nocna zmiana", "Ukończ pomidor po 22:00.", int(late), 1),
        badge("10h", "10 godzin", "10 godzin skupienia łącznie.", total_minutes, 600),
        badge("setka", "Setka", "100 ukończonych pomidorów.", total_completed, 100),
        badge("100h", "100 godzin", "100 godzin skupienia łącznie.", total_minutes, 6000),
    ]

    return {
        "today": {
            "focus_seconds": today_values["seconds"],
            "pomodoros": today_values["completed"],
            "goal": daily_goal,
            "goal_reached": today_values["completed"] >= daily_goal,
        },
        "streak": {"current": current_streak, "longest": longest_streak},
        "level": level_for(total_minutes),
        "totals": {"focus_seconds": total_seconds, "pomodoros": total_completed, "active_days": len(per_day)},
        "records": {
            "best_day": {"date": best_day[0].isoformat(), "label": format_day(best_day[0]), "focus_seconds": best_day[1]["seconds"]}
            if best_day
            else None,
            "best_day_pomodoros": best_count,
            "longest_focus_seconds": longest_focus,
        },
        "achievements": achievements,
        "unlocked": sum(1 for item in achievements if item["unlocked"]),
    }
