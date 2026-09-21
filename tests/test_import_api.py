"""Testy endpointów importu i eksportu pakietów JSON."""
from __future__ import annotations

import io
import json

from conftest import register

PACKAGE = {
    "tytul": "Mikrobiologia — bakterie Gram-dodatnie",
    "przedmiot": "Mikrobiologia",
    "tagi": ["Mikrobiologia", "Bakteriologia"],
    "fiszki": [
        {"przod": "Staphylococcus aureus — cecha różnicująca", "tyl": "Dodatni test na koagulazę."},
        {"przod": "Streptococcus pyogenes — hemoliza", "tyl": "Hemoliza typu beta."},
    ],
    "pytania": [
        {
            "pytanie": "Który drobnoustrój jest koagulazo-dodatni?",
            "odpowiedzi": ["S. epidermidis", "S. aureus", "S. saprophyticus"],
            "poprawna": "B",
            "wyjasnienie": "Koagulaza odróżnia S. aureus od gronkowców koagulazo-ujemnych.",
        }
    ],
}


def test_walidacja_z_tekstu_zwraca_podglad(client):
    register(client)
    response = client.post("/api/import/validate", json={"data": json.dumps(PACKAGE, ensure_ascii=False)})

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["stats"]["cards"] == 2
    assert body["stats"]["questions"] == 1
    assert body["payload"]["title"] == PACKAGE["tytul"]
    assert body["payload"]["questions"][0]["options"][1]["is_correct"] is True


def test_walidacja_niepoprawnego_pliku_zwraca_bledy(client):
    register(client)
    response = client.post("/api/import/validate", json={"data": "{ zepsute"})

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["payload"] is None
    assert body["issues"][0]["severity"] == "error"


def test_upload_pliku_json(client):
    register(client)
    content = json.dumps(PACKAGE, ensure_ascii=False).encode("utf-8")
    response = client.post(
        "/api/import/upload",
        files={"file": ("pakiet.json", io.BytesIO(content), "application/json")},
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["stats"]["cards"] == 2


def test_commit_tworzy_zestaw_uzytkownika(client):
    register(client)
    response = client.post("/api/import/commit", json={"data": PACKAGE})

    assert response.status_code == 201, response.text
    created = response.json()
    assert created["title"] == PACKAGE["tytul"]
    assert created["cards_count"] == 2
    assert created["visibility"] == "private"
    assert created["is_owner"] is True

    library = client.get("/api/sets").json()
    assert [item["id"] for item in library] == [created["id"]]


def test_commit_niepoprawnych_danych_zwraca_422_z_uwagami(client):
    register(client)
    response = client.post("/api/import/commit", json={"data": {"title": "Pusty"}})

    assert response.status_code == 422
    body = response.json()
    assert body["ok"] is False
    assert any(issue["severity"] == "error" for issue in body["issues"])


def test_pelna_petla_eksport_import(client):
    register(client)
    created = client.post("/api/import/commit", json={"data": PACKAGE}).json()

    exported = client.get(f"/api/sets/{created['id']}/export").json()
    reimported = client.post("/api/import/commit", json={"data": exported})

    assert reimported.status_code == 201
    clone = reimported.json()
    assert clone["cards_count"] == created["cards_count"]
    assert clone["questions_count"] == created["questions_count"]
    assert clone["tags"] == created["tags"]
    assert [option["text"] for option in clone["questions"][0]["options"]] == [
        option["text"] for option in created["questions"][0]["options"]
    ]


def test_import_wymaga_zalogowania(client):
    assert client.post("/api/import/validate", json={"data": PACKAGE}).status_code == 401
