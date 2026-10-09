"""Testy kalendarza aktywności, serii nauki i rankingów."""
from __future__ import annotations

import copy
from datetime import date, datetime, timedelta, timezone

import pytest

from conftest import SAMPLE_SET, register, unlock_admin

UTC = timezone.utc


@pytest.fixture(autouse=True)
def warsaw(app_module, monkeypatch):
    """Granice dni i tygodni zawsze według czasu polskiego — niezależnie od maszyny testowej."""
    from app.config import settings

    monkeypatch.setattr(settings, "timezone", "Europe/Warsaw")


def _set_id(client) -> int:
    payload = copy.deepcopy(SAMPLE_SET)
    payload["visibility"] = "public"
    return client.post("/api/sets", json=payload).json()["id"]


def _session(user_id: int, set_id: int, when: datetime, total: int, *, mode: str = "quiz", score: int | None = None):
    from app.database import session_scope
    from app.models import StudyMode, StudySession

    with session_scope() as db:
        db.add(
            StudySession(
                user_id=user_id,
                set_id=set_id,
                mode=StudyMode(mode),
                score=total if score is None else score,
                total=total,
                duration_seconds=60,
                created_at=when,
            )
        )


def _heatmap(user_id: int, now: datetime, weeks: int = 53):
    from app.activity import build_heatmap
    from app.database import session_scope
    from app.models import User

    with session_scope() as db:
        return build_heatmap(db, db.get(User, user_id), weeks, now=now)


def _days(heatmap) -> dict[date, tuple[int, int, int]]:
    return {day.day: (day.items, day.sessions, day.level) for day in heatmap.days}


# --------------------------------------------------------------------------- #
# Kalendarz aktywności
# --------------------------------------------------------------------------- #
def test_kalendarz_przypisuje_sesje_do_lokalnego_dnia(client):
    user = register(client)
    set_id = _set_id(client)
    # 23:30 UTC 27 marca to już 28 marca w Warszawie (CET, UTC+1).
    _session(user["id"], set_id, datetime(2026, 3, 27, 23, 30, tzinfo=UTC), 10)
    # 29 marca 2026 zmiana czasu: 22:30 UTC to 00:30 CEST 30 marca.
    _session(user["id"], set_id, datetime(2026, 3, 29, 22, 30, tzinfo=UTC), 7)
    # Dwie sesje tego samego lokalnego dnia sumują się.
    _session(user["id"], set_id, datetime(2026, 3, 29, 9, 0, tzinfo=UTC), 4, mode="flashcards")
    _session(user["id"], set_id, datetime(2026, 3, 29, 15, 0, tzinfo=UTC), 6)

    days = _days(_heatmap(user["id"], now=datetime(2026, 4, 2, 12, 0, tzinfo=UTC)))

    assert days[date(2026, 3, 27)][:2] == (0, 0)
    assert days[date(2026, 3, 28)][:2] == (10, 1)
    assert days[date(2026, 3, 29)][:2] == (10, 2)
    assert days[date(2026, 3, 30)][:2] == (7, 1)


def test_kalendarz_ma_pelne_tygodnie_od_poniedzialku(client):
    user = register(client)
    now = datetime(2026, 10, 8, 10, 0, tzinfo=UTC)  # czwartek
    heatmap = _heatmap(user["id"], now=now, weeks=26)

    assert len(heatmap.weeks) == 26
    assert all(len(week) == 7 for week in heatmap.weeks)
    assert heatmap.start.weekday() == 0
    assert heatmap.end == date(2026, 10, 8)
    # Piątek–niedziela bieżącego tygodnia to przyszłość: bez kafelków do pokolorowania.
    assert [day.is_future for day in heatmap.weeks[-1]] == [False] * 4 + [True] * 3
    assert len(heatmap.days) == 25 * 7 + 4
    assert len(heatmap.month_labels) == 26
    assert "paź" in heatmap.month_labels


def test_sesje_spoza_okna_i_innych_kont_nie_sa_liczone(client):
    first = register(client, "pierwszy")
    set_id = _set_id(client)
    second = register(client, "drugi")
    now = datetime(2026, 10, 8, 10, 0, tzinfo=UTC)

    _session(first["id"], set_id, now - timedelta(days=500), 50)
    _session(second["id"], set_id, now - timedelta(hours=1), 9)

    heatmap = _heatmap(first["id"], now=now)
    assert heatmap.total_items == 0
    assert heatmap.active_days == 0
    assert heatmap.best_day is None


def test_poziomy_intensywnosci_to_kwartyle(app_module):
    from app.activity import intensity_level, intensity_thresholds

    thresholds = intensity_thresholds([0, 5, 10, 20, 40, 0])
    assert thresholds == (5, 10, 20)
    levels = [intensity_level(items, 1, thresholds) for items in (0, 5, 10, 15, 25, 40)]
    assert levels == [1, 1, 2, 3, 4, 4]
    assert intensity_level(0, 0, thresholds) == 0
    assert intensity_thresholds([]) == (1, 1, 1)


def test_seria_dni_nauki(client):
    user = register(client)
    set_id = _set_id(client)
    now = datetime(2026, 10, 8, 18, 0, tzinfo=UTC)
    # Najdłuższa seria: 4 dni we wrześniu; bieżąca: wczoraj i przedwczoraj (dziś jeszcze bez nauki).
    for day in (10, 11, 12, 13):
        _session(user["id"], set_id, datetime(2026, 9, day, 12, 0, tzinfo=UTC), 5)
    for day in (6, 7):
        _session(user["id"], set_id, datetime(2026, 10, day, 12, 0, tzinfo=UTC), 5)

    heatmap = _heatmap(user["id"], now=now)
    assert heatmap.current_streak == 2
    assert heatmap.longest_streak == 4
    assert heatmap.studied_today is False

    _session(user["id"], set_id, datetime(2026, 10, 8, 17, 0, tzinfo=UTC), 1)
    heatmap = _heatmap(user["id"], now=now)
    assert heatmap.current_streak == 3
    assert heatmap.studied_today is True


def test_przerwa_zeruje_biezaca_serie(client):
    user = register(client)
    set_id = _set_id(client)
    now = datetime(2026, 10, 8, 18, 0, tzinfo=UTC)
    _session(user["id"], set_id, datetime(2026, 10, 5, 12, 0, tzinfo=UTC), 5)

    heatmap = _heatmap(user["id"], now=now)
    assert heatmap.current_streak == 0
    assert heatmap.longest_streak == 1


def test_api_kalendarza(client):
    register(client)
    set_id = _set_id(client)
    client.post("/api/study/sessions", json={"set_id": set_id, "mode": "quiz", "score": 3, "total": 4})
    client.post("/api/study/sessions", json={"set_id": set_id, "mode": "flashcards", "score": 1, "total": 2})

    data = client.get("/api/activity/heatmap?weeks=4").json()
    assert data["timezone"] == "Europe/Warsaw"
    assert data["total_items"] == 6
    assert data["total_sessions"] == 2
    assert data["current_streak"] == 1
    assert data["studied_today"] is True
    today = [day for day in data["days"] if day["items"]]
    assert len(today) == 1 and today[0]["level"] >= 1
    assert client.get("/api/activity/heatmap?weeks=200").status_code == 422


def _query_plans(run) -> list[str]:
    """Plany SQLite dla zapytań o sesje wykonanych przez ``run(db)``."""
    from sqlalchemy import event

    from app.database import get_engine, session_scope

    captured: list[tuple[str, object]] = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        if "study_sessions" in statement and not statement.startswith("EXPLAIN"):
            captured.append((statement, parameters))

    engine = get_engine()
    event.listen(engine, "before_cursor_execute", capture)
    try:
        with session_scope() as db:
            run(db)
            connection = db.connection()
            return [
                " | ".join(str(row[-1]) for row in connection.exec_driver_sql("EXPLAIN QUERY PLAN " + sql, params))
                for sql, params in list(captured)
            ]
    finally:
        event.remove(engine, "before_cursor_execute", capture)


def test_kalendarz_i_rankingi_czytaja_wylacznie_indeks_pokrywajacy(client):
    """Agregacje nie mogą sięgać do wierszy tabeli — na wolumenie Dockera losowe odczyty są drogie."""
    from app.activity import build_heatmap
    from app.leaderboard import Period, build_leaderboard
    from app.models import User

    user = register(client)
    _session(user["id"], _set_id(client), datetime(2026, 10, 7, 12, tzinfo=UTC), 5)

    def run(db):
        viewer = db.get(User, user["id"])
        build_heatmap(db, viewer)
        build_leaderboard(db, Period.WEEK, viewer)
        build_leaderboard(db, Period.ALL, viewer)

    heatmap_plan, weekly_plan, all_time_plan = _query_plans(run)
    assert "COVERING INDEX ix_study_sessions_activity" in heatmap_plan, heatmap_plan
    assert "COVERING INDEX ix_study_sessions_activity" in all_time_plan, all_time_plan
    # Ranking tygodniowy czyta tylko sesje z bieżącego tygodnia (zakres po indeksie daty);
    # pełne przejście tabeli byłoby błędem.
    assert "SCAN study_sessions" not in weekly_plan, weekly_plan
    assert "USING INDEX" in weekly_plan or "USING COVERING INDEX" in weekly_plan, weekly_plan


# --------------------------------------------------------------------------- #
# Ranking
# --------------------------------------------------------------------------- #
def _board(period: str, viewer_id: int | None = None, *, now: datetime, limit: int = 50):
    from app.database import session_scope
    from app.leaderboard import Period, build_leaderboard
    from app.models import User

    with session_scope() as db:
        viewer = db.get(User, viewer_id) if viewer_id else None
        return build_leaderboard(db, Period(period), viewer, limit=limit, now=now)


def test_tydzien_rankingowy_trwa_od_poniedzialku_do_niedzieli(app_module):
    from app.leaderboard import current_week

    # Niedziela 23:30 w Warszawie (CEST) — wciąż tydzień 5–11 października.
    sunday = current_week(datetime(2026, 10, 11, 21, 30, tzinfo=UTC))
    assert (sunday.start, sunday.end) == (date(2026, 10, 5), date(2026, 10, 11))
    assert sunday.days_left(datetime(2026, 10, 11, 21, 30, tzinfo=UTC)) == 1
    assert sunday.resets_at == datetime(2026, 10, 11, 22, 0, tzinfo=UTC)

    # Poniedziałek 00:30 w Warszawie — nowy tydzień.
    monday = current_week(datetime(2026, 10, 11, 22, 30, tzinfo=UTC))
    assert (monday.start, monday.end) == (date(2026, 10, 12), date(2026, 10, 18))
    assert monday.label == "12–18 października"
    assert current_week(datetime(2026, 9, 30, 12, tzinfo=UTC)).label == "28 września – 4 października"


def test_ranking_ogolny_i_tygodniowy(client):
    ania = register(client, "ania")
    set_id = _set_id(client)
    bartek = register(client, "bartek")
    celina = register(client, "celina")
    now = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)  # czwartek

    # Ania: dużo nauki w zeszłym tygodniu, mało w bieżącym.
    _session(ania["id"], set_id, datetime(2026, 9, 30, 12, tzinfo=UTC), 100)
    _session(ania["id"], set_id, datetime(2026, 10, 6, 12, tzinfo=UTC), 5)
    # Bartek: tylko bieżący tydzień — quiz i fiszki.
    _session(bartek["id"], set_id, datetime(2026, 10, 7, 12, tzinfo=UTC), 20, score=15)
    _session(bartek["id"], set_id, datetime(2026, 10, 8, 8, tzinfo=UTC), 30, mode="flashcards", score=10)
    # Celina: zero elementów — nie trafia do rankingu.
    _session(celina["id"], set_id, datetime(2026, 10, 7, 12, tzinfo=UTC), 0)

    all_time = _board("all", ania["id"], now=now)
    assert [(entry.username, entry.rank, entry.points) for entry in all_time.entries] == [
        ("ania", 1, 105),
        ("bartek", 2, 50),
    ]
    assert all_time.viewer.username == "ania"
    assert all_time.participants == 2

    weekly = _board("week", ania["id"], now=now)
    assert [(entry.username, entry.points) for entry in weekly.entries] == [("bartek", 50), ("ania", 5)]
    leader = weekly.entries[0]
    assert (leader.quiz_items, leader.card_items, leader.quiz_accuracy) == (20, 30, 75.0)
    assert weekly.viewer.rank == 2
    assert weekly.week.label == "5–11 października"


def test_remis_daje_to_samo_miejsce(client):
    users = [register(client, name) for name in ("ala", "bob", "cyryl", "daria")]
    set_id = _set_id(client)
    now = datetime(2026, 10, 8, 12, tzinfo=UTC)
    for user, points in zip(users, (30, 20, 20, 10)):
        _session(user["id"], set_id, now - timedelta(hours=2), points)

    board = _board("week", users[3]["id"], now=now)
    assert [entry.rank for entry in board.entries] == [1, 2, 2, 4]


def test_pozycja_konta_poza_lista(client):
    users = [register(client, name) for name in ("ala", "bob", "cyryl")]
    set_id = _set_id(client)
    now = datetime(2026, 10, 8, 12, tzinfo=UTC)
    for user, points in zip(users, (30, 20, 10)):
        _session(user["id"], set_id, now - timedelta(hours=2), points)

    board = _board("week", users[2]["id"], now=now, limit=2)
    assert len(board.entries) == 2
    assert board.viewer_outside_list is True
    assert board.viewer.rank == 3


def test_konto_zablokowane_znika_z_rankingu(client, app_module):
    from fastapi.testclient import TestClient

    ala = register(client, "ala")
    set_id = _set_id(client)
    now = datetime(2026, 10, 8, 12, tzinfo=UTC)
    _session(ala["id"], set_id, now - timedelta(hours=1), 10)

    with TestClient(app_module.app) as admin:
        unlock_admin(admin)
        assert admin.patch(f"/api/admin/users/{ala['id']}", json={"is_active": False}).status_code == 200

    assert _board("all", now=now).entries == []


def test_api_rankingu(client):
    register(client, "ala")
    set_id = _set_id(client)
    client.post("/api/study/sessions", json={"set_id": set_id, "mode": "quiz", "score": 8, "total": 10})

    weekly = client.get("/api/activity/leaderboard").json()
    assert weekly["period"] == "week"
    assert weekly["viewer"]["points"] == 10
    assert weekly["viewer"]["quiz_accuracy"] == 80.0
    assert weekly["week_start"] <= date.today().isoformat() <= weekly["week_end"]

    all_time = client.get("/api/activity/leaderboard?period=all").json()
    assert all_time["entries"][0]["username"] == "ala"
    assert client.get("/api/activity/leaderboard?period=month").status_code == 422


def test_zawyzony_wynik_sesji_jest_odrzucany(client):
    register(client)
    set_id = _set_id(client)
    response = client.post(
        "/api/study/sessions", json={"set_id": set_id, "mode": "quiz", "score": 0, "total": 1_000_000}
    )
    assert response.status_code == 422


# --------------------------------------------------------------------------- #
# Widoki
# --------------------------------------------------------------------------- #
def test_pulpit_pokazuje_kalendarz_i_ranking_tygodnia(client):
    register(client, "ala")
    set_id = _set_id(client)
    client.post("/api/study/sessions", json={"set_id": set_id, "mode": "quiz", "score": 2, "total": 3})

    page = client.get("/pulpit")
    assert page.status_code == 200
    assert "Aktywność nauki" in page.text
    assert "Ranking tygodnia" in page.text
    assert "Twoje miejsce:" in page.text
    assert "3 elementy (1 sesja)" in page.text


def test_strona_rankingu(client):
    register(client, "ala")
    set_id = _set_id(client)
    client.post("/api/study/sessions", json={"set_id": set_id, "mode": "quiz", "score": 2, "total": 3})

    page = client.get("/ranking")
    assert page.status_code == 200
    assert "Ten tydzień" in page.text and "Od początku" in page.text
    assert "ala" in page.text
    assert "3 punkty" in page.text


def test_strona_rankingu_wymaga_logowania(client):
    response = client.get("/ranking", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/logowanie")


def test_pusty_ranking(client):
    register(client)
    page = client.get("/ranking")
    assert "Ranking jest jeszcze pusty" in page.text
