"""Definicja trybu generatora promptu i reguły wspólne dla wszystkich trybów.

Tryb to „przepis” nakładany na uniwersalny prompt składany w przeglądarce
(``static/js/prompt_generator.js``). Rdzeń promptu — opis formatu JSON,
rygor merytoryczny, format odpowiedzi — pozostaje wspólny; tryb podmienia
rolę modelu, domyślne źródła i przykład, dokłada własne zasady oraz sekcję
wymagań. Treść trybów żyje po stronie serwera, więc trafia do przeglądarki
wyłącznie wtedy, gdy konto ma odpowiednie uprawnienie.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..permissions import Permission

# Silnik quizu obsługuje wyłącznie pytania zamknięte. Każdy tryb dziedzinowy
# zawęża je dodatkowo do formatu „single best answer” z czterema wariantami.
OPTIONS_PER_QUESTION = 4

CLOSED_QUESTION_RULES = (
    "### Pytania — wyłącznie zamknięte, format ABCD",
    "",
    f"- Każde pytanie to pytanie zamknięte jednokrotnego wyboru: dokładnie {OPTIONS_PER_QUESTION} warianty",
    "  odpowiedzi (A–D) i dokładnie jeden wariant z `is_correct: true`.",
    "- Nie twórz pytań otwartych, uzupełnianek, pytań typu prawda/fałsz, dopasowywania par",
    "  ani pytań wielokrotnego wyboru — aplikacja ich nie obsługuje.",
    "- Nie stosuj wariantów złożonych („A i B”, „1, 2 i 4”), „wszystkie powyższe”",
    "  ani „żadne z powyższych”.",
    "- Pozycja poprawnej odpowiedzi ma być zróżnicowana w obrębie zestawu — nie umieszczaj",
    "  jej stale na tym samym miejscu.",
)


@dataclass(frozen=True)
class SourceTextSpec:
    """Opis pola na tekst źródłowy wklejany bezpośrednio do generatora."""

    label: str
    placeholder: str
    heading: str
    intro: str
    min_chars: int = 200


@dataclass(frozen=True)
class PromptMode:
    """Tryb generatora promptu przypisany do uprawnienia.

    Pola tekstowe są listami wierszy, a nie jednym napisem — łatwiej je
    stroić, porównywać w przeglądzie zmian i testować wybiórczo.
    """

    key: str
    label: str
    summary: str
    permission: Permission
    # Akapit „# ROLA” — kim ma być model.
    role: tuple[str, ...]
    # Wymagania trybu wstawiane jako osobna sekcja po zasadach budowy treści.
    instructions: tuple[str, ...]
    # Domyślne źródła, gdy użytkownik wybierze „wiedzę podręcznikową”.
    sources: tuple[str, ...]
    # Dodatkowe zasady rygoru: (nagłówek, *wiersze opisu).
    rigor: tuple[tuple[str, ...], ...]
    example: dict[str, Any]
    example_caption: str
    # Wartości startowe pól formularza (klucze jak w komponencie JS).
    defaults: dict[str, Any] = field(default_factory=dict)
    source_text: SourceTextSpec | None = None
    # Nazwa rangi pokazywana przy trybie oraz grupa w menu „Dodaj zestaw”.
    badge: str = ""
    group: str = "Tryby dziedzinowe"

    @property
    def instructions_text(self) -> str:
        return "\n".join(self.instructions)

    def to_client(self) -> dict[str, Any]:
        """Postać przekazywana do komponentu generatora (klucze zgodne z JS)."""
        material = None
        if self.source_text is not None:
            material = {
                "etykieta": self.source_text.label,
                "podpowiedz": self.source_text.placeholder,
                "naglowek": self.source_text.heading,
                "wstep": self.source_text.intro,
                "minZnakow": self.source_text.min_chars,
            }
        return {
            "klucz": self.key,
            "etykieta": self.label,
            "opis": self.summary,
            "odznaka": self.badge,
            "grupa": self.group,
            "rola": list(self.role),
            "instrukcje": self.instructions_text,
            "zrodla": list(self.sources),
            "rygor": [list(rule) for rule in self.rigor],
            "przyklad": self.example,
            "podpisPrzykladu": self.example_caption,
            "ustawienia": dict(self.defaults),
            "material": material,
            # Format ABCD jest stały: generator blokuje przełącznik wielokrotnego wyboru.
            "jednokrotnyWybor": True,
        }
