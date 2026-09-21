"""Testy materiałów testowych z katalogu `przyklady/`.

Pilnują, aby dołączone pakiety pozostawały zgodne z parserem importu —
w tym plik celowo zniekształcony, na którym demonstrujemy odporność silnika.
"""
from __future__ import annotations

from pathlib import Path

import pytest

KATALOG = Path(__file__).resolve().parent.parent / "przyklady"

PAKIETY_POPRAWNE = [
    ("01-kosci-lacina-polski-angielski.json", 38, 6),
    ("02-miesnie-lacina-polski-angielski.json", 32, 5),
    ("03-narzady-wewnetrzne-lacina-polski-angielski.json", 35, 6),
    ("04-mianownictwo-kierunki-i-plaszczyzny.json", 38, 5),
]


@pytest.fixture()
def normalise(app_module):
    from app.importer import normalise_payload

    return normalise_payload


@pytest.mark.parametrize(("nazwa", "fiszki", "pytania"), PAKIETY_POPRAWNE)
def test_pakiet_importuje_sie_bez_uwag(normalise, nazwa: str, fiszki: int, pytania: int):
    result = normalise((KATALOG / nazwa).read_text(encoding="utf-8"))

    assert result.ok is True, [issue.message for issue in result.issues]
    assert [issue for issue in result.issues if issue.severity == "warning"] == []
    assert result.stats["cards"] == fiszki
    assert result.stats["questions"] == pytania


@pytest.mark.parametrize(("nazwa", "_fiszki", "_pytania"), PAKIETY_POPRAWNE)
def test_kazda_fiszka_podaje_oba_jezyki(normalise, nazwa: str, _fiszki: int, _pytania: int):
    """Rewers każdej fiszki musi zawierać odpowiednik polski i angielski."""
    result = normalise((KATALOG / nazwa).read_text(encoding="utf-8"))

    for card in result.payload.cards:
        assert "polski:" in card.back, card.front
        assert "angielski:" in card.back, card.front
        assert card.hint, card.front


@pytest.mark.parametrize(("nazwa", "_fiszki", "_pytania"), PAKIETY_POPRAWNE)
def test_kazde_pytanie_ma_poprawna_odpowiedz_i_wyjasnienie(normalise, nazwa: str, _fiszki: int, _pytania: int):
    result = normalise((KATALOG / nazwa).read_text(encoding="utf-8"))

    for question in result.payload.questions:
        assert any(option.is_correct for option in question.options), question.prompt
        assert question.explanation, question.prompt
        assert len(question.options) >= 3, question.prompt


def test_plik_zniekształcony_jest_importowany_z_ostrzezeniami(normalise):
    """Plik demonstracyjny musi przejść import, pomijając cztery wadliwe elementy."""
    result = normalise((KATALOG / "05-surowa-odpowiedz-modelu.txt").read_text(encoding="utf-8"))

    assert result.ok is True
    assert result.stats["cards"] == 6
    assert result.stats["questions"] == 3
    assert result.stats["cards_skipped"] == 2
    assert result.stats["questions_skipped"] == 1

    komunikaty = [issue.message for issue in result.issues if issue.severity == "warning"]
    assert any("brak treści rewersu" in message for message in komunikaty)
    assert any("brak treści awersu" in message for message in komunikaty)
    assert any("brak listy wariantów" in message for message in komunikaty)
    assert any("od 1" in message for message in komunikaty)


def test_plik_zniekształcony_poprawnie_rozpoznaje_wskazania_odpowiedzi(normalise):
    """Litera, indeks liczony od 1 oraz lista liter muszą trafić we właściwe warianty."""
    result = normalise((KATALOG / "05-surowa-odpowiedz-modelu.txt").read_text(encoding="utf-8"))
    pytania = result.payload.questions

    assert [option.text for option in pytania[0].options if option.is_correct] == ["Czaszka"]
    assert [option.text for option in pytania[1].options if option.is_correct] == ["Pelvis"]
    assert sorted(option.text for option in pytania[2].options if option.is_correct) == [
        "Abdomen",
        "Pelvis",
        "Thorax",
    ]
    assert pytania[2].multiple is True


def test_katalog_zawiera_opis(normalise):
    opis = (KATALOG / "README.md").read_text(encoding="utf-8")
    for nazwa, _fiszki, _pytania in PAKIETY_POPRAWNE:
        assert nazwa in opis
    assert "05-surowa-odpowiedz-modelu.txt" in opis
