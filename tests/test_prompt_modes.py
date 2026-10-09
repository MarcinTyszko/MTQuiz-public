"""Testy dziedzinowych trybów generatora promptu (LEK, anatomia, synteza).

Tryby żyją po stronie serwera (``app/prompts``) i trafiają do przeglądarki
wyłącznie dla kont z odpowiednią rangą. Przykłady zawarte w trybach uczą model
formatu, więc muszą przechodzić rzeczywisty import bez żadnych uwag.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from conftest import register, unlock_admin

MEDICAL_KEYS = ["lek", "anatomia", "synteza"]
GENERATOR_JS = Path(__file__).resolve().parent.parent / "app" / "static" / "js" / "prompt_generator.js"


@pytest.fixture()
def modes(app_module):
    from app.prompts import all_modes

    return {mode.key: mode for mode in all_modes()}


def _grant(app_module, username: str, role: str) -> None:
    from fastapi.testclient import TestClient

    with TestClient(app_module.app) as admin:
        unlock_admin(admin)
        users = admin.get(f"/api/admin/users?q={username}").json()
        user_id = next(item["id"] for item in users if item["username"] == username)
        assert admin.patch(f"/api/admin/users/{user_id}", json={"role": role}).status_code == 200


def _generator_config(html: str) -> dict:
    match = re.search(r'<script type="application/json" id="konfiguracja-generatora">(.*?)</script>', html, re.S)
    assert match, "Brak bloku konfiguracji generatora"
    return json.loads(match.group(1))


# --------------------------------------------------------------------------- #
# Treść trybów
# --------------------------------------------------------------------------- #
def test_rejestr_zawiera_tryby_medyczne(modes):
    assert list(modes) == MEDICAL_KEYS
    for mode in modes.values():
        assert mode.permission.value == "prompts.medical"
        assert mode.group == "Tryby medyczne"


@pytest.mark.parametrize("key", MEDICAL_KEYS)
def test_przyklad_trybu_przechodzi_import_bez_uwag(app_module, modes, key):
    from app.importer import normalise_payload

    example = modes[key].example
    result = normalise_payload(example)

    assert result.ok is True, [issue.message for issue in result.issues]
    assert [issue for issue in result.issues if issue.severity == "warning"] == []
    assert result.stats["questions"] == len(example["questions"]) >= 1


@pytest.mark.parametrize("key", MEDICAL_KEYS)
def test_przyklad_trybu_to_pytania_abcd_z_jedna_odpowiedzia(modes, key):
    example = modes[key].example

    assert set(example) <= {"title", "description", "subject", "tags", "visibility", "cards", "questions"}
    for question in example["questions"]:
        assert set(question) <= {"prompt", "explanation", "options"}
        assert len(question["options"]) == 4, question["prompt"]
        assert sum(option["is_correct"] for option in question["options"]) == 1, question["prompt"]
        for option in question["options"]:
            assert set(option) <= {"text", "is_correct", "feedback"}
            assert not re.match(r"^[A-D][).]\s", option["text"]), "Wariant nie może mieć prefiksu litery"


def test_poprawne_odpowiedzi_w_przykladach_sa_na_roznych_pozycjach(modes):
    """Model wzoruje się na przykładach — stała pozycja poprawnej odpowiedzi uczyłaby go wzorca."""
    positions = set()
    for mode in modes.values():
        for question in mode.example["questions"]:
            positions.add(next(i for i, option in enumerate(question["options"]) if option["is_correct"]))
    assert len(positions) >= 3


@pytest.mark.parametrize("key", MEDICAL_KEYS)
def test_tryb_wymusza_wylacznie_pytania_zamkniete(modes, key):
    from app.prompts.base import CLOSED_QUESTION_RULES

    mode = modes[key]
    text = mode.instructions_text

    for line in CLOSED_QUESTION_RULES:
        assert line in text
    assert "dokładnie 4 warianty" in text
    assert "Nie twórz pytań otwartych" in text
    # Tryb nie może przywracać wielokrotnego wyboru, który generator dopuszcza w trybie standardowym.
    assert "Zaznacz wszystkie prawidłowe" not in text
    assert mode.to_client()["jednokrotnyWybor"] is True


def test_tryb_lek_wymaga_winiet_i_uzasadnien(modes):
    text = modes["lek"].instructions_text
    role = " ".join(modes["lek"].role)

    assert "Lekarskiego Egzaminu Końcowego" in role
    assert "winietę kliniczną" in text
    assert '"explanation"' in text and "Zapamiętaj:" in text
    assert '"feedback" przy każdym dystraktorze' in text
    assert any("Szczeklik" in source for source in modes["lek"].sources)


def test_tryb_anatomii_obejmuje_osie_wiedzy(modes):
    text = modes["anatomia"].instructions_text
    for axis in ("Położenie i rzut", "Topografia i relacje", "Unaczynienie", "Unerwienie", "Znaczenie kliniczne"):
        assert axis in text, axis
    assert "Terminologia Anatomica" in text


def test_tryb_syntezy_wymaga_tekstu_i_mnemotechnik(modes):
    mode = modes["synteza"]
    text = mode.instructions_text

    assert mode.source_text is not None
    assert mode.defaults["zrodlo"] == "wlasne"
    assert "high-yield" in text
    assert "Mnemotechnika:" in text
    assert '"description"' in text
    # Przykład pokazuje mnemotechnikę dokładnie w formie opisanej w instrukcji: pełna w notatce
    # na rewersie, a we wskazówce na awersie wyłącznie klucz bez odpowiedzi.
    card = mode.example["cards"][0]
    assert card["note"].startswith("Mnemotechnika:")
    assert "Mnemotechnika" not in card["hint"]
    for answer_part in ("10", "9", "7", "II", "IX"):
        assert answer_part not in card["hint"].replace("1972", ""), answer_part


@pytest.mark.parametrize("key", MEDICAL_KEYS)
def test_wskazowka_w_przykladzie_nie_zdradza_odpowiedzi(modes, key):
    """Pole hint widać na awersie — nie może zawierać rozkodowanej mnemotechniki ani odpowiedzi."""
    for card in modes[key].example["cards"]:
        hint = card.get("hint") or ""
        assert not hint.startswith("Mnemotechnika:"), key
        assert card["back"].lower() not in hint.lower(), key


def test_postac_dla_przegladarki_jest_serializowalna(modes):
    for mode in modes.values():
        payload = mode.to_client()
        assert json.loads(json.dumps(payload, ensure_ascii=False)) == payload
        assert payload["instrukcje"].startswith("## WYMAGANIA TRYBU")
        assert payload["rola"] and payload["zrodla"] and payload["rygor"]


# --------------------------------------------------------------------------- #
# Kontrola dostępu — API
# --------------------------------------------------------------------------- #
def test_zwykly_uzytkownik_nie_widzi_trybow(client):
    register(client)
    assert client.get("/api/prompts/modes").json() == []
    response = client.get("/api/prompts/modes/lek")
    assert response.status_code == 403
    assert "Student medycyny" in response.json()["detail"]


def test_student_medycyny_widzi_tryby(client, app_module):
    register(client, "kasia")
    _grant(app_module, "kasia", "medical_student")

    listed = client.get("/api/prompts/modes").json()
    assert [mode["klucz"] for mode in listed] == MEDICAL_KEYS
    assert client.get("/api/prompts/modes/anatomia").json()["etykieta"] == "Anatomia"
    assert client.get("/api/prompts/modes/nieznany").status_code == 404


def test_administrator_widzi_tryby(app_module):
    from fastapi.testclient import TestClient

    with TestClient(app_module.app) as admin:
        unlock_admin(admin)
        assert len(admin.get("/api/prompts/modes").json()) == len(MEDICAL_KEYS)


def test_gosc_nie_ma_dostepu_do_trybow(client):
    assert client.get("/api/prompts/modes").status_code == 401


# --------------------------------------------------------------------------- #
# Kontrola dostępu — widoki HTML
# --------------------------------------------------------------------------- #
def test_generator_bez_rangi_nie_zawiera_tresci_trybow(client):
    register(client)
    page = client.get("/generator-promptu")
    config = _generator_config(page.text)

    assert config == {"tryby": [], "startowy": None, "odrzucony": None}
    # Treść promptów medycznych nie może trafić do przeglądarki nawet w ukryciu.
    assert "WYMAGANIA TRYBU" not in page.text
    assert "/generator-promptu?tryb=" not in page.text


def test_link_do_trybu_bez_rangi_jest_odrzucany(client):
    register(client)
    config = _generator_config(client.get("/generator-promptu?tryb=lek").text)

    assert config["tryby"] == []
    assert config["startowy"] is None
    assert config["odrzucony"] == {"etykieta": "LEK i egzaminy kliniczne", "odznaka": "Student medycyny"}


def test_generator_studenta_otwiera_wskazany_tryb(client, app_module):
    register(client, "kasia")
    _grant(app_module, "kasia", "medical_student")

    config = _generator_config(client.get("/generator-promptu?tryb=synteza").text)
    assert [mode["klucz"] for mode in config["tryby"]] == MEDICAL_KEYS
    assert config["startowy"] == "synteza"
    assert config["odrzucony"] is None

    # Nieznany tryb w adresie nie psuje strony.
    config = _generator_config(client.get("/generator-promptu?tryb=xyz").text)
    assert config["startowy"] is None and config["odrzucony"] is None


def test_menu_dodaj_zestaw_pokazuje_tryby_tylko_z_ranga(client, app_module):
    register(client, "kasia")
    before = client.get("/pulpit").text
    assert "Tryby medyczne" not in before

    _grant(app_module, "kasia", "medical_student")
    after = client.get("/pulpit").text
    assert "Tryby medyczne" in after
    for key in MEDICAL_KEYS:
        assert f'href="/generator-promptu?tryb={key}"' in after


# --------------------------------------------------------------------------- #
# Integracja z komponentem generatora
# --------------------------------------------------------------------------- #
def test_generator_nie_zawiera_tresci_trybow_na_sztywno():
    """Treść trybów pochodzi z serwera — plik JS zawiera tylko mechanizm."""
    code = GENERATOR_JS.read_text(encoding="utf-8")

    assert 'readJsonScript("konfiguracja-generatora")' in code
    for phrase in ("Lekarskiego Egzaminu", "Terminologia Anatomica — nazewnictwo", "Mnemotechnika:", "WYMAGANIA TRYBU"):
        assert phrase not in code, phrase


def test_generator_wlacza_sekcje_trybu_do_promptu():
    code = GENERATOR_JS.read_text(encoding="utf-8")
    prompt = code[code.index("get promptTekst()") : code.index("get dlugoscPromptu()")]

    assert "this.sekcjaTrybu" in prompt
    assert "this.sekcjaFragmentu" in prompt
    # Rygor dziedzinowy trybu zastępuje rygor profilu, a nie się z nim dubluje.
    rigor = code[code.index("get sekcjaRygoru()") : code.index("get sekcjaTresci()")]
    assert "this.trybAktywny ? this.trybAktywny.rygor : this.aktywnyProfil.rygor" in rigor
