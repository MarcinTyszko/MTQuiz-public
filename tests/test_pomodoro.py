"""Testy Pomodoro: ustawienia konta, stan minutnika, wpisy, statystyki, odznaki i powiadomienia push."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

import pytest

from conftest import register

UTC = timezone.utc


@pytest.fixture(autouse=True)
def warsaw(app_module, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "timezone", "Europe/Warsaw")


def _entry(client, key: str, ended: datetime, minutes: int = 25, *, completed: bool = True, label: str = "", kind: str = "focus"):
    started = ended - timedelta(minutes=minutes)
    return client.post(
        "/api/pomodoro/entries",
        json={
            "client_key": key,
            "kind": kind,
            "planned_seconds": minutes * 60,
            "actual_seconds": minutes * 60,
            "completed": completed,
            "label": label,
            "started_at": started.isoformat(),
            "ended_at": ended.isoformat(),
        },
    )


def _db_entry(user_id: int, key: str, ended: datetime, minutes: int = 25, *, completed: bool = True, label: str = ""):
    from app.database import session_scope
    from app.models import PomodoroEntry

    with session_scope() as db:
        db.add(
            PomodoroEntry(
                user_id=user_id,
                client_key=key,
                kind="focus",
                planned_seconds=minutes * 60,
                actual_seconds=minutes * 60,
                completed=completed,
                label=label,
                started_at=ended - timedelta(minutes=minutes),
                ended_at=ended,
            )
        )


def _with_user(user_id: int, fn, *args, **kwargs):
    from app.database import session_scope
    from app.models import User

    with session_scope() as db:
        return fn(db, db.get(User, user_id), *args, **kwargs)


# --------------------------------------------------------------------------- #
# Ustawienia konta
# --------------------------------------------------------------------------- #
def test_ustawienia_maja_wartosci_domyslne(client):
    register(client)
    prefs = client.get("/api/preferences").json()

    assert prefs["pomodoro_enabled"] is True
    assert prefs["pomodoro_widget"] is True
    # Dźwięki tła są ukryte, dopóki użytkownik ich nie włączy.
    assert prefs["ambient_sounds"] is False
    assert prefs["pomodoro"]["focus_minutes"] == 25
    assert prefs["pomodoro"]["rounds"] == 4


def test_zmiana_ustawien_scala_sie_z_zapisanymi(client):
    register(client)
    client.patch("/api/preferences", json={"pomodoro": {"focus_minutes": 50, "rounds": 3}})
    prefs = client.patch("/api/preferences", json={"ambient_sounds": True}).json()

    assert prefs["ambient_sounds"] is True
    assert prefs["pomodoro"]["focus_minutes"] == 50
    assert prefs["pomodoro"]["rounds"] == 3
    assert prefs["pomodoro"]["short_break_minutes"] == 5


def test_niepoprawne_ustawienie_jest_odrzucane(client):
    register(client)
    response = client.patch("/api/preferences", json={"pomodoro": {"focus_minutes": 0}})

    assert response.status_code == 422
    assert client.get("/api/preferences").json()["pomodoro"]["focus_minutes"] == 25


def test_uszkodzone_ustawienia_wracaja_do_domyslnych(client):
    user = register(client)
    from app.database import session_scope
    from app.models import UserPreferences

    with session_scope() as db:
        db.add(UserPreferences(user_id=user["id"], data=json.dumps({"ambient_sounds": True, "pomodoro": {"rounds": 99}})))

    prefs = client.get("/api/preferences").json()
    assert prefs["ambient_sounds"] is True
    assert prefs["pomodoro"]["rounds"] == 4


def test_ustawienia_wymagaja_zalogowania(client):
    assert client.get("/api/preferences").status_code == 401


# --------------------------------------------------------------------------- #
# Stan minutnika i plan powiadomień
# --------------------------------------------------------------------------- #
def _scheduled(user_id: int):
    from sqlalchemy import select

    from app.database import session_scope
    from app.models import ScheduledPush

    with session_scope() as db:
        return [
            (row.title, row.fire_at)
            for row in db.scalars(select(ScheduledPush).where(ScheduledPush.user_id == user_id).order_by(ScheduledPush.fire_at))
        ]


def test_stan_minutnika_zapisuje_sie_z_planem_powiadomien(client):
    user = register(client)
    state = {"status": "running", "index": 0, "plan": [{"type": "focus", "seconds": 1500}]}
    response = client.put(
        "/api/pomodoro/state",
        json={
            "revision": 1,
            "state": state,
            "schedule": [
                {"in_seconds": 1500, "title": "Koniec skupienia", "body": "Przerwa 5 min"},
                {"in_seconds": 1800, "title": "Koniec przerwy"},
            ],
        },
    )
    assert response.status_code == 200
    assert response.json()["accepted"] is True

    assert client.get("/api/pomodoro/state").json()["state"] == state
    titles = [title for title, _ in _scheduled(user["id"])]
    assert titles == ["Koniec skupienia", "Koniec przerwy"]


def test_starsza_rewizja_nie_nadpisuje_nowszej(client):
    register(client)
    client.put("/api/pomodoro/state", json={"revision": 5, "state": {"status": "paused"}})
    response = client.put("/api/pomodoro/state", json={"revision": 4, "state": {"status": "idle"}})

    assert response.json()["accepted"] is False
    assert response.json()["revision"] == 5
    assert response.json()["state"]["status"] == "paused"


def test_pauza_czysci_zaplanowane_powiadomienia(client):
    user = register(client)
    client.put(
        "/api/pomodoro/state",
        json={"revision": 1, "state": {"status": "running"}, "schedule": [{"in_seconds": 60, "title": "Koniec"}]},
    )
    client.put("/api/pomodoro/state", json={"revision": 2, "state": {"status": "paused"}, "schedule": []})

    assert _scheduled(user["id"]) == []


def test_stan_minutnika_trafia_do_strony(client):
    register(client)
    client.put("/api/pomodoro/state", json={"revision": 3, "state": {"status": "running", "index": 1}})
    html = client.get("/pulpit").text

    start = html.index('id="pomodoro-bootstrap">') + len('id="pomodoro-bootstrap">')
    data = json.loads(html[start : html.index("</script>", start)])
    assert data["timer"]["revision"] == 3
    assert data["timer"]["state"]["index"] == 1
    assert data["vapidKey"]
    assert 'aria-label="Minutnik Pomodoro"' in html


# --------------------------------------------------------------------------- #
# Wpisy
# --------------------------------------------------------------------------- #
def test_wpis_jest_idempotentny(client):
    register(client)
    ended = datetime.now(UTC) - timedelta(minutes=1)
    first = _entry(client, "seria:0", ended)
    second = _entry(client, "seria:0", ended)

    assert first.status_code == second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert len(client.get("/api/pomodoro/entries").json()) == 1
    # Czas w odpowiedzi jest jawnie w UTC — przeglądarka nie pomyli go z czasem lokalnym.
    assert first.json()["ended_at"].endswith("Z")


def test_wpis_z_przyszlosci_jest_odrzucany(client):
    register(client)
    assert _entry(client, "x", datetime.now(UTC) + timedelta(hours=1)).status_code == 422


def test_czas_faktyczny_nie_przekracza_czasu_od_startu(client):
    register(client)
    ended = datetime.now(UTC)
    response = client.post(
        "/api/pomodoro/entries",
        json={
            "client_key": "k",
            "kind": "focus",
            "planned_seconds": 1500,
            "actual_seconds": 1500,
            "completed": False,
            "started_at": (ended - timedelta(minutes=5)).isoformat(),
            "ended_at": ended.isoformat(),
        },
    )
    assert response.json()["actual_seconds"] <= 305


def test_wpisy_sa_prywatne(client):
    register(client, "pierwsza")
    entry = _entry(client, "a", datetime.now(UTC) - timedelta(minutes=2)).json()
    client.post("/api/auth/logout")
    register(client, "druga")

    assert client.get("/api/pomodoro/entries").json() == []
    assert client.delete(f"/api/pomodoro/entries/{entry['id']}").status_code == 404


def test_usuniecie_wpisu(client):
    register(client)
    entry = _entry(client, "a", datetime.now(UTC) - timedelta(minutes=2)).json()

    assert client.delete(f"/api/pomodoro/entries/{entry['id']}").status_code == 200
    assert client.get("/api/pomodoro/entries").json() == []


# --------------------------------------------------------------------------- #
# Statystyki
# --------------------------------------------------------------------------- #
def test_statystyki_tygodnia_z_porownaniem(client):
    from app.pomodoro import StatsPeriod, build_stats

    user = register(client)
    # Środa 14 października 2026, 18:00 w Warszawie.
    now = datetime(2026, 10, 14, 16, 0, tzinfo=UTC)
    # Bieżący tydzień (od poniedziałku 12.10): 3 bloki po 25 min.
    for i, day in enumerate((12, 13, 14)):
        _db_entry(user["id"], f"b{i}", datetime(2026, 10, day, 9, 0, tzinfo=UTC), label="Anatomia")
    # Poprzedni tydzień do tego samego momentu: 2 bloki; czwartkowy już się nie liczy.
    _db_entry(user["id"], "p1", datetime(2026, 10, 5, 9, 0, tzinfo=UTC))
    _db_entry(user["id"], "p2", datetime(2026, 10, 7, 9, 0, tzinfo=UTC))
    _db_entry(user["id"], "p3", datetime(2026, 10, 8, 9, 0, tzinfo=UTC))

    stats = _with_user(user["id"], build_stats, StatsPeriod.WEEK, 0, now=now)

    assert stats["label"] == "12–18 października"
    assert stats["totals"]["pomodoros"] == 3
    assert stats["totals"]["focus_seconds"] == 3 * 25 * 60
    assert stats["previous"]["pomodoros"] == 2
    assert stats["deltas"]["pomodoros"] == 50
    assert [bucket["pomodoros"] for bucket in stats["buckets"]] == [1, 1, 1, 0, 0, 0, 0]
    assert stats["current_bucket"] == 2
    assert stats["top_labels"][0]["label"] == "Anatomia"


def test_statystyki_zakonczonego_okresu_porownuja_calosc(client):
    from app.pomodoro import StatsPeriod, build_stats

    user = register(client)
    now = datetime(2026, 10, 14, 16, 0, tzinfo=UTC)
    _db_entry(user["id"], "p3", datetime(2026, 10, 8, 9, 0, tzinfo=UTC))

    stats = _with_user(user["id"], build_stats, StatsPeriod.WEEK, -1, now=now)
    assert stats["totals"]["pomodoros"] == 1
    assert stats["is_current"] is False
    assert stats["deltas"]["pomodoros"] is None


@pytest.mark.parametrize(
    ("period", "buckets"),
    [("day", 24), ("week", 7), ("month", 31), ("year", 12)],
)
def test_okresy_statystyk_maja_wlasciwa_liczbe_przedzialow(client, period, buckets):
    register(client)
    stats = client.get(f"/api/pomodoro/stats?period={period}").json()

    if period == "month":
        assert 28 <= len(stats["buckets"]) <= 31
    else:
        assert len(stats["buckets"]) == buckets


def test_dzien_przypisuje_wpisy_do_godzin_lokalnych(client):
    from app.pomodoro import StatsPeriod, build_stats

    user = register(client)
    now = datetime(2026, 10, 14, 20, 0, tzinfo=UTC)
    # 21:30 UTC to 23:30 w Warszawie (CEST).
    _db_entry(user["id"], "noc", datetime(2026, 10, 14, 21, 30, tzinfo=UTC) - timedelta(hours=2))
    stats = _with_user(user["id"], build_stats, StatsPeriod.DAY, 0, now=now)

    assert stats["buckets"][21]["pomodoros"] == 1


# --------------------------------------------------------------------------- #
# Grywalizacja
# --------------------------------------------------------------------------- #
def test_seria_poziom_i_odznaki(client):
    from app.pomodoro import build_summary

    user = register(client)
    now = datetime(2026, 10, 14, 16, 0, tzinfo=UTC)
    for day in (12, 13, 14):
        for n in range(4):
            _db_entry(user["id"], f"{day}-{n}", datetime(2026, 10, day, 8 + n, 0, tzinfo=UTC))
    _db_entry(user["id"], "glebia", datetime(2026, 10, 14, 15, 0, tzinfo=UTC), minutes=50)

    summary = _with_user(user["id"], build_summary, 4, now=now)
    unlocked = {item["key"] for item in summary["achievements"] if item["unlocked"]}

    assert summary["streak"] == {"current": 3, "longest": 3}
    assert summary["today"]["pomodoros"] == 5
    assert summary["today"]["goal_reached"] is True
    assert {"pierwszy", "rozgrzewka", "cel", "seria-3", "glebia"} <= unlocked
    assert "seria-7" not in unlocked
    # 12 × 25 + 50 = 350 minut — poziom „Sadzonka” (od 180 min).
    assert summary["level"]["name"] == "Sadzonka"
    assert summary["level"]["next_name"] == "Krzaczek"


def test_przerwane_bloki_nie_buduja_serii(client):
    from app.pomodoro import build_summary

    user = register(client)
    now = datetime(2026, 10, 14, 16, 0, tzinfo=UTC)
    _db_entry(user["id"], "a", datetime(2026, 10, 14, 9, 0, tzinfo=UTC), completed=False)

    summary = _with_user(user["id"], build_summary, 8, now=now)
    assert summary["streak"]["current"] == 0
    assert summary["totals"]["focus_seconds"] == 25 * 60


# --------------------------------------------------------------------------- #
# Powiadomienia push
# --------------------------------------------------------------------------- #
def _b64(data: bytes) -> str:
    import base64

    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def test_szyfrowanie_zgodne_z_wektorem_rfc_8291(app_module):
    """Dodatek A RFC 8291 — wynik musi zgadzać się co do bajtu."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    from app.push import b64url_decode, encrypt_payload

    def key(value: str):
        return ec.derive_private_key(int.from_bytes(b64url_decode(value), "big"), ec.SECP256R1())

    ua = key("q1dXpw3UpT5VOmu_cf_v6ih07Aems3njxI-JWgLcM94")
    ua_public = _b64(ua.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))
    body = encrypt_payload(
        b"When I grow up, I want to be a watermelon",
        ua_public,
        "BTBZMqHH6r4Tts7J_aSIgg",
        salt=b64url_decode("DGv6ra1nlYgDCS1FRnbzlw"),
        server_key=key("yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw"),
    )
    assert _b64(body) == (
        "DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A_"
        "yl95bQpu6cVPTpK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLVWGNWQexSgSxsj_Qulcy4a-fN"
    )


def test_token_vapid_jest_podpisany_kluczem_serwera(app_module):
    import jwt

    from app.push import vapid_authorization, vapid_keys

    header = vapid_authorization("https://fcm.googleapis.com/fcm/send/abc")
    token = header.split("t=")[1].split(",")[0]
    claims = jwt.decode(token, vapid_keys().private_key.public_key(), algorithms=["ES256"], audience="https://fcm.googleapis.com")

    assert claims["sub"].startswith("mailto:")
    assert header.endswith(f"k={vapid_keys().public_key}")


def test_klucz_vapid_jest_trwaly(client, data_dir):
    first = client.get("/api/push/key")
    assert first.status_code == 401
    register(client)
    key = client.get("/api/push/key").json()["public_key"]

    assert (data_dir / ".vapid_private.pem").exists()
    assert client.get("/api/push/key").json()["public_key"] == key


def _subscription() -> dict:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1())
    public = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return {"endpoint": "https://push.example.org/abc", "keys": {"p256dh": _b64(public), "auth": _b64(os.urandom(16))}}


def test_subskrypcja_wymaga_https(client):
    register(client)
    payload = _subscription()
    payload["endpoint"] = "http://push.example.org/abc"
    assert client.post("/api/push/subscriptions", json=payload).status_code == 422


def test_wysylka_zaplanowanych_powiadomien(client, monkeypatch):
    from app import push

    user = register(client)
    assert client.post("/api/push/subscriptions", json=_subscription()).status_code == 201
    client.put(
        "/api/pomodoro/state",
        json={"revision": 1, "state": {"status": "running"}, "schedule": [{"in_seconds": 0, "title": "Koniec skupienia", "body": "Przerwa"}]},
    )

    sent = []
    monkeypatch.setattr(push, "send_push", lambda subscription, message, **kw: sent.append(message) or 201)
    push.dispatch_due(datetime.now(UTC) + timedelta(seconds=1))
    # Drugie przejście niczego nie wysyła ponownie.
    push.dispatch_due(datetime.now(UTC) + timedelta(seconds=2))

    assert [message["title"] for message in sent] == ["Koniec skupienia"]
    assert sent[0]["url"] == "/pomodoro"
    assert user["id"]


def test_spoznione_powiadomienie_nie_jest_wysylane(client, monkeypatch):
    from app import push

    register(client)
    client.post("/api/push/subscriptions", json=_subscription())
    client.put("/api/pomodoro/state", json={"revision": 1, "state": {}, "schedule": [{"in_seconds": 0, "title": "Stare"}]})

    sent = []
    monkeypatch.setattr(push, "send_push", lambda subscription, message, **kw: sent.append(message) or 201)
    push.dispatch_due(datetime.now(UTC) + timedelta(minutes=30))
    assert sent == []


def test_wygasla_subskrypcja_jest_usuwana(client, monkeypatch):
    from sqlalchemy import func, select

    from app import push
    from app.database import session_scope
    from app.models import PushSubscription

    user = register(client)
    client.post("/api/push/subscriptions", json=_subscription())
    monkeypatch.setattr(push, "send_push", lambda subscription, message, **kw: 410)

    assert push.deliver_to_user(user["id"], {"title": "x"}) == 0
    with session_scope() as db:
        assert db.scalar(select(func.count(PushSubscription.id))) == 0


def test_powiadomienie_probne_bez_urzadzen(client):
    register(client)
    assert client.post("/api/push/test").status_code == 404


# --------------------------------------------------------------------------- #
# Strony
# --------------------------------------------------------------------------- #
def test_strona_pomodoro(client):
    assert client.get("/pomodoro", follow_redirects=False).status_code == 303
    register(client)
    html = client.get("/pomodoro").text

    assert 'x-data="pomodoroPage()"' in html
    assert "/static/js/pomodoro.js" in html
    assert 'href="/pomodoro"' in html


def test_wylaczone_pomodoro_znika_z_menu(client):
    register(client)
    client.patch("/api/preferences", json={"pomodoro_enabled": False})
    html = client.get("/pulpit").text

    assert 'href="/pomodoro"' not in html
    assert 'aria-label="Minutnik Pomodoro"' not in html


def test_konto_pokazuje_przelaczniki_pomodoro(client):
    register(client)
    html = client.get("/konto").text

    assert "ustawieniaPomodoro(" in html
    assert "Dźwięki tła" in html


def test_service_worker_i_manifest(client):
    worker = client.get("/sw.js")
    assert worker.status_code == 200
    assert worker.headers["service-worker-allowed"] == "/"
    assert "showNotification" in worker.text

    manifest = client.get("/manifest.webmanifest")
    assert manifest.headers["content-type"].startswith("application/manifest+json")
    data = manifest.json()
    assert data["display"] == "standalone"
    for icon in data["icons"]:
        assert client.get(icon["src"]).status_code == 200
