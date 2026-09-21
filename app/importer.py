"""Uniwersalny, odporny na błędy parser pakietów nauki w formacie JSON.

Moduł przyjmuje dane wygenerowane przez modele językowe (np. Claude CLI),
normalizuje nazewnictwo pól (obsługa wariantów polskich i angielskich),
naprawia typowe drobne usterki i zwraca kanoniczny obiekt ``StudySetCreate``
razem z listą czytelnych komunikatów dla użytkownika.

Zasada działania:
  * ``error``   -> problem blokujący import (np. brak tytułu, niepoprawny JSON),
  * ``warning`` -> element pominięty lub automatycznie poprawiony; import trwa.
"""
from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from pydantic import ValidationError

from .config import settings
from .models import Visibility
from .schemas import (
    AnswerOptionIn,
    FlashcardIn,
    ImportIssue,
    ImportPreview,
    QuestionIn,
    StudySetCreate,
)

# --------------------------------------------------------------------------- #
# Słowniki aliasów pól
# --------------------------------------------------------------------------- #
SET_TITLE_KEYS = ("title", "name", "tytul", "nazwa", "set_title", "settitle")
SET_DESCRIPTION_KEYS = ("description", "desc", "summary", "opis", "streszczenie")
SET_SUBJECT_KEYS = ("subject", "topic", "course", "przedmiot", "temat", "dziedzina")
SET_TAGS_KEYS = ("tags", "tag", "keywords", "tagi", "slowa_kluczowe", "labels")
SET_VISIBILITY_KEYS = ("visibility", "widocznosc", "access", "dostep")
SET_CARDS_KEYS = ("cards", "flashcards", "fiszki", "karty", "terms")
SET_QUESTIONS_KEYS = ("questions", "quiz", "quizzes", "pytania", "mcq", "mcqs", "test")
SET_WRAPPER_KEYS = ("set", "study_set", "studyset", "data", "payload", "zestaw", "deck")

CARD_FRONT_KEYS = ("front", "term", "question", "prompt", "przod", "pojecie", "pytanie", "haslo", "awers")
CARD_BACK_KEYS = ("back", "definition", "answer", "tyl", "definicja", "odpowiedz", "rewers", "tresc")
CARD_HINT_KEYS = ("hint", "clue", "wskazowka", "podpowiedz")
CARD_NOTE_KEYS = ("note", "notes", "context", "clinical_context", "notatka", "uwagi", "kontekst")

Q_PROMPT_KEYS = ("prompt", "question", "stem", "text", "pytanie", "tresc", "title")
Q_OPTIONS_KEYS = ("options", "answers", "choices", "odpowiedzi", "opcje", "warianty", "distractors")
Q_EXPLANATION_KEYS = ("explanation", "rationale", "why", "wyjasnienie", "uzasadnienie", "komentarz")
Q_CORRECT_KEYS = (
    "correct",
    "correct_answer",
    "correct_answers",
    "correctanswer",
    "correctanswers",
    "answer",
    "answers",
    "answer_key",
    "answerkey",
    "key",
    "solution",
    "poprawna",
    "poprawne",
    "poprawna_odpowiedz",
    "prawidlowa",
)
Q_MULTIPLE_KEYS = ("multiple", "multi", "multiselect", "multiple_correct", "wielokrotny", "wielokrotnego_wyboru")

OPT_TEXT_KEYS = ("text", "label", "answer", "option", "content", "value", "tresc", "odpowiedz", "opcja")
OPT_CORRECT_KEYS = ("is_correct", "iscorrect", "correct", "right", "valid", "poprawna", "prawidlowa")
OPT_FEEDBACK_KEYS = ("feedback", "why", "rationale", "explanation", "komentarz", "wyjasnienie")
OPT_LETTER_KEYS = ("letter", "key", "id", "label", "litera", "oznaczenie")

TRUE_WORDS = {"true", "1", "yes", "y", "tak", "t", "prawda", "correct", "poprawna", "on"}
FALSE_WORDS = {"false", "0", "no", "n", "nie", "falsz", "fałsz", "incorrect", "off", ""}

_FENCE_RE = re.compile(r"^\s*```[a-zA-Z0-9_-]*\s*|\s*```\s*$")
_LETTER_RE = re.compile(r"^\(?\s*([A-Ha-h])\s*[\).\:\-]?\s*$")
_LEADING_LETTER_RE = re.compile(r"^\(?\s*([A-Ha-h])\s*[\).\:]\s+")


class ImportError_(Exception):
    """Błąd krytyczny parsera (np. niepoprawna składnia JSON)."""


# --------------------------------------------------------------------------- #
# Narzędzia pomocnicze
# --------------------------------------------------------------------------- #
def _normalise_key(key: Any) -> str:
    """Sprowadza nazwę klucza do postaci porównywalnej (bez znaków diakrytycznych)."""
    text = str(key).strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[\s\-]+", "_", text)


def _index(mapping: dict[str, Any]) -> dict[str, Any]:
    """Buduje mapę znormalizowany_klucz -> wartość."""
    return {_normalise_key(key): value for key, value in mapping.items()}


def _pick(indexed: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in indexed and indexed[key] is not None:
            return indexed[key]
    return None


def _as_text(value: Any) -> str:
    """Zamienia dowolną wartość na tekst, spłaszczając listy i obiekty."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, bool):
        return "tak" if value else "nie"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "\n".join(part for part in (_as_text(item) for item in value) if part)
    if isinstance(value, dict):
        indexed = _index(value)
        for key in ("text", "value", "content", "tresc"):
            if key in indexed:
                return _as_text(indexed[key])
        return "\n".join(f"{key}: {_as_text(val)}" for key, val in value.items())
    return str(value).strip()


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        token = value.strip().lower()
        if token in TRUE_WORDS:
            return True
        if token in FALSE_WORDS:
            return False
    return default


def _strip_leading_letter(text: str) -> str:
    """Usuwa prefiks „A) ” z treści odpowiedzi, jeśli model go dopisał."""
    return _LEADING_LETTER_RE.sub("", text, count=1).strip() or text


def _letter_to_index(token: str) -> int | None:
    match = _LETTER_RE.match(token)
    if match:
        return ord(match.group(1).upper()) - ord("A")
    return None


def strip_code_fences(text: str) -> str:
    """Usuwa otoczkę ```json ... ``` typową dla odpowiedzi modeli językowych."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].lstrip().startswith("```"):
            lines = lines[1:]
        while lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return _FENCE_RE.sub("", cleaned).strip()


def _extract_json_block(text: str) -> str:
    """Wyłuskuje pierwszy kompletny obiekt/tablicę JSON z tekstu z komentarzem."""
    start_candidates = [pos for pos in (text.find("{"), text.find("[")) if pos != -1]
    if not start_candidates:
        return text
    start = min(start_candidates)
    opening = text[start]
    closing = "}" if opening == "{" else "]"
    depth = 0
    in_string = False
    escape = False
    for pos in range(start, len(text)):
        char = text[pos]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return text[start : pos + 1]
    return text[start:]


def parse_json_text(raw: str) -> Any:
    """Parsuje tekst JSON, tolerując bloki kodu, BOM i końcowe przecinki."""
    if not raw or not raw.strip():
        raise ImportError_("Plik jest pusty — nie znaleziono żadnych danych JSON.")

    candidate = raw.lstrip("﻿")
    candidate = strip_code_fences(candidate)

    attempts = [candidate, _extract_json_block(candidate)]
    # Ostatnia szansa: usunięcie przecinków wiszących przed nawiasem zamykającym.
    attempts.append(re.sub(r",(\s*[}\]])", r"\1", attempts[-1]))

    last_error: json.JSONDecodeError | None = None
    for attempt in attempts:
        if not attempt.strip():
            continue
        try:
            return json.loads(attempt)
        except json.JSONDecodeError as exc:
            last_error = exc

    assert last_error is not None
    raise ImportError_(
        f"Niepoprawna składnia JSON (wiersz {last_error.lineno}, znak {last_error.colno}): {last_error.msg}."
    )


# --------------------------------------------------------------------------- #
# Normalizacja elementów
# --------------------------------------------------------------------------- #
class _Collector:
    def __init__(self) -> None:
        self.issues: list[ImportIssue] = []

    def error(self, path: str, message: str) -> None:
        self.issues.append(ImportIssue(severity="error", path=path, message=message))

    def warn(self, path: str, message: str) -> None:
        self.issues.append(ImportIssue(severity="warning", path=path, message=message))

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == "error" for issue in self.issues)


def _normalise_card(raw: Any, path: str, collector: _Collector) -> FlashcardIn | None:
    if isinstance(raw, str):
        # Wariant „Pojęcie — definicja” w jednej linii.
        for separator in ("\t", " — ", " – ", " - ", "::", ";"):
            if separator in raw:
                front, back = raw.split(separator, 1)
                if front.strip() and back.strip():
                    collector.warn(path, "Fiszkę odczytano z pojedynczego tekstu rozdzielonego separatorem.")
                    return FlashcardIn(front=front.strip(), back=back.strip())
        collector.warn(path, "Pominięto fiszkę: tekst nie zawiera rozdzielenia na przód i tył.")
        return None

    if isinstance(raw, (list, tuple)) and len(raw) >= 2:
        collector.warn(path, "Fiszkę odczytano z tablicy [przód, tył].")
        raw = {"front": raw[0], "back": raw[1]}

    if not isinstance(raw, dict):
        collector.warn(path, "Pominięto fiszkę: oczekiwano obiektu z polami „front” i „back”.")
        return None

    indexed = _index(raw)
    front = _as_text(_pick(indexed, CARD_FRONT_KEYS))
    back = _as_text(_pick(indexed, CARD_BACK_KEYS))
    hint = _as_text(_pick(indexed, CARD_HINT_KEYS)) or None
    note = _as_text(_pick(indexed, CARD_NOTE_KEYS)) or None

    if not front and not back:
        collector.warn(path, "Pominięto pustą fiszkę.")
        return None
    if not front:
        collector.warn(path, "Pominięto fiszkę: brak treści awersu (pole „front”).")
        return None
    if not back:
        collector.warn(path, "Pominięto fiszkę: brak treści rewersu (pole „back”).")
        return None

    try:
        return FlashcardIn(front=front, back=back, hint=hint, note=note)
    except ValidationError as exc:
        collector.warn(path, f"Pominięto fiszkę: {_first_error(exc)}")
        return None


def _normalise_options(raw: Any, path: str, collector: _Collector) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Zwraca listę opcji w postaci słownikowej oraz mapę litera -> indeks."""
    options: list[dict[str, Any]] = []
    letters: dict[str, int] = {}

    if isinstance(raw, dict):
        # Postać {"A": "...", "B": "..."} lub {"A": {"text": ..., "correct": true}}
        items = list(raw.items())
        # Sortowanie po literze, by zachować kolejność A, B, C, D.
        items.sort(key=lambda pair: str(pair[0]).strip().upper())
        for key, value in items:
            entry = _option_entry(value, f"{path}[{key}]", collector)
            if entry is None:
                continue
            entry.pop("_letter", None)
            letter = str(key).strip().upper()[:1]
            if letter:
                letters[letter] = len(options)
            options.append(entry)
        return options, letters

    if not isinstance(raw, (list, tuple)):
        return options, letters

    for position, value in enumerate(raw):
        entry = _option_entry(value, f"{path}[{position}]", collector)
        if entry is None:
            continue
        letter = entry.pop("_letter", None)
        if letter:
            letters[str(letter).strip().upper()[:1]] = len(options)
        else:
            letters.setdefault(chr(ord("A") + len(options)), len(options))
        options.append(entry)
    return options, letters


def _option_entry(value: Any, path: str, collector: _Collector) -> dict[str, Any] | None:
    if isinstance(value, str):
        text = _strip_leading_letter(value.strip())
        if not text:
            return None
        return {"text": text, "is_correct": False, "feedback": None}

    if isinstance(value, (int, float, bool)):
        return {"text": _as_text(value), "is_correct": False, "feedback": None}

    if not isinstance(value, dict):
        collector.warn(path, "Pominięto wariant odpowiedzi o nieobsługiwanym typie.")
        return None

    indexed = _index(value)
    text = _as_text(_pick(indexed, OPT_TEXT_KEYS))
    if not text:
        # Obiekt typu {"A": "treść"} zagnieżdżony w liście.
        single = [(key, val) for key, val in value.items() if isinstance(val, str)]
        if len(single) == 1:
            letter, content = single[0]
            return {
                "text": _strip_leading_letter(content.strip()),
                "is_correct": False,
                "feedback": None,
                "_letter": letter,
            }
        collector.warn(path, "Pominięto wariant odpowiedzi bez treści.")
        return None

    entry: dict[str, Any] = {
        "text": _strip_leading_letter(text),
        "is_correct": _as_bool(_pick(indexed, OPT_CORRECT_KEYS), default=False),
        "feedback": _as_text(_pick(indexed, OPT_FEEDBACK_KEYS)) or None,
    }
    letter = _pick(indexed, OPT_LETTER_KEYS)
    if isinstance(letter, str) and _LETTER_RE.match(letter):
        entry["_letter"] = letter
    return entry


def _apply_correct_markers(
    options: list[dict[str, Any]],
    letters: dict[str, int],
    marker: Any,
    path: str,
    collector: _Collector,
) -> None:
    """Nanosi informację o poprawnych odpowiedziach z osobnego pola (litera/indeks/treść)."""
    if marker is None:
        return

    markers = marker if isinstance(marker, (list, tuple, set)) else [marker]
    texts = {option["text"].strip().casefold(): idx for idx, option in enumerate(options)}

    for token in markers:
        if isinstance(token, bool):
            continue
        if isinstance(token, (int, float)) and not isinstance(token, bool):
            index = int(token)
            if 0 <= index < len(options):
                options[index]["is_correct"] = True
                continue
            # Model użył numeracji od 1 — korygujemy i informujemy.
            if 1 <= index <= len(options):
                options[index - 1]["is_correct"] = True
                collector.warn(path, "Indeks poprawnej odpowiedzi liczony od 1 — skorygowano automatycznie.")
                continue
            collector.warn(path, f"Wskazanie poprawnej odpowiedzi „{index}” jest poza zakresem wariantów.")
            continue

        token_text = _as_text(token)
        if not token_text:
            continue

        letter_index = _letter_to_index(token_text)
        if letter_index is not None:
            mapped = letters.get(token_text.strip().upper()[:1], letter_index)
            if 0 <= mapped < len(options):
                options[mapped]["is_correct"] = True
                continue
            collector.warn(path, f"Wskazana litera „{token_text}” nie odpowiada żadnemu wariantowi.")
            continue

        match = texts.get(_strip_leading_letter(token_text).strip().casefold())
        if match is not None:
            options[match]["is_correct"] = True
            continue

        collector.warn(path, f"Nie udało się dopasować poprawnej odpowiedzi „{token_text}” do wariantów.")


def _normalise_question(raw: Any, path: str, collector: _Collector) -> QuestionIn | None:
    if not isinstance(raw, dict):
        collector.warn(path, "Pominięto pytanie: oczekiwano obiektu JSON.")
        return None

    indexed = _index(raw)
    prompt = _as_text(_pick(indexed, Q_PROMPT_KEYS))
    if not prompt:
        collector.warn(path, "Pominięto pytanie: brak treści polecenia.")
        return None

    raw_options = _pick(indexed, Q_OPTIONS_KEYS)
    if raw_options is None:
        collector.warn(path, f"Pominięto pytanie „{prompt[:60]}”: brak listy wariantów odpowiedzi.")
        return None

    options, letters = _normalise_options(raw_options, f"{path}.options", collector)
    if len(options) < 2:
        collector.warn(path, f"Pominięto pytanie „{prompt[:60]}”: wymagane są co najmniej dwa warianty.")
        return None
    if len(options) > 10:
        collector.warn(path, "Pytanie miało ponad 10 wariantów — zachowano pierwsze 10.")
        options = options[:10]

    _apply_correct_markers(options, letters, _pick(indexed, Q_CORRECT_KEYS), path, collector)

    correct_count = sum(1 for option in options if option["is_correct"])
    if correct_count == 0:
        collector.warn(path, f"Pominięto pytanie „{prompt[:60]}”: nie wskazano poprawnej odpowiedzi.")
        return None

    declared_multiple = _pick(indexed, Q_MULTIPLE_KEYS)
    if declared_multiple is not None and _as_bool(declared_multiple) and correct_count == 1:
        collector.warn(path, "Pytanie oznaczono jako wielokrotnego wyboru, ale ma jedną poprawną odpowiedź.")

    explanation = _as_text(_pick(indexed, Q_EXPLANATION_KEYS)) or None

    try:
        return QuestionIn(
            prompt=prompt,
            explanation=explanation,
            options=[AnswerOptionIn(**option) for option in options],
        )
    except ValidationError as exc:
        collector.warn(path, f"Pominięto pytanie: {_first_error(exc)}")
        return None


def _first_error(exc: ValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "nieznany błąd walidacji"
    first = errors[0]
    location = ".".join(str(part) for part in first.get("loc", ()))
    message = first.get("msg", "błąd walidacji")
    return f"{location}: {message}" if location else message


def _looks_like_question(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    indexed = _index(item)
    return any(key in indexed for key in Q_OPTIONS_KEYS)


# --------------------------------------------------------------------------- #
# Główne wejście modułu
# --------------------------------------------------------------------------- #
def normalise_payload(raw: Any, *, default_visibility: Visibility | None = None) -> ImportPreview:
    """Przetwarza surowe dane na kanoniczny ``StudySetCreate`` z listą uwag."""
    collector = _Collector()

    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError:
            return ImportPreview(
                ok=False,
                issues=[
                    ImportIssue(
                        severity="error",
                        path="$",
                        message="Plik nie jest zapisany w kodowaniu UTF-8.",
                    )
                ],
            )

    if isinstance(raw, str):
        try:
            raw = parse_json_text(raw)
        except ImportError_ as exc:
            return ImportPreview(ok=False, issues=[ImportIssue(severity="error", path="$", message=str(exc))])

    # Rozpakowanie typowych kopert: {"set": {...}} lub {"data": {...}}.
    if isinstance(raw, dict):
        indexed = _index(raw)
        wrapper = _pick(indexed, SET_WRAPPER_KEYS)
        if isinstance(wrapper, dict) and not any(key in indexed for key in SET_TITLE_KEYS):
            collector.warn("$", "Dane rozpakowano z obiektu nadrzędnego.")
            raw = wrapper
        elif isinstance(wrapper, list) and wrapper and isinstance(wrapper[0], dict):
            candidate = wrapper[0]
            if any(_normalise_key(key) in SET_TITLE_KEYS for key in candidate):
                collector.warn("$", "Plik zawiera listę zestawów — zaimportowano pierwszy z nich.")
                raw = candidate

    cards_raw: Any = []
    questions_raw: Any = []
    meta: dict[str, Any] = {}

    if isinstance(raw, list):
        collector.warn("$", "Plik zawiera samą listę elementów — nadano domyślny tytuł zestawu.")
        questions_raw = [item for item in raw if _looks_like_question(item)]
        cards_raw = [item for item in raw if not _looks_like_question(item)]
    elif isinstance(raw, dict):
        meta = _index(raw)
        cards_raw = _pick(meta, SET_CARDS_KEYS) or []
        questions_raw = _pick(meta, SET_QUESTIONS_KEYS) or []
        if isinstance(questions_raw, dict):
            questions_raw = _pick(_index(questions_raw), SET_QUESTIONS_KEYS) or list(questions_raw.values())
    else:
        return ImportPreview(
            ok=False,
            issues=[
                ImportIssue(
                    severity="error",
                    path="$",
                    message="Oczekiwano obiektu JSON opisującego zestaw nauki.",
                )
            ],
        )

    if not isinstance(cards_raw, list):
        collector.warn("$.cards", "Pole z fiszkami nie jest listą — zignorowano.")
        cards_raw = []
    if not isinstance(questions_raw, list):
        collector.warn("$.questions", "Pole z pytaniami nie jest listą — zignorowano.")
        questions_raw = []

    if len(cards_raw) > settings.max_cards_per_set:
        collector.warn("$.cards", f"Ograniczono liczbę fiszek do {settings.max_cards_per_set}.")
        cards_raw = cards_raw[: settings.max_cards_per_set]
    if len(questions_raw) > settings.max_questions_per_set:
        collector.warn("$.questions", f"Ograniczono liczbę pytań do {settings.max_questions_per_set}.")
        questions_raw = questions_raw[: settings.max_questions_per_set]

    cards: list[FlashcardIn] = []
    for position, item in enumerate(cards_raw):
        card = _normalise_card(item, f"$.cards[{position}]", collector)
        if card is not None:
            cards.append(card)

    questions: list[QuestionIn] = []
    for position, item in enumerate(questions_raw):
        question = _normalise_question(item, f"$.questions[{position}]", collector)
        if question is not None:
            questions.append(question)

    title = _as_text(_pick(meta, SET_TITLE_KEYS)) if meta else ""
    if not title:
        title = "Zaimportowany zestaw"
        collector.warn("$.title", "Brak tytułu w pliku — nadano tytuł domyślny „Zaimportowany zestaw”.")
    title = title[:200]

    description = _as_text(_pick(meta, SET_DESCRIPTION_KEYS)) if meta else ""
    subject = _as_text(_pick(meta, SET_SUBJECT_KEYS)) if meta else ""
    tags_value = _pick(meta, SET_TAGS_KEYS) if meta else None

    visibility = default_visibility or Visibility.PRIVATE
    raw_visibility = _as_text(_pick(meta, SET_VISIBILITY_KEYS)).lower() if meta else ""
    if default_visibility is None and raw_visibility:
        if raw_visibility in {"public", "publiczny", "publiczna", "open"}:
            visibility = Visibility.PUBLIC
        elif raw_visibility in {"private", "prywatny", "prywatna"}:
            visibility = Visibility.PRIVATE
        else:
            collector.warn("$.visibility", f"Nieznana wartość widoczności „{raw_visibility}” — ustawiono prywatną.")

    if not cards and not questions:
        collector.error("$", "Nie znaleziono ani jednej poprawnej fiszki ani pytania quizowego.")

    stats = {
        "cards": len(cards),
        "questions": len(questions),
        "cards_skipped": max(0, len(cards_raw) - len(cards)),
        "questions_skipped": max(0, len(questions_raw) - len(questions)),
        "warnings": sum(1 for issue in collector.issues if issue.severity == "warning"),
        "errors": sum(1 for issue in collector.issues if issue.severity == "error"),
    }

    if collector.has_errors:
        return ImportPreview(ok=False, issues=collector.issues, payload=None, stats=stats)

    try:
        payload = StudySetCreate(
            title=title,
            description=description[:5000],
            subject=subject[:120],
            visibility=visibility,
            tags=tags_value or [],
            cards=cards,
            questions=questions,
        )
    except ValidationError as exc:
        collector.error("$", f"Nie udało się zbudować zestawu: {_first_error(exc)}")
        return ImportPreview(ok=False, issues=collector.issues, payload=None, stats=stats)

    return ImportPreview(ok=True, issues=collector.issues, payload=payload, stats=stats)


def export_payload(study_set: Any) -> dict[str, Any]:
    """Serializuje zestaw do kanonicznego formatu wymiany JSON."""
    return {
        "schema": "medfiszki/study-set",
        "version": 1,
        "title": study_set.title,
        "description": study_set.description,
        "subject": study_set.subject,
        "tags": study_set.tags,
        "visibility": study_set.visibility.value,
        "cards": [
            {
                "front": card.front,
                "back": card.back,
                **({"hint": card.hint} if card.hint else {}),
                **({"note": card.note} if card.note else {}),
            }
            for card in sorted(study_set.cards, key=lambda item: item.position)
        ],
        "questions": [
            {
                "prompt": question.prompt,
                **({"explanation": question.explanation} if question.explanation else {}),
                "multiple": question.multiple,
                "options": [
                    {
                        "text": option.text,
                        "is_correct": option.is_correct,
                        **({"feedback": option.feedback} if option.feedback else {}),
                    }
                    for option in sorted(question.options, key=lambda item: item.position)
                ],
            }
            for question in sorted(study_set.questions, key=lambda item: item.position)
        ],
    }
