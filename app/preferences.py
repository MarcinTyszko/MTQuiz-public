"""Ustawienia konta: konfiguracja Pomodoro i funkcje włączane na życzenie.

Dokument JSON w tabeli ``user_preferences`` jest uzupełniany wartościami
domyślnymi przy każdym odczycie, więc dodanie nowego ustawienia nie wymaga
migracji, a uszkodzony lub częściowy zapis nie psuje strony.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from .models import User, UserPreferences

logger = logging.getLogger("mtquiz")


class PomodoroConfig(BaseModel):
    """Parametry serii Pomodoro, np. 25/5 × 4 z długą przerwą 15 minut."""

    model_config = ConfigDict(extra="ignore")

    focus_minutes: int = Field(default=25, ge=1, le=180)
    short_break_minutes: int = Field(default=5, ge=1, le=60)
    # 0 — seria kończy się bez długiej przerwy.
    long_break_minutes: int = Field(default=15, ge=0, le=90)
    rounds: int = Field(default=4, ge=1, le=12)
    auto_start_breaks: bool = True
    auto_start_focus: bool = False
    sound: bool = True
    daily_goal: int = Field(default=8, ge=1, le=24)


class Preferences(BaseModel):
    model_config = ConfigDict(extra="ignore")

    pomodoro: PomodoroConfig = Field(default_factory=PomodoroConfig)
    # Zakładka Pomodoro w menu i minutnik na stronach.
    pomodoro_enabled: bool = True
    # Pływający minutnik widoczny na każdej stronie, gdy seria trwa.
    pomodoro_widget: bool = True
    # Dźwięki tła (szum, ton, rytmy binauralne) — domyślnie ukryte, włączane w „Moje konto”.
    ambient_sounds: bool = False


def _validated(raw: dict[str, Any]) -> Preferences:
    """Waliduje dokument; pole z niepoprawną wartością wraca do domyślnej, reszta zostaje."""
    try:
        return Preferences.model_validate(raw)
    except ValidationError as exc:
        cleaned = json.loads(json.dumps(raw))
        for error in exc.errors():
            location = [part for part in error.get("loc", ()) if isinstance(part, str)]
            target = cleaned
            for part in location[:-1]:
                target = target.get(part, {}) if isinstance(target, dict) else {}
            if location and isinstance(target, dict):
                target.pop(location[-1], None)
        try:
            return Preferences.model_validate(cleaned)
        except ValidationError:  # pragma: no cover - ostatnia linia obrony
            return Preferences()


def _stored(db: Session, user: User) -> dict[str, Any]:
    row = db.get(UserPreferences, user.id)
    if row is None:
        return {}
    try:
        data = json.loads(row.data or "{}")
    except json.JSONDecodeError:
        logger.warning("Uszkodzone ustawienia konta #%s — używam domyślnych.", user.id)
        return {}
    return data if isinstance(data, dict) else {}


def load_preferences(db: Session, user: User) -> Preferences:
    return _validated(_stored(db, user))


def _merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def update_preferences(db: Session, user: User, patch: dict[str, Any]) -> Preferences:
    """Scala zmiany z zapisanymi ustawieniami. Niepoprawne wartości zgłaszają ``ValidationError``."""
    current = load_preferences(db, user).model_dump()
    updated = Preferences.model_validate(_merge(current, patch))

    row = db.get(UserPreferences, user.id)
    if row is None:
        row = UserPreferences(user_id=user.id)
        db.add(row)
    row.data = updated.model_dump_json()
    db.commit()
    return updated
