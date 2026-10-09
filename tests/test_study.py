"""Testy rejestrowania sesji nauki i statystyk pulpitu."""
from __future__ import annotations

import copy

from conftest import SAMPLE_SET, register


def make_set(client, visibility="private"):
    payload = copy.deepcopy(SAMPLE_SET)
    payload["visibility"] = visibility
    return client.post("/api/sets", json=payload).json()


def test_zapis_sesji_quizu_i_historii(client):
    register(client)
    created = make_set(client)

    response = client.post(
        "/api/study/sessions",
        json={"set_id": created["id"], "mode": "quiz", "score": 8, "total": 10, "duration_seconds": 240},
    )
    assert response.status_code == 201, response.text
    session = response.json()
    assert session["accuracy"] == 80.0
    assert session["set_title"] == created["title"]

    history = client.get("/api/study/sessions").json()
    assert len(history) == 1
    assert history[0]["mode"] == "quiz"


def test_wynik_nie_moze_przekroczyc_liczby_pytan(client):
    register(client)
    created = make_set(client)
    response = client.post(
        "/api/study/sessions",
        json={"set_id": created["id"], "mode": "quiz", "score": 11, "total": 10},
    )
    assert response.status_code == 422


def test_statystyki_pulpitu_licza_sredna_skutecznosc(client):
    register(client)
    created = make_set(client)
    for score in (10, 6):
        client.post(
            "/api/study/sessions",
            json={"set_id": created["id"], "mode": "quiz", "score": score, "total": 10, "duration_seconds": 60},
        )

    stats = client.get("/api/study/stats").json()
    assert stats["sets_owned"] == 1
    assert stats["cards_total"] == 2
    assert stats["questions_total"] == 1
    assert stats["sessions_last_30_days"] == 2
    assert stats["average_accuracy"] == 80.0


def test_oznaczone_fiszki_sa_widoczne_w_statystykach(client):
    register(client)
    created = make_set(client)
    client.post(f"/api/cards/{created['cards'][0]['id']}/star")

    assert client.get("/api/study/stats").json()["starred_cards"] == 1


def test_nie_mozna_zapisac_sesji_dla_cudzego_prywatnego_zestawu(client):
    register(client, "autor", "HasloAutora123")
    created = make_set(client)
    client.post("/api/auth/logout")

    register(client, "obcy", "HasloObcego1234")
    response = client.post(
        "/api/study/sessions",
        json={"set_id": created["id"], "mode": "flashcards", "score": 1, "total": 2},
    )
    assert response.status_code == 403


def test_licznik_wyswietlen_rosnie_tylko_dla_obcych(client):
    register(client, "autor", "HasloAutora123")
    created = make_set(client, visibility="public")

    client.post(f"/api/sets/{created['id']}/view")
    assert client.get(f"/api/sets/{created['id']}").json()["view_count"] == 0

    client.post("/api/auth/logout")
    register(client, "widz", "HasloWidza12345")
    client.post(f"/api/sets/{created['id']}/view")
    assert client.get(f"/api/sets/{created['id']}").json()["view_count"] == 1


# --------------------------------------------------------------------------- #
# Zapis postępu po każdym elemencie (PATCH /api/study/sessions/{id})
# --------------------------------------------------------------------------- #
def _start(client, set_id, mode="flashcards", total=1, score=0):
    response = client.post(
        "/api/study/sessions", json={"set_id": set_id, "mode": mode, "score": score, "total": total}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_postep_sesji_rosnie_z_kazdym_elementem(client):
    register(client)
    created = make_set(client)  # 2 fiszki, 1 pytanie
    session_id = _start(client, created["id"])

    response = client.patch(f"/api/study/sessions/{session_id}", json={"score": 1, "total": 2, "duration_seconds": 40})
    assert response.status_code == 200, response.text
    assert (response.json()["total"], response.json()["score"]) == (2, 1)

    # Postęp trafia od razu do rankingu i kalendarza — bez kończenia sesji.
    assert client.get("/api/activity/leaderboard").json()["viewer"]["points"] == 2
    assert client.get("/api/activity/heatmap?weeks=4").json()["total_items"] == 2
    assert len(client.get("/api/study/sessions").json()) == 1


def test_postep_nie_przekracza_liczby_elementow_zestawu(client):
    register(client)
    created = make_set(client)
    flashcards = _start(client, created["id"], "flashcards")
    quiz = _start(client, created["id"], "quiz", total=1, score=1)

    assert client.patch(f"/api/study/sessions/{flashcards}", json={"score": 0, "total": 3}).status_code == 422
    assert client.patch(f"/api/study/sessions/{quiz}", json={"score": 1, "total": 2}).status_code == 422
    assert client.patch(f"/api/study/sessions/{quiz}", json={"score": 2, "total": 1}).status_code == 422


def test_spozniony_zapis_nie_odbiera_punktow(client):
    """Starsze żądanie dotarłe po nowszym nie może zmniejszyć liczby przerobionych elementów."""
    register(client)
    created = make_set(client)
    session_id = _start(client, created["id"])

    client.patch(f"/api/study/sessions/{session_id}", json={"score": 2, "total": 2, "duration_seconds": 30})
    stale = client.patch(f"/api/study/sessions/{session_id}", json={"score": 1, "total": 1, "duration_seconds": 10})
    assert stale.status_code == 200
    assert (stale.json()["total"], stale.json()["score"], stale.json()["duration_seconds"]) == (2, 1, 30)


def test_nie_mozna_aktualizowac_cudzej_sesji(client):
    register(client, "autor", "HasloAutora123")
    created = make_set(client, visibility="public")
    session_id = _start(client, created["id"])
    client.post("/api/auth/logout")

    register(client, "obcy", "HasloObcego1234")
    response = client.patch(f"/api/study/sessions/{session_id}", json={"score": 0, "total": 2})
    assert response.status_code == 404
    assert client.patch("/api/study/sessions/999999", json={"score": 0, "total": 1}).status_code == 404


def test_stara_sesja_jest_zamknieta_dla_zmian(client):
    from datetime import timedelta

    from app.database import session_scope
    from app.models import StudySession, utcnow

    register(client)
    created = make_set(client)
    session_id = _start(client, created["id"])
    with session_scope() as db:
        db.get(StudySession, session_id).created_at = utcnow() - timedelta(hours=25)

    response = client.patch(f"/api/study/sessions/{session_id}", json={"score": 0, "total": 2})
    assert response.status_code == 409
