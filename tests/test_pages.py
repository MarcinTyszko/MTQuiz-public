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


def test_stopka_zawiera_note_o_prawach_autorskich(client):
    from datetime import datetime, timezone

    html = client.get("/logowanie").text
    rok = datetime.now(timezone.utc).year

    assert f"© {rok} Marcin Tyszko" in html
    assert "Wszelkie prawa zastrzeżone" in html
    assert "licencji MIT" in html


def test_menu_grupuje_trzy_drogi_tworzenia_zestawu(client):
    """Edytor, generator promptu i import mają być w jednym menu, nie osobno w pasku."""
    register(client)
    html = client.get("/pulpit").text

    assert "Dodaj zestaw" in html
    for etykieta in ("Edytor ręczny", "Generator promptu AI", "Import pliku JSON"):
        assert etykieta in html, etykieta
    for sciezka in ("/zestawy/nowy", "/generator-promptu", "/zestawy/import"):
        assert sciezka in html, sciezka

    # Dawne, rozsypane pozycje paska nie mogą wrócić.
    assert ">Import AI<" not in html
    assert ">Prompt AI<" not in html


def test_opis_aplikacji_nie_zaweza_jej_do_medycyny(client):
    """Strona powitalna ma przedstawiać narzędzie jako ogólne, nie medyczne."""
    html = client.get("/").text

    assert "dowolnego przedmiotu" in html or "dowolnego przedmiotu" in html.lower()
    for fraza in ("kierunków medycznych", "anatomię, farmakologię"):
        assert fraza not in html, fraza


def test_strona_transkrypcji_wymaga_zalogowania(client):
    response = client.get("/transkrypcje", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/logowanie?next=")


def test_strona_transkrypcji_renderuje_sie(client):
    register(client)
    response = client.get("/transkrypcje")

    assert response.status_code == 200
    assert "Transkrypcja AI" in response.text
    assert 'x-data="listaTranskrypcji()"' in response.text
    # Proces liczący startuje razem z aplikacją — strona podpowiada docker compose, nie ręczną instalację.
    assert "docker compose up -d --build" in response.text
    assert "docker compose restart transkrypcja" in response.text


def test_strona_wyniku_transkrypcji(client):
    import io

    register(client)
    utworzone = client.post(
        "/api/transkrypcje",
        files={"file": ("wyklad.mp3", io.BytesIO(b"dane" * 64), "audio/mpeg")},
        data={"title": "Wykład testowy", "language": "pl"},
    ).json()

    response = client.get(f"/transkrypcje/{utworzone['id']}")
    assert response.status_code == 200
    assert "Wykład testowy" in response.text
    assert 'x-data="szczegolyTranskrypcji()"' in response.text
    assert 'id="dane-transkrypcji"' in response.text


def test_cudza_transkrypcja_zwraca_404(client):
    import io

    register(client, "autor", "HasloAutora123")
    utworzone = client.post(
        "/api/transkrypcje",
        files={"file": ("wyklad.mp3", io.BytesIO(b"dane" * 64), "audio/mpeg")},
        data={"title": "Prywatne", "language": "pl"},
    ).json()
    client.post("/api/auth/logout")

    register(client, "obcy", "HasloObcego1234")
    assert client.get(f"/transkrypcje/{utworzone['id']}").status_code == 404


def test_nawigacja_zawiera_transkrypcje(client):
    register(client)
    html = client.get("/pulpit").text
    assert "/transkrypcje" in html
    assert "Transkrypcja nagrania" in html
