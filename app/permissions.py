"""Uprawnienia oparte na rangach kont (RBAC).

Kod aplikacji pyta o uprawnienie, a nie o nazwę rangi — dzięki temu nowa ranga
to jeden wpis w ``ROLE_PERMISSIONS``, bez przeszukiwania szablonów i routerów.
Administrator ma zawsze komplet uprawnień.
"""
from __future__ import annotations

import enum

from .models import User, UserRole


class Permission(str, enum.Enum):
    # Dziedzinowe tryby generatora promptu: LEK, anatomia, synteza skryptu.
    MEDICAL_PROMPTS = "prompts.medical"


ROLE_PERMISSIONS: dict[UserRole, frozenset[Permission]] = {
    UserRole.USER: frozenset(),
    UserRole.MEDICAL_STUDENT: frozenset({Permission.MEDICAL_PROMPTS}),
    UserRole.ADMIN: frozenset(Permission),
}

ROLE_LABELS: dict[UserRole, str] = {
    UserRole.USER: "Użytkownik",
    UserRole.MEDICAL_STUDENT: "Student medycyny",
    UserRole.ADMIN: "Administrator",
}


def permissions_for(user: User | None) -> frozenset[Permission]:
    """Zbiór uprawnień konta; gość i konto zablokowane nie mają żadnych."""
    if user is None or not user.is_active:
        return frozenset()
    return ROLE_PERMISSIONS.get(user.role, frozenset())


def has_permission(user: User | None, permission: Permission | str) -> bool:
    """Sprawdza uprawnienie; przyjmuje też wartość tekstową (wygodne w szablonach)."""
    try:
        wanted = Permission(permission)
    except ValueError:
        return False
    return wanted in permissions_for(user)


def role_label(role: UserRole | str | None) -> str:
    try:
        return ROLE_LABELS[UserRole(role)]
    except ValueError:
        return str(role or "—")


def role_choices() -> list[dict[str, str]]:
    """Rangi w kolejności rosnących uprawnień — do list wyboru w interfejsie."""
    return [{"value": role.value, "label": ROLE_LABELS[role]} for role in UserRole]
