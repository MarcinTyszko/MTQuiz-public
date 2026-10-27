"""Pomodoro: stan minutnika, zapis faz, statystyki, ustawienia konta i powiadomienia push."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from .. import push
from ..deps import DbSession, UnlockedUser
from ..models import PomodoroEntry, PomodoroTimer, PushSubscription, ScheduledPush, utcnow
from ..pomodoro import KINDS, StatsPeriod, build_stats, build_summary
from ..preferences import load_preferences, update_preferences
from ..schemas import MessageOut

router = APIRouter(tags=["pomodoro"])

MAX_STATE_BYTES = 16 * 1024
MAX_PHASE_SECONDS = 4 * 3600


class ScheduledNotice(BaseModel):
    # Czas względny, nie bezwzględny — zegar telefonu może się różnić od zegara serwera.
    in_seconds: float = Field(ge=0, le=86400)
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(default="", max_length=255)


class TimerStateIn(BaseModel):
    revision: int = Field(ge=0)
    state: dict[str, Any]
    schedule: list[ScheduledNotice] = Field(default_factory=list, max_length=40)


class TimerStateOut(BaseModel):
    revision: int
    state: dict[str, Any]
    accepted: bool = True
    server_now: datetime


class EntryIn(BaseModel):
    client_key: str = Field(min_length=1, max_length=64)
    kind: Literal["focus", "short_break", "long_break"]
    planned_seconds: int = Field(ge=0, le=MAX_PHASE_SECONDS)
    actual_seconds: int = Field(ge=0, le=MAX_PHASE_SECONDS)
    completed: bool = False
    label: str = Field(default="", max_length=120)
    started_at: datetime
    ended_at: datetime

    @field_validator("started_at", "ended_at")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


class EntryOut(BaseModel):
    id: int
    kind: str
    planned_seconds: int
    actual_seconds: int
    completed: bool
    label: str
    started_at: datetime
    ended_at: datetime


class SubscriptionKeys(BaseModel):
    p256dh: str = Field(min_length=20, max_length=200)
    auth: str = Field(min_length=8, max_length=100)


class SubscriptionIn(BaseModel):
    endpoint: str = Field(min_length=10, max_length=2000)
    keys: SubscriptionKeys

    @field_validator("endpoint")
    @classmethod
    def _https(cls, value: str) -> str:
        if not value.startswith("https://"):
            raise ValueError("Adres usługi push musi używać HTTPS.")
        return value


class UnsubscribeIn(BaseModel):
    endpoint: str = Field(min_length=10, max_length=2000)


def _timer_out(timer: PomodoroTimer | None, accepted: bool = True) -> TimerStateOut:
    state: dict[str, Any] = {}
    if timer is not None:
        try:
            state = json.loads(timer.state or "{}")
        except json.JSONDecodeError:
            state = {}
    return TimerStateOut(
        revision=timer.revision if timer else 0,
        state=state,
        accepted=accepted,
        server_now=utcnow(),
    )


# --------------------------------------------------------------------------- #
# Stan minutnika                                                               #
# --------------------------------------------------------------------------- #


@router.get("/api/pomodoro/state", response_model=TimerStateOut)
def get_state(user: UnlockedUser, db: DbSession) -> TimerStateOut:
    return _timer_out(db.get(PomodoroTimer, user.id))


@router.put("/api/pomodoro/state", response_model=TimerStateOut)
def put_state(payload: TimerStateIn, user: UnlockedUser, db: DbSession) -> TimerStateOut:
    """Zapisuje stan minutnika i plan powiadomień o końcu kolejnych faz.

    Zapis o numerze rewizji nie wyższym niż zapisany jest odrzucany (``accepted:
    false``) wraz z aktualnym stanem — przeglądarka przyjmuje wtedy wersję serwera.
    """
    encoded = json.dumps(payload.state, ensure_ascii=False)
    if len(encoded.encode("utf-8")) > MAX_STATE_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Stan minutnika jest zbyt duży.")

    timer = db.get(PomodoroTimer, user.id)
    if timer is not None and payload.revision <= timer.revision:
        return _timer_out(timer, accepted=False)
    if timer is None:
        timer = PomodoroTimer(user_id=user.id)
        db.add(timer)
    timer.state = encoded
    timer.revision = payload.revision

    # Plan powiadomień zawsze zastępuje poprzedni: pauza lub stop go czyści.
    db.execute(delete(ScheduledPush).where(ScheduledPush.user_id == user.id, ScheduledPush.sent_at.is_(None)))
    now = utcnow()
    for notice in payload.schedule:
        db.add(
            ScheduledPush(
                user_id=user.id,
                fire_at=now + timedelta(seconds=notice.in_seconds),
                title=notice.title,
                body=notice.body,
                url="/pomodoro",
            )
        )
    db.commit()
    db.refresh(timer)
    return _timer_out(timer)


# --------------------------------------------------------------------------- #
# Wpisy i statystyki                                                           #
# --------------------------------------------------------------------------- #


def _utc(value: datetime) -> datetime:
    """SQLite zwraca czas bez strefy — w bazie zawsze leży UTC."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _entry_out(entry: PomodoroEntry) -> EntryOut:
    return EntryOut(
        id=entry.id,
        kind=entry.kind,
        planned_seconds=entry.planned_seconds,
        actual_seconds=entry.actual_seconds,
        completed=entry.completed,
        label=entry.label,
        started_at=_utc(entry.started_at),
        ended_at=_utc(entry.ended_at),
    )


@router.post("/api/pomodoro/entries", response_model=EntryOut)
def record_entry(payload: EntryIn, user: UnlockedUser, db: DbSession) -> EntryOut:
    """Zapisuje zakończoną fazę. Powtórzone zgłoszenie tej samej fazy zwraca istniejący wpis."""
    if payload.kind not in KINDS:  # pragma: no cover - pilnuje tego Literal
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Nieznany rodzaj fazy.")
    if payload.ended_at < payload.started_at:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Faza nie może skończyć się przed startem.")
    if payload.ended_at > utcnow() + timedelta(minutes=5):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Faza nie może kończyć się w przyszłości.")
    # Czas faktyczny nie może przekroczyć czasu, jaki upłynął od startu fazy.
    wall = (payload.ended_at - payload.started_at).total_seconds()
    actual = int(min(payload.actual_seconds, wall + 5))

    existing = db.scalar(
        select(PomodoroEntry).where(PomodoroEntry.user_id == user.id, PomodoroEntry.client_key == payload.client_key)
    )
    if existing is not None:
        return _entry_out(existing)

    entry = PomodoroEntry(
        user_id=user.id,
        client_key=payload.client_key,
        kind=payload.kind,
        planned_seconds=payload.planned_seconds,
        actual_seconds=max(0, actual),
        completed=payload.completed,
        label=payload.label.strip(),
        started_at=payload.started_at,
        ended_at=payload.ended_at,
    )
    db.add(entry)
    try:
        db.commit()
    except IntegrityError:
        # Dwie karty zgłosiły tę samą fazę w tej samej chwili.
        db.rollback()
        existing = db.scalar(
            select(PomodoroEntry).where(PomodoroEntry.user_id == user.id, PomodoroEntry.client_key == payload.client_key)
        )
        assert existing is not None
        return _entry_out(existing)
    db.refresh(entry)
    return _entry_out(entry)


@router.get("/api/pomodoro/entries", response_model=list[EntryOut])
def list_entries(
    user: UnlockedUser,
    db: DbSession,
    limit: int = Query(default=20, ge=1, le=200),
    kind: str | None = Query(default=None),
) -> list[EntryOut]:
    stmt = select(PomodoroEntry).where(PomodoroEntry.user_id == user.id)
    if kind:
        stmt = stmt.where(PomodoroEntry.kind == kind)
    rows = db.scalars(stmt.order_by(PomodoroEntry.ended_at.desc(), PomodoroEntry.id.desc()).limit(limit))
    return [_entry_out(row) for row in rows]


@router.delete("/api/pomodoro/entries/{entry_id}", response_model=MessageOut)
def delete_entry(entry_id: int, user: UnlockedUser, db: DbSession) -> MessageOut:
    entry = db.get(PomodoroEntry, entry_id)
    if entry is None or entry.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nie znaleziono wpisu.")
    db.delete(entry)
    db.commit()
    return MessageOut(message="Wpis usunięty ze statystyk.")


@router.get("/api/pomodoro/stats")
def stats(
    user: UnlockedUser,
    db: DbSession,
    period: StatsPeriod = StatsPeriod.WEEK,
    offset: int = Query(default=0, ge=-520, le=0),
) -> dict[str, Any]:
    """Statystyki dnia, tygodnia, miesiąca albo roku wraz z porównaniem do poprzedniego okresu."""
    return build_stats(db, user, period, offset)


@router.get("/api/pomodoro/summary")
def summary(user: UnlockedUser, db: DbSession) -> dict[str, Any]:
    """Postęp dnia, seria, poziom, rekordy i odznaki."""
    goal = load_preferences(db, user).pomodoro.daily_goal
    return build_summary(db, user, goal)


# --------------------------------------------------------------------------- #
# Ustawienia konta                                                             #
# --------------------------------------------------------------------------- #


@router.get("/api/preferences")
def get_preferences(user: UnlockedUser, db: DbSession) -> dict[str, Any]:
    return load_preferences(db, user).model_dump()


@router.patch("/api/preferences")
def patch_preferences(payload: dict[str, Any], user: UnlockedUser, db: DbSession) -> dict[str, Any]:
    """Zmienia wybrane ustawienia; pozostałe zostają bez zmian."""
    try:
        return update_preferences(db, user, payload).model_dump()
    except ValidationError as exc:
        first = exc.errors()[0] if exc.errors() else {}
        where = ".".join(str(part) for part in first.get("loc", ()))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Nieprawidłowe ustawienie {where}: {first.get('msg', 'błędna wartość')}.",
        ) from exc


# --------------------------------------------------------------------------- #
# Powiadomienia push                                                           #
# --------------------------------------------------------------------------- #


@router.get("/api/push/key")
def push_key(user: UnlockedUser) -> dict[str, str]:
    """Klucz publiczny VAPID przekazywany do ``pushManager.subscribe``."""
    return {"public_key": push.vapid_keys().public_key}


@router.post("/api/push/subscriptions", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
def subscribe(payload: SubscriptionIn, request: Request, user: UnlockedUser, db: DbSession) -> MessageOut:
    existing = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == payload.endpoint))
    if existing is None:
        existing = PushSubscription(endpoint=payload.endpoint)
        db.add(existing)
    # Ta sama przeglądarka po przelogowaniu na inne konto przechodzi na nie.
    existing.user_id = user.id
    existing.p256dh = payload.keys.p256dh
    existing.auth = payload.keys.auth
    existing.user_agent = (request.headers.get("user-agent") or "")[:255]
    db.commit()
    return MessageOut(message="Powiadomienia włączone na tym urządzeniu.")


@router.delete("/api/push/subscriptions", response_model=MessageOut)
def unsubscribe(payload: UnsubscribeIn, user: UnlockedUser, db: DbSession) -> MessageOut:
    db.execute(
        delete(PushSubscription).where(PushSubscription.endpoint == payload.endpoint, PushSubscription.user_id == user.id)
    )
    db.commit()
    return MessageOut(message="Powiadomienia wyłączone na tym urządzeniu.")


@router.post("/api/push/test", response_model=MessageOut)
def push_test(user: UnlockedUser, db: DbSession) -> MessageOut:
    """Wysyła powiadomienie próbne na wszystkie urządzenia konta."""
    count = db.scalar(select(PushSubscription.id).where(PushSubscription.user_id == user.id).limit(1))
    if count is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Na tym koncie nie ma urządzeń z włączonymi powiadomieniami.")
    delivered = push.deliver_to_user(
        user.id,
        {"title": "MTQuiz · Pomodoro", "body": "Powiadomienia działają — tak zabrzmi koniec fazy.", "url": "/pomodoro", "tag": "mtquiz-test"},
    )
    if not delivered:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Usługa push nie przyjęła powiadomienia. Spróbuj włączyć je ponownie.")
    return MessageOut(message=f"Wysłano powiadomienie próbne ({delivered} {'urządzenie' if delivered == 1 else 'urządzenia'}).")
