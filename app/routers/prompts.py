"""Tryby generatora promptu dostępne dla zalogowanego konta."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status

from ..deps import UnlockedUser
from ..prompts import available_modes, can_use_mode, get_mode

router = APIRouter(prefix="/api/prompts", tags=["prompts"])


@router.get("/modes")
def list_modes(user: UnlockedUser) -> list[dict[str, Any]]:
    """Pełne definicje trybów, z których konto może korzystać (pusta lista bez rangi)."""
    return [mode.to_client() for mode in available_modes(user)]


@router.get("/modes/{key}")
def mode_detail(key: str, user: UnlockedUser) -> dict[str, Any]:
    mode = get_mode(key)
    if mode is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nie ma takiego trybu generatora.")
    if not can_use_mode(user, mode):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Tryb „{mode.label}” wymaga rangi: {mode.badge or 'wyższej'}.",
        )
    return mode.to_client()
