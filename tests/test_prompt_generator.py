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


def _odkoduj_js(tekst: str) -> str:
    """Zdejmuje jeden poziom znaków ucieczki języka JavaScript.

    W kodzie źródłowym sekwencja ``\\n`` opisuje znak ucieczki JSON-a, a nie znak
    nowego wiersza, więc przed ``json.loads`` trzeba ją sprowadzić do ``\n``.
    """
    return re.sub(r"\\(.)", lambda m: m.group(1) if m.group(1) in "\"'\\" else "\\" + m.group(1), tekst)


PROFILE_Z_PRZYKLADEM = ["ogolny", "medycyna", "jezyki"]


def _przyklady(kod: str) -> dict[str, dict]:
    """Skleja przykładowe obiekty JSON rozbite w kodzie na listy wierszy."""
    fragment = kod[kod.index("const PRZYKLADY") : kod.index("const PROFILE")]
    wyniki: dict[str, dict] = {}

    for nazwa in PROFILE_Z_PRZYKLADEM:
        poczatek = fragment.index(f"{nazwa}: {{")
        koniec = fragment.index("tresc: [", poczatek)
        blok = fragment[koniec:]
        blok = blok[: blok.index("\n      ],")]

        wiersze = [wiersz for _cudzyslow, wiersz in re.findall(r'^\s*(["\'])(.*?)\1,\s*$', blok, re.M)]
        wyniki[nazwa] = json.loads(_odkoduj_js("\n".join(wiersze)))

    return wyniki


@pytest.mark.parametrize("profil", PROFILE_Z_PRZYKLADEM)
def test_przyklad_z_promptu_przechodzi_import_bez_uwag(kod, normalise, profil: str):
    przyklad = _przyklady(kod)[profil]
    result = normalise(przyklad)

    assert result.ok is True, [issue.message for issue in result.issues]
    assert [issue for issue in result.issues if issue.severity == "warning"] == []
    assert result.stats["cards"] == len(przyklad["cards"])
    assert result.stats["questions"] == len(przyklad["questions"])


@pytest.mark.parametrize("profil", PROFILE_Z_PRZYKLADEM)
def test_przyklad_uzywa_wylacznie_pol_ze_specyfikacji(kod, profil: str):
    przyklad = _przyklady(kod)[profil]

    assert set(przyklad) <= {"title", "description", "subject", "tags", "visibility", "cards", "questions"}
    for karta in przyklad["cards"]:
        assert set(karta) <= {"front", "back", "hint", "note"}
    for pytanie in przyklad["questions"]:
        assert set(pytanie) <= {"prompt", "explanation", "options"}
        # Pole `multiple` wylicza aplikacja — prompt nie może uczyć modela go podawać.
        assert "multiple" not in pytanie
        for wariant in pytanie["options"]:
            assert set(wariant) <= {"text", "is_correct", "feedback"}


@pytest.mark.parametrize("profil", PROFILE_Z_PRZYKLADEM)
def test_przyklad_ma_dokladnie_jedna_poprawna_odpowiedz(kod, profil: str):
    przyklad = _przyklady(kod)[profil]

    for pytanie in przyklad["questions"]:
        poprawne = [wariant for wariant in pytanie["options"] if wariant["is_correct"]]
        assert len(poprawne) == 1, pytanie["prompt"]
        assert len(pytanie["options"]) == 4, pytanie["prompt"]


def test_przyklad_jezykowy_nie_zdradza_odpowiedzi_na_awersie(kod):
    """Fiszka do nauki języka ma mieć na awersie sam termin, bez tłumaczenia."""
    przyklad = _przyklady(kod)["jezyki"]
    karta = przyklad["cards"][0]

    assert "\n" not in karta["front"]
    assert len(karta["front"].split()) <= 3
    assert "\n" in karta["back"]


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
    assert "Nie łącz faktów w nowe wnioski." in fragment
    assert "Brak informacji jest lepszy niż informacja nieprawdziwa." in fragment
    # Zasady bazowe nie mogą być przypisane do jednej dziedziny.
    for slowo in ("dawek", "pacjent", "medyczn", "klinicz"):
        assert slowo not in fragment.lower(), slowo


def test_rola_w_prompcie_jest_niezalezna_od_dziedziny(kod):
    """Nagłówek promptu nie może zakładać konkretnej dyscypliny."""
    fragment = kod[kod.index("get promptTekst()") : kod.index("get dlugoscPromptu()")]

    assert "Jesteś doświadczonym dydaktykiem i redaktorem materiałów do nauki." in fragment
    assert "dziedzinaDoPromptu" in fragment
    for slowo in ("medyczn", "lekarz", "pacjent"):
        assert slowo not in fragment.lower(), slowo


def test_wariant_wlasnych_materialow_zabrania_wiedzy_spoza_zrodla(kod):
    fragment = kod[kod.index("get sekcjaZrodel()") : kod.index("get sekcjaRygoru()")]

    assert "WYŁĄCZNIE na treści dołączonych materiałów" in fragment
    assert "Nie uzupełniaj luk wiedzą własną" in fragment
    # Wariant podręcznikowy korzysta z listy przypisanej do profilu.
    assert "aktywnyProfil.zrodla" in fragment
    assert "wlasneZrodla" in fragment


def test_kazdy_profil_ma_zrodla_i_przyklad(kod):
    """Każdy profil dziedziny musi dostarczać listę źródeł i wskazywać istniejący przykład."""
    fragment = kod[kod.index("const PROFILE") : kod.index("const POZIOMY")]
    klucze = re.findall(r"^    ([a-z]+): \{$", fragment, re.M)

    assert set(klucze) == {"ogolny", "scisle", "medycyna", "prawo", "it", "jezyki", "humanistyka"}
    for klucz in klucze:
        blok = fragment[fragment.index(f"    {klucz}: {{") :]
        blok = blok[: blok.index("\n    },")]
        assert "etykieta:" in blok, klucz
        assert "zrodla: [" in blok, klucz
        przyklad = re.search(r'przyklad: "([a-z]+)"', blok)
        assert przyklad is not None, klucz
        assert przyklad.group(1) in PROFILE_Z_PRZYKLADEM, klucz


def test_profile_pozamedyczne_nie_powolują_sie_na_zrodla_medyczne(kod):
    """Lista źródeł profilu medycznego nie może wyciekać do innych dziedzin."""
    fragment = kod[kod.index("const PROFILE") : kod.index("const POZIOMY")]

    for klucz in ("prawo", "it", "jezyki", "humanistyka", "scisle", "ogolny"):
        blok = fragment[fragment.index(f"    {klucz}: {{") :]
        blok = blok[: blok.index("\n    },")]
        for pozycja in ("Bochenek", "Szczeklik", "Robbins", "Kostowski"):
            assert pozycja not in blok, f"{klucz}: {pozycja}"

    # Profil medyczny nadal wskazuje konkretne pozycje.
    blok_med = fragment[fragment.index("    medycyna: {") :]
    blok_med = blok_med[: blok_med.index("\n    },")]
    for pozycja in ("Bochenek", "Terminologia Anatomica", "Szczeklika", "Robbins"):
        assert pozycja in blok_med, pozycja


def test_poziomy_odbiorcy_nie_sa_przypisane_do_medycyny(kod):
    fragment = kod[kod.index("const POZIOMY") : kod.index("const JEZYKI")]

    assert set(re.findall(r"^    ([a-z]+): \{$", fragment, re.M)) == {
        "wprowadzenie",
        "studia",
        "egzamin",
        "ekspercki",
        "slownictwo",
    }
    for slowo in ("medyczn", "klinicz", "LEK", "pacjent"):
        assert slowo not in fragment, slowo


def test_szablony_obejmuja_rozne_dziedziny(kod):
    """Szablony startowe mają pokazywać, że narzędzie nie jest narzędziem medycznym."""
    fragment = kod[kod.index("const SZABLONY") : kod.index("function promptGenerator")]
    profile = re.findall(r'profil: "([a-z]+)"', fragment)

    assert len(profile) >= 6
    assert len(set(profile)) >= 4
    for oczekiwany in ("prawo", "it", "jezyki", "humanistyka"):
        assert oczekiwany in profile, oczekiwany


def test_prompt_wymaga_czystego_json_na_wyjsciu(kod):
    fragment = kod[kod.index("get sekcjaFormatu()") : kod.index("get promptTekst()")]

    assert "WYŁĄCZNIE obiektem JSON" in fragment
    assert "LISTA KONTROLNA" in fragment
    assert "UTF-8" in fragment
