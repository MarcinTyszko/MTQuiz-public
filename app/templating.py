"""Konfiguracja silnika szablonów Jinja2 wraz z filtrami pomocniczymi."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape

from .config import STATIC_DIR, TEMPLATES_DIR, settings

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def format_datetime(value: datetime | None, pattern: str = "%d.%m.%Y %H:%M") -> str:
    if value is None:
        return "—"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.strftime(pattern)


def relative_time(value: datetime | None) -> str:
    """Zwraca przyjazny opis czasu, np. „3 dni temu”."""
    if value is None:
        return "—"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - value
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return "przed chwilą"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} min temu"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} godz. temu"
    days = hours // 24
    if days == 1:
        return "wczoraj"
    if days < 31:
        return f"{days} dni temu"
    months = days // 30
    if months < 12:
        return f"{months} mies. temu"
    return format_datetime(value, "%d.%m.%Y")


def format_bytes(value: int | None) -> str:
    size = float(value or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def to_json(value: object) -> Markup:
    """JSON do osadzenia w bloku ``<script>`` — neutralizuje znaczniki HTML."""
    encoded = json.dumps(value, ensure_ascii=False, default=str)
    encoded = encoded.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return Markup(encoded)


def to_json_attr(value: object) -> Markup:
    """JSON do osadzenia w atrybucie HTML (np. ``x-data``).

    Cudzysłowy muszą zostać zamienione na encje, inaczej wartość atrybutu
    kończyłaby się przedwcześnie. Przeglądarka rozkoduje encje przed
    przekazaniem wyrażenia do Alpine.js.
    """
    encoded = json.dumps(value, ensure_ascii=False, default=str)
    return Markup(escape(encoded))


def current_year() -> int:
    """Rok używany w nocie o prawach autorskich — liczony przy każdym renderowaniu."""
    return datetime.now(timezone.utc).year


def plural_pl(count: int, one: str, few: str, many: str) -> str:
    """Poprawna odmiana rzeczownika po liczebniku (np. 1 fiszka, 2 fiszki, 5 fiszek)."""
    if count == 1:
        return one
    last_two = count % 100
    last = count % 10
    if 2 <= last <= 4 and not 12 <= last_two <= 14:
        return few
    return many


_static_versions: dict[str, str] = {}


def static_url(path: str) -> str:
    """Zwraca adres zasobu statycznego z sygnaturą wersji.

    Sygnatura pochodzi z czasu modyfikacji pliku, dzięki czemu po aktualizacji
    aplikacji przeglądarki pobierają nowe arkusze i skrypty zamiast wersji
    z pamięci podręcznej.
    """
    normalised = path.lstrip("/")
    cached = _static_versions.get(normalised)
    if cached is None:
        target = STATIC_DIR / normalised
        try:
            cached = f"{int(target.stat().st_mtime):x}"
        except OSError:
            cached = "0"
        _static_versions[normalised] = cached
    return f"/static/{normalised}?v={cached}"


templates.env.filters["dt"] = format_datetime
templates.env.filters["relative"] = relative_time
templates.env.filters["bytes"] = format_bytes
templates.env.filters["tojson_safe"] = to_json
templates.env.filters["tojson_attr"] = to_json_attr
templates.env.globals["plural_pl"] = plural_pl
templates.env.globals["static_url"] = static_url
templates.env.globals["app_name"] = settings.app_name
templates.env.globals["current_year"] = current_year
templates.env.globals["app_tagline"] = settings.app_tagline
templates.env.globals["allow_registration"] = settings.allow_registration
