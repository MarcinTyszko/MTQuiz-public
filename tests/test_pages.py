"""Testy widoków HTML: dostępność stron, przekierowania i kontrola uprawnień."""
from __future__ import annotations

import copy

from conftest import SAMPLE_SET, register, unlock_admin


def test_strona_glowna_dla_gosci(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Baza publiczna" in response.text


def test_logowanie_przekierowuje_na_pulpit(client):
    register(client)
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/pulpit"

    dashboard = client.get("/pulpit")
    assert dashboard.status_code == 200
    assert "Moje zestawy" in dashboard.text


def test_strony_chronione_przekierowuja_gosci_do_logowania(client):
    for path in ("/pulpit", "/zestawy/nowy", "/zestawy/import", "/konto", "/panel"):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 303, path
        assert response.headers["location"].startswith("/logowanie?next="), path


def test_konto_z_wymuszona_zmiana_hasla_trafia_na_formularz(client):
    client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    response = client.get("/pulpit", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/zmiana-hasla"

    form = client.get("/zmiana-hasla")
    assert form.status_code == 200
    assert "Wymagana zmiana hasła" in form.text


def test_panel_administratora_jest_niedostepny_dla_uzytkownika(client):
    register(client)
    response = client.get("/panel")
    assert response.status_code == 403
    assert "Brak dostępu" in response.text


def test_widoki_zestawu_i_trybow_nauki(client):
    register(client)
    created = client.post("/api/sets", json=SAMPLE_SET).json()

    detail = client.get(f"/zestawy/{created['id']}")
    assert detail.status_code == 200
    assert SAMPLE_SET["title"] in detail.text
    assert "Ucz się fiszkami" in detail.text

    assert client.get(f"/zestawy/{created['id']}/fiszki").status_code == 200
    assert client.get(f"/zestawy/{created['id']}/quiz").status_code == 200
    assert client.get(f"/zestawy/{created['id']}/edycja").status_code == 200


def test_tryb_quizu_bez_pytan_zwraca_404(client):
    register(client)
    payload = copy.deepcopy(SAMPLE_SET)
    payload["questions"] = []
    created = client.post("/api/sets", json=payload).json()

    response = client.get(f"/zestawy/{created['id']}/quiz")
    assert response.status_code == 404
    assert "pytań quizowych" in response.text


def test_nieistniejaca_strona_zwraca_przyjazny_blad(client):
    response = client.get("/nie-ma-takiej-strony")
    assert response.status_code == 404
    assert "Nie znaleziono strony" in response.text


def test_panel_administratora_dla_admina(client):
    unlock_admin(client)
    response = client.get("/panel")
    assert response.status_code == 200
    assert "Panel administratora" in response.text
    assert "Kopie zapasowe" in response.text


def test_zasoby_statyczne_i_sonda_zdrowia(client):
    assert client.get("/healthz").json()["status"] == "ok"
    assert client.get("/static/js/app.js").status_code == 200
    assert client.get("/static/favicon.svg").status_code == 200


def test_zasoby_statyczne_maja_sygnature_wersji(client):
    """Sygnatura w adresie wymusza pobranie nowych plików po aktualizacji."""
    html = client.get("/logowanie").text
    assert "/static/css/app.css?v=" in html
    assert "/static/js/auth.js?v=" in html


def test_api_zwraca_json_zamiast_html_dla_bledow(client):
    response = client.get("/api/sets", headers={"Accept": "application/json"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Wymagane zalogowanie."


def test_generator_promptu_wymaga_zalogowania(client):
    response = client.get("/generator-promptu", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/logowanie?next=")


def test_generator_promptu_renderuje_sie_dla_uzytkownika(client):
    register(client)
    response = client.get("/generator-promptu")

    assert response.status_code == 200
    assert "Generator promptu AI" in response.text
    # Komponent i jego skrypt muszą być podpięte.
    assert 'x-data="promptGenerator()"' in response.text
    assert "/static/js/prompt_generator.js?v=" in response.text
    # Zakładki dla poszczególnych dostawców modeli.
    for dostawca in ("Claude CLI", "ChatGPT", "Gemini"):
        assert dostawca in response.text


def test_nawigacja_prowadzi_do_generatora_promptu(client):
    register(client)
    assert '/generator-promptu' in client.get("/pulpit").text


def test_strona_importu_odsyla_do_generatora(client):
    register(client)
    assert "/generator-promptu" in client.get("/zestawy/import").text
