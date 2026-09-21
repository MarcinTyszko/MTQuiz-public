"""Testy zarządzania zestawami, widoczności, ulubionych i klonowania."""
from __future__ import annotations

import copy

from conftest import SAMPLE_SET, register


def create_set(client, payload=None):
    response = client.post("/api/sets", json=payload or SAMPLE_SET)
    assert response.status_code == 201, response.text
    return response.json()


def test_tworzenie_zestawu_zapisuje_pelna_tresc(client):
    register(client)
    created = create_set(client)

    assert created["title"] == SAMPLE_SET["title"]
    assert created["cards_count"] == 2
    assert created["questions_count"] == 1
    assert created["tags"] == ["Farmakologia", "Układ krążenia"]
    assert created["cards"][0]["position"] == 0
    assert created["questions"][0]["multiple"] is False
    assert [option["is_correct"] for option in created["questions"][0]["options"]] == [False, True, False, False]


def test_zestaw_bez_tresci_jest_odrzucany(client):
    register(client)
    payload = {"title": "Pusty", "cards": [], "questions": []}
    assert client.post("/api/sets", json=payload).status_code == 422


def test_pytanie_bez_poprawnej_odpowiedzi_jest_odrzucane(client):
    register(client)
    payload = copy.deepcopy(SAMPLE_SET)
    for option in payload["questions"][0]["options"]:
        option["is_correct"] = False
    assert client.post("/api/sets", json=payload).status_code == 422


def test_wielokrotny_wybor_jest_wykrywany_automatycznie(client):
    register(client)
    payload = copy.deepcopy(SAMPLE_SET)
    payload["questions"][0]["options"][0]["is_correct"] = True
    created = create_set(client, payload)
    assert created["questions"][0]["multiple"] is True


def test_aktualizacja_zachowuje_identyfikatory_istniejacych_fiszek(client):
    register(client)
    created = create_set(client)
    first_card_id = created["cards"][0]["id"]

    payload = copy.deepcopy(SAMPLE_SET)
    payload["cards"] = [
        {"id": first_card_id, "front": "Zmieniony awers", "back": "Zmieniony rewers"},
        {"front": "Zupełnie nowa fiszka", "back": "Nowa treść"},
    ]
    updated = client.put(f"/api/sets/{created['id']}", json=payload)
    assert updated.status_code == 200, updated.text
    data = updated.json()

    assert data["cards_count"] == 2
    assert data["cards"][0]["id"] == first_card_id
    assert data["cards"][0]["front"] == "Zmieniony awers"
    assert data["cards"][1]["id"] != first_card_id


def test_prywatny_zestaw_jest_niewidoczny_dla_innych(client):
    register(client, "autor", "HasloAutora123")
    created = create_set(client)
    client.post("/api/auth/logout")

    register(client, "obcy", "HasloObcego123")
    assert client.get(f"/api/sets/{created['id']}").status_code == 403
    assert client.get("/api/public/sets").json() == []


def test_publiczny_zestaw_trafia_do_bazy_publicznej_i_da_sie_sklonowac(client):
    register(client, "autor", "HasloAutora123")
    payload = copy.deepcopy(SAMPLE_SET)
    payload["visibility"] = "public"
    created = create_set(client, payload)
    client.post("/api/auth/logout")

    register(client, "student2", "HasloStudenta123")
    feed = client.get("/api/public/sets").json()
    assert [item["id"] for item in feed] == [created["id"]]

    clone = client.post(f"/api/sets/{created['id']}/fork")
    assert clone.status_code == 201, clone.text
    cloned = clone.json()

    assert cloned["id"] != created["id"]
    assert cloned["visibility"] == "private"
    assert cloned["forked_from_id"] == created["id"]
    assert cloned["cards_count"] == created["cards_count"]
    assert cloned["questions_count"] == created["questions_count"]
    assert cloned["is_owner"] is True

    # Kopia jest niezależna — edycja nie zmienia oryginału.
    mine = client.get("/api/sets").json()
    assert [item["id"] for item in mine] == [cloned["id"]]


def test_nie_mozna_sklonowac_wlasnego_zestawu(client):
    register(client)
    payload = copy.deepcopy(SAMPLE_SET)
    payload["visibility"] = "public"
    created = create_set(client, payload)
    assert client.post(f"/api/sets/{created['id']}/fork").status_code == 400


def test_ulubione_sa_przypinane_do_biblioteki(client):
    register(client, "autor", "HasloAutora123")
    payload = copy.deepcopy(SAMPLE_SET)
    payload["visibility"] = "public"
    created = create_set(client, payload)
    client.post("/api/auth/logout")

    register(client, "czytelnik", "HasloCzytelnika1")
    assert client.post(f"/api/sets/{created['id']}/favorite").status_code == 200
    favorites = client.get("/api/sets/favorites").json()
    assert [item["id"] for item in favorites] == [created["id"]]
    assert favorites[0]["is_favorite"] is True

    # Ponowne dodanie nie tworzy duplikatu.
    client.post(f"/api/sets/{created['id']}/favorite")
    assert len(client.get("/api/sets/favorites").json()) == 1

    client.delete(f"/api/sets/{created['id']}/favorite")
    assert client.get("/api/sets/favorites").json() == []


def test_oznaczanie_trudnych_fiszek_dziala_per_uzytkownik(client):
    register(client, "autor", "HasloAutora123")
    payload = copy.deepcopy(SAMPLE_SET)
    payload["visibility"] = "public"
    created = create_set(client, payload)
    card_id = created["cards"][0]["id"]

    assert client.post(f"/api/cards/{card_id}/star").json()["ok"] is True
    assert client.get(f"/api/sets/{created['id']}").json()["cards"][0]["starred"] is True
    assert client.post(f"/api/cards/{card_id}/star").json()["ok"] is False

    client.post(f"/api/cards/{card_id}/star")
    client.post("/api/auth/logout")
    register(client, "inny", "HasloInnego123")
    assert client.get(f"/api/sets/{created['id']}").json()["cards"][0]["starred"] is False


def test_wyszukiwanie_i_sortowanie_bazy_publicznej(client):
    register(client, "autor", "HasloAutora123")
    for title, subject in [("Anatomia klatki", "Anatomia"), ("Beta-blokery", "Farmakologia")]:
        payload = copy.deepcopy(SAMPLE_SET)
        payload["title"] = title
        payload["subject"] = subject
        payload["visibility"] = "public"
        create_set(client, payload)

    assert [item["title"] for item in client.get("/api/public/sets?q=beta").json()] == ["Beta-blokery"]
    alpha = [item["title"] for item in client.get("/api/public/sets?sort=alpha").json()]
    assert alpha == ["Anatomia klatki", "Beta-blokery"]
    # Oba zestawy dzielą ten sam tag; domyślne sortowanie to „najnowsze”.
    assert {item["title"] for item in client.get("/api/public/sets?tag=Farmakologia").json()} == {
        "Anatomia klatki",
        "Beta-blokery",
    }
    assert client.get("/api/public/sets?tag=Nieistniejacy").json() == []
    assert {tag["name"] for tag in client.get("/api/public/tags").json()} == {"Farmakologia", "Układ krążenia"}


def test_usuwanie_zestawu_wymaga_wlasciciela(client):
    register(client, "autor", "HasloAutora123")
    payload = copy.deepcopy(SAMPLE_SET)
    payload["visibility"] = "public"
    created = create_set(client, payload)
    client.post("/api/auth/logout")

    register(client, "napastnik", "HasloNapastnika1")
    assert client.delete(f"/api/sets/{created['id']}").status_code == 403
    assert client.put(f"/api/sets/{created['id']}", json=SAMPLE_SET).status_code == 403

    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"username": "autor", "password": "HasloAutora123"})
    assert client.delete(f"/api/sets/{created['id']}").status_code == 200
    assert client.get(f"/api/sets/{created['id']}").status_code == 404


def test_eksport_zwraca_kanoniczny_json(client):
    register(client)
    created = create_set(client)
    response = client.get(f"/api/sets/{created['id']}/export")

    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    data = response.json()
    assert data["schema"] == "medfiszki/study-set"
    assert len(data["cards"]) == 2
    assert data["questions"][0]["options"][1]["is_correct"] is True
