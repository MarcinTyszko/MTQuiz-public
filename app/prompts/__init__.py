"""Rejestr trybów generatora promptu.

Nowy zestaw trybów (np. dla prawników) to nowy moduł obok ``medical.py``
i jedna linijka w ``_REGISTRY`` — reszta aplikacji korzysta wyłącznie
z funkcji poniżej.
"""
from __future__ import annotations

from ..models import User
from ..permissions import has_permission
from .base import PromptMode
from .medical import MEDICAL_MODES

_REGISTRY: dict[str, PromptMode] = {mode.key: mode for mode in (*MEDICAL_MODES,)}


def all_modes() -> list[PromptMode]:
    return list(_REGISTRY.values())


def get_mode(key: str) -> PromptMode | None:
    return _REGISTRY.get(key)


def can_use_mode(user: User | None, mode: PromptMode) -> bool:
    return has_permission(user, mode.permission)


def available_modes(user: User | None) -> list[PromptMode]:
    """Tryby, z których konto może korzystać — kolejność jak w rejestrze."""
    return [mode for mode in _REGISTRY.values() if can_use_mode(user, mode)]


__all__ = ["PromptMode", "all_modes", "available_modes", "can_use_mode", "get_mode"]
