"""Testy uniwersalnego parsera pakietów JSON (odporność na warianty formatu)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture()
def normalise(app_module):
    from app.importer import normalise_payload

    return normalise_payload


def test_format_kanoniczny_przechodzi_bez_uwag(normalise):
    payload = {
        "title": "Anatomia",
        "description": "Opis",
        "subject": "Anatomia",
        "tags": ["Kości", "Kości", "Stawy"],
        "cards": [{"front": "Kość udowa", "back": "Najdłuższa kość ciała"}],
        "questions": [
            {
                "prompt": "Która kość jest najdłuższa?",
                "options": [
                    {"text": "Udowa", "is_correct": True},
                    {"text": "Piszczelowa", "is_correct": False},
                ],
            }
        ],
    }
    result = normalise(payload)

    assert result.ok is True
    assert result.payload.title == "Anatomia"
    # Duplikat taga zostaje usunięty.
    assert result.payload.tags == ["Kości", "Stawy"]
    assert result.stats == {
        "cards": 1,
        "questions": 1,
        "cards_skipped": 0,
        "questions_skipped": 0,
        "warnings": 0,
        "errors": 0,
    }


def test_polskie_nazwy_pol_sa_rozpoznawane(normalise):
    payload = {
        "tytul": "Fizjologia nerek",
        "opis": "Wchłanianie zwrotne",
        "przedmiot": "Fizjologia",
        "tagi": "Nerki, Gospodarka wodna",
        "fiszki": [{"przod": "GFR", "tyl": "Przesączanie kłębuszkowe"}],
        "pytania": [
            {
                "pytanie": "Gdzie wchłania się większość sodu?",
                "odpowiedzi": ["Kanalik proksymalny", "Pętla Henlego"],
                "poprawna": "A",
                "wyjasnienie": "Około 65% sodu wchłania się w kanaliku bliższym.",
            }
        ],
    }
    result = normalise(payload)

    assert result.ok is True
    assert result.payload.title == "Fizjologia nerek"
    assert result.payload.subject == "Fizjologia"
    assert result.payload.tags == ["Nerki", "Gospodarka wodna"]
    assert result.payload.cards[0].front == "GFR"
    question = result.payload.questions[0]
    assert [option.is_correct for option in question.options] == [True, False]
    assert question.explanation.startswith("Około 65%")


def test_odpowiedzi_jako_litera_indeks_i_tresc(normalise):
    base = {"title": "T", "questions": []}

    variants = [
        ({"prompt": "P", "options": ["A1", "B1", "C1"], "correct_answer": "C"}, 2),
        ({"prompt": "P", "options": ["A1", "B1", "C1"], "answer": 1}, 1),
        ({"prompt": "P", "options": ["A1", "B1", "C1"], "answer": "B1"}, 1),
        ({"prompt": "P", "options": {"A": "A1", "B": "B1"}, "key": "B"}, 1),
        ({"prompt": "P", "options": ["A) pierwsza", "B) druga"], "correct": "b"}, 1),
    ]
    for question, expected_index in variants:
        result = normalise({**base, "questions": [question]})
        assert result.ok is True, result.issues
        options = result.payload.questions[0].options
        correct = [index for index, option in enumerate(options) if option.is_correct]
        assert correct == [expected_index], question


def test_indeks_liczony_od_jedynki_jest_korygowany_z_ostrzezeniem(normalise):
    result = normalise(
        {"title": "T", "questions": [{"prompt": "P", "options": ["A1", "B1"], "answer": 2}]}
    )
    assert result.ok is True
    assert result.payload.questions[0].options[1].is_correct is True
    assert any("od 1" in issue.message for issue in result.issues if issue.severity == "warning")


def test_prefiks_literowy_jest_usuwany_z_tresci_wariantu(normalise):
    result = normalise(
        {"title": "T", "questions": [{"prompt": "P", "options": ["A) Pierwsza", "B) Druga"], "correct": "A"}]}
    )
    assert [option.text for option in result.payload.questions[0].options] == ["Pierwsza", "Druga"]


def test_blok_markdown_i_przecinek_wiszacy_sa_tolerowane(normalise):
    raw = """Oto wygenerowany pakiet:

```json
{
  "title": "Biochemia",
  "cards": [
    { "front": "ATP", "back": "Adenozyno-5'-trifosforan" },
  ]
}
```
"""
    result = normalise(raw)
    assert result.ok is True
    assert result.payload.cards[0].front == "ATP"


def test_niepoprawny_json_zwraca_czytelny_blad(normalise):
    result = normalise("{ to nie jest JSON")
    assert result.ok is False
    assert result.issues[0].severity == "error"
    assert "JSON" in result.issues[0].message


def test_pusta_zawartosc_jest_bledem_krytycznym(normalise):
    result = normalise({"title": "Pusty zestaw", "cards": [], "questions": []})
    assert result.ok is False
    assert any(issue.severity == "error" for issue in result.issues)


def test_uszkodzone_elementy_sa_pomijane_a_reszta_importowana(normalise):
    payload = {
        "title": "Mieszany pakiet",
        "cards": [
            {"front": "Poprawna", "back": "Treść"},
            {"front": "Bez rewersu"},
            {"back": "Bez awersu"},
            "To jest tekst bez separatora",
            12345,
        ],
        "questions": [
            {"prompt": "Bez wariantów"},
            {"prompt": "Jeden wariant", "options": ["Tylko ten"], "correct": "A"},
            {"prompt": "Bez wskazania", "options": ["A1", "B1"]},
            {"prompt": "Dobre pytanie", "options": ["A1", "B1"], "correct": "B"},
        ],
    }
    result = normalise(payload)

    assert result.ok is True
    assert result.stats["cards"] == 1
    assert result.stats["cards_skipped"] == 4
    assert result.stats["questions"] == 1
    assert result.stats["questions_skipped"] == 3
    assert result.stats["warnings"] >= 7


def test_lista_fiszek_na_najwyzszym_poziomie(normalise):
    result = normalise([{"term": "Serce", "definition": "Narząd mięśniowy"}])
    assert result.ok is True
    assert result.payload.title == "Zaimportowany zestaw"
    assert result.payload.cards[0].back == "Narząd mięśniowy"


def test_koperta_z_kluczem_set_jest_rozpakowywana(normalise):
    result = normalise({"data": {"title": "Wewnętrzny", "cards": [{"front": "A", "back": "B"}]}})
    assert result.ok is True
    assert result.payload.title == "Wewnętrzny"


def test_wielokrotny_wybor_jest_zachowany(normalise):
    result = normalise(
        {
            "title": "T",
            "questions": [
                {
                    "prompt": "Które nerwy przechodzą przez otwór szyjny?",
                    "options": ["IX", "X", "XI", "XII"],
                    "correct": ["A", "B", "C"],
                }
            ],
        }
    )
    question = result.payload.questions[0]
    assert question.multiple is True
    assert [option.is_correct for option in question.options] == [True, True, True, False]


def test_widocznosc_z_pliku_i_nadpisanie_parametrem(normalise, app_module):
    from app.models import Visibility

    payload = {"title": "T", "visibility": "public", "cards": [{"front": "A", "back": "B"}]}
    assert normalise(payload).payload.visibility == Visibility.PUBLIC
    assert normalise(payload, default_visibility=Visibility.PRIVATE).payload.visibility == Visibility.PRIVATE


def test_przykladowy_pakiet_dostarczony_z_aplikacja_jest_poprawny(normalise):
    path = Path(__file__).resolve().parent.parent / "app" / "data" / "przyklad_nerwy_czaszkowe.json"
    result = normalise(json.loads(path.read_text(encoding="utf-8")))

    assert result.ok is True
    assert [issue for issue in result.issues if issue.severity == "warning"] == []
    assert result.stats["cards"] >= 12
    assert result.stats["questions"] >= 5
    assert all(any(option.is_correct for option in question.options) for question in result.payload.questions)


def test_przyklad_ze_specyfikacji_ai_schema_jest_importowalny(normalise):
    """Gwarantuje, że dokumentacja dla modeli językowych nie rozjedzie się z parserem."""
    import re

    spec = (Path(__file__).resolve().parent.parent / "AI_SCHEMA.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```json\n(.*?)\n```", spec, re.S)
    payloads = [json.loads(block) for block in blocks]

    example = next(item for item in payloads if item.get("schema") == "mtquiz/study-set")
    result = normalise(example)

    assert result.ok is True
    assert [issue for issue in result.issues if issue.severity == "warning"] == []
    assert result.stats["cards"] == len(example["cards"])
    assert result.stats["questions"] == len(example["questions"])
