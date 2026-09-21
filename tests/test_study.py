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
