"""Testy generatora promptu dla modeli językowych.

Prompt uczy model formatu wymiany, więc zawarty w nim przykład i opis pól muszą
pozostawać zgodne z rzeczywistym parserem importu.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ZRODLO = Path(__file__).resolve().parent.parent / "app" / "static" / "js" / "prompt_generator.js"


@pytest.fixture(scope="module")
def kod() -> str:
    return ZRODLO.read_text(encoding="utf-8")


@pytest.fixture()
def normalise(app_module):
    from app.importer import normalise_payload

    return normalise_payload


def _przyklad_json(kod: str) -> dict:
    """Skleja przykładowy obiekt JSON rozbity w kodzie na listę wierszy."""
    fragment = kod[kod.index("get sekcjaPrzykladu()") : kod.index("get sekcjaFormatu()")]
    wiersze = re.findall(r'^\s*(["\'])(.*?)\1,\s*$', fragment, re.M)
    tresc = [wiersz for _cudzyslow, wiersz in wiersze]

    poczatek = tresc.index("```json")
    koniec = tresc.index("```", poczatek)
    surowy = "\n".join(tresc[poczatek + 1 : koniec])
    # W kodzie źródłowym cudzysłowy wewnątrz wierszy są poprzedzone ukośnikiem.
    return json.loads(surowy.replace('\\"', '"'))


def test_przyklad_z_promptu_przechodzi_import_bez_uwag(kod, normalise):
    przyklad = _przyklad_json(kod)
    result = normalise(przyklad)

    assert result.ok is True, [issue.message for issue in result.issues]
    assert [issue for issue in result.issues if issue.severity == "warning"] == []
    assert result.stats["cards"] == len(przyklad["cards"])
    assert result.stats["questions"] == len(przyklad["questions"])


def test_przyklad_z_promptu_uzywa_wylacznie_pol_ze_specyfikacji(kod):
    przyklad = _przyklad_json(kod)

    assert set(przyklad) <= {"title", "description", "subject", "tags", "visibility", "cards", "questions"}
    for karta in przyklad["cards"]:
        assert set(karta) <= {"front", "back", "hint", "note"}
    for pytanie in przyklad["questions"]:
        assert set(pytanie) <= {"prompt", "explanation", "options"}
        # Pole `multiple` wylicza aplikacja — prompt nie może uczyć modela go podawać.
        assert "multiple" not in pytanie
        for wariant in pytanie["options"]:
            assert set(wariant) <= {"text", "is_correct", "feedback"}


def test_przyklad_ma_dokladnie_jedna_poprawna_odpowiedz(kod):
    przyklad = _przyklad_json(kod)

    for pytanie in przyklad["questions"]:
        poprawne = [wariant for wariant in pytanie["options"] if wariant["is_correct"]]
        assert len(poprawne) == 1, pytanie["prompt"]
        assert len(pytanie["options"]) == 4, pytanie["prompt"]


def test_opis_schematu_wymienia_wszystkie_pola_formatu(kod):
    """Tabele w prompcie muszą opisywać komplet pól przyjmowanych przez import."""
    fragment = kod[kod.index("get sekcjaSchematu()") : kod.index("get sekcjaPrzykladu()")]

    for pole in ("title", "description", "subject", "tags", "visibility", "cards", "questions"):
        assert f"`{pole}`" in fragment, pole
    for pole in ("front", "back", "hint", "note", "prompt", "explanation", "options", "text", "is_correct", "feedback"):
        assert f"`{pole}`" in fragment, pole
    # Prompt musi jasno mówić, że pola `multiple` się nie podaje.
    assert "multiple" in fragment


def test_prompt_zawiera_zasady_ograniczajace_konfabulacje(kod):
    fragment = kod[kod.index("get sekcjaRygoru()") : kod.index("get sekcjaTresci()")]

    assert "Nie wymyślaj." in fragment
    assert "dawek" in fragment
    assert "Nie łącz faktów w nowe wnioski." in fragment
    assert "Brak informacji jest lepszy niż informacja nieprawdziwa." in fragment


def test_wariant_wlasnych_materialow_zabrania_wiedzy_spoza_zrodla(kod):
    fragment = kod[kod.index("get sekcjaZrodel()") : kod.index("get sekcjaRygoru()")]

    assert "WYŁĄCZNIE na treści dołączonych materiałów" in fragment
    assert "Nie uzupełniaj luk wiedzą własną" in fragment
    # Wariant podręcznikowy wskazuje konkretne pozycje.
    assert "ZRODLA_PODRECZNIKOWE" in fragment


def test_lista_zrodel_podrecznikowych_jest_konkretna(kod):
    fragment = kod[kod.index("const ZRODLA_PODRECZNIKOWE") : kod.index("function promptGenerator")]

    for pozycja in ("Bochenek", "Terminologia Anatomica", "Kostowski", "Szczeklika", "Robbins"):
        assert pozycja in fragment, pozycja


def test_prompt_wymaga_czystego_json_na_wyjsciu(kod):
    fragment = kod[kod.index("get sekcjaFormatu()") : kod.index("get promptTekst()")]

    assert "WYŁĄCZNIE obiektem JSON" in fragment
    assert "LISTA KONTROLNA" in fragment
    assert "UTF-8" in fragment
