"""Testy rang kont (RBAC): uprawnienia, zarządzanie rangą i zgodność wsteczna bazy."""
from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy import select

from conftest import register, unlock_admin

# Schemat tabel sprzed wprowadzenia rangi „student medycyny” — skopiowany z bazy
# działającej instancji. Kolumna `role` ma długość 5 znaków i brak ograniczenia CHECK.
LEGACY_USERS_DDL = """
CREATE TABLE users (
    id INTEGER NOT NULL,
    username VARCHAR(64) NOT NULL,
    email VARCHAR(255),
    display_name VARCHAR(120),
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(5) NOT NULL,
    is_active BOOLEAN NOT NULL,
    must_change_password BOOLEAN NOT NULL,
    created_at DATETIME NOT NULL,
    last_login_at DATETIME,
    PRIMARY KEY (id)
)
"""
LEGACY_SESSIONS_DDL = """
CREATE TABLE study_sessions (
    id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    set_id INTEGER NOT NULL,
    mode VARCHAR(10) NOT NULL,
    score INTEGER NOT NULL,
    total INTEGER NOT NULL,
    duration_seconds INTEGER NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
    FOREIGN KEY(set_id) REFERENCES study_sets (id) ON DELETE CASCADE
)
"""


def _admin_client(app_module):
    """Drugi klient zalogowany jako odblokowany administrator."""
    from fastapi.testclient import TestClient

    admin = TestClient(app_module.app)
    unlock_admin(admin)
    return admin


def _user_id(client, username: str) -> int:
    users = client.get(f"/api/admin/users?q={username}").json()
    return next(item["id"] for item in users if item["username"] == username)


# --------------------------------------------------------------------------- #
# Macierz uprawnień
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("role", "expected"),
    [("user", False), ("medical_student", True), ("admin", True)],
)
def test_uprawnienie_do_trybow_medycznych_wynika_z_rangi(app_module, role, expected):
    from app.models import User, UserRole
    from app.permissions import Permission, has_permission

    user = User(username="x", password_hash="-", role=UserRole(role), is_active=True)
    assert has_permission(user, Permission.MEDICAL_PROMPTS) is expected
    # Wariant tekstowy — używany w szablonach.
    assert has_permission(user, "prompts.medical") is expected


def test_konto_zablokowane_i_gosc_nie_maja_uprawnien(app_module):
    from app.models import User, UserRole
    from app.permissions import Permission, has_permission

    blocked = User(username="x", password_hash="-", role=UserRole.ADMIN, is_active=False)
    assert has_permission(blocked, Permission.MEDICAL_PROMPTS) is False
    assert has_permission(None, Permission.MEDICAL_PROMPTS) is False
    assert has_permission(blocked, "nieistniejace.uprawnienie") is False


def test_kazda_ranga_ma_etykiete_i_wpis_uprawnien(app_module):
    from app.models import UserRole
    from app.permissions import ROLE_LABELS, ROLE_PERMISSIONS, role_choices

    assert set(ROLE_LABELS) == set(UserRole)
    assert set(ROLE_PERMISSIONS) == set(UserRole)
    assert [choice["value"] for choice in role_choices()] == ["user", "medical_student", "admin"]


# --------------------------------------------------------------------------- #
# Zarządzanie rangą przez administratora
# --------------------------------------------------------------------------- #
def test_nowe_konto_dostaje_range_uzytkownika(client):
    created = register(client)
    assert created["role"] == "user"
    assert client.get("/api/auth/me").json()["role"] == "user"


def test_administrator_nadaje_range_studenta_medycyny(client, app_module):
    register(client, "kasia")
    admin = _admin_client(app_module)
    user_id = _user_id(admin, "kasia")

    response = admin.patch(f"/api/admin/users/{user_id}", json={"role": "medical_student"})
    assert response.status_code == 200, response.text
    assert response.json()["role"] == "medical_student"

    # Zmiana działa od razu w sesji samego użytkownika i trafia do dziennika.
    assert client.get("/api/auth/me").json()["role"] == "medical_student"
    audit = admin.get("/api/admin/audit").json()
    assert any(
        entry["action"] == "admin.user_role" and "Użytkownik → Student medycyny" in entry["detail"]
        for entry in audit
    )
    assert admin.get("/api/admin/stats").json()["medical_students"] == 1


def test_uzytkownik_nie_moze_zmienic_rangi(client):
    created = register(client)
    response = client.patch(f"/api/admin/users/{created['id']}", json={"role": "medical_student"})
    assert response.status_code == 403


def test_nieznana_ranga_jest_odrzucana(client, app_module):
    register(client, "kasia")
    admin = _admin_client(app_module)
    response = admin.patch(f"/api/admin/users/{_user_id(admin, 'kasia')}", json={"role": "superadmin"})
    assert response.status_code == 422


def test_administrator_nie_moze_sam_zejsc_do_rangi_studenta(client, app_module):
    admin = _admin_client(app_module)
    response = admin.patch(f"/api/admin/users/{_user_id(admin, 'admin')}", json={"role": "medical_student"})
    assert response.status_code == 400
    assert admin.get("/api/auth/me").json()["role"] == "admin"


def test_administrator_moze_zdegradowac_innego_administratora(client, app_module):
    register(client, "drugi")
    admin = _admin_client(app_module)
    other_id = _user_id(admin, "drugi")

    assert admin.patch(f"/api/admin/users/{other_id}", json={"role": "admin"}).status_code == 200
    response = admin.patch(f"/api/admin/users/{other_id}", json={"role": "medical_student"})
    assert response.status_code == 200
    assert response.json()["role"] == "medical_student"


def test_panel_administratora_oferuje_wszystkie_rangi(client, app_module):
    admin = _admin_client(app_module)
    page = admin.get("/panel")
    assert page.status_code == 200
    for value, label in (("user", "Użytkownik"), ("medical_student", "Student medycyny"), ("admin", "Administrator")):
        assert f'<option value="{value}">{label}</option>' in page.text


def test_strona_konta_pokazuje_nazwe_rangi(client, app_module):
    register(client, "kasia")
    admin = _admin_client(app_module)
    admin.patch(f"/api/admin/users/{_user_id(admin, 'kasia')}", json={"role": "medical_student"})
    assert "Student medycyny" in client.get("/konto").text


# --------------------------------------------------------------------------- #
# Zgodność wsteczna z istniejącą bazą
# --------------------------------------------------------------------------- #
def test_istniejaca_baza_przyjmuje_nowa_range_bez_migracji(app_module, data_dir):
    """Baza utworzona przez starszą wersję działa bez zmian w schemacie."""
    from fastapi.testclient import TestClient

    database = data_dir / "quizapp.db"
    with sqlite3.connect(database) as connection:
        connection.execute(LEGACY_USERS_DDL)
        connection.execute(LEGACY_SESSIONS_DDL)
        connection.execute("CREATE INDEX ix_study_sessions_user_id ON study_sessions (user_id)")
        connection.execute(
            "INSERT INTO users (username, password_hash, role, is_active, must_change_password, created_at) "
            "VALUES ('stary', 'x', 'USER', 1, 0, '2025-01-01 10:00:00.000000')"
        )

    with TestClient(app_module.app):
        from app.database import session_scope
        from app.models import User, UserRole

        with session_scope() as db:
            legacy = db.scalar(select(User).where(User.username == "stary"))
            # Dotychczasowe konto zachowuje bezpieczną rangę domyślną.
            assert legacy.role == UserRole.USER
            legacy.role = UserRole.MEDICAL_STUDENT

        with session_scope() as db:
            assert db.scalar(select(User).where(User.username == "stary")).role == UserRole.MEDICAL_STUDENT

    with sqlite3.connect(database) as connection:
        ddl = connection.execute("SELECT sql FROM sqlite_master WHERE name = 'users'").fetchone()[0]
        stored = connection.execute("SELECT role FROM users WHERE username = 'stary'").fetchone()[0]
        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'study_sessions'"
            )
        }

    # Schemat kolumny pozostał nietknięty, a nowy indeks dołożono addytywnie.
    assert "role VARCHAR(5) NOT NULL" in ddl
    assert stored == "MEDICAL_STUDENT"
    assert "ix_study_sessions_activity" in indexes
    assert "ix_study_sessions_user_id" in indexes


# --------------------------------------------------------------------------- #
# Wiersz poleceń
# --------------------------------------------------------------------------- #
@pytest.fixture()
def cli(app_module):
    import importlib

    from app.bootstrap import initialise

    initialise()
    return importlib.import_module("app.cli")


def _role(username: str):
    from app.database import session_scope
    from app.models import User

    with session_scope() as db:
        return db.scalar(select(User).where(User.username == username)).role


def _add_user(username: str) -> None:
    from app.database import session_scope
    from app.models import User, UserRole

    with session_scope() as db:
        db.add(User(username=username, password_hash="-", role=UserRole.USER, is_active=True))


def test_cli_nadaje_range(cli, capsys):
    from app.models import UserRole

    _add_user("jan")
    assert cli.main(["rola", "jan", "medical_student"]) == 0
    assert "Użytkownik → Student medycyny" in capsys.readouterr().out
    assert _role("jan") == UserRole.MEDICAL_STUDENT

    assert cli.main(["konta"]) == 0
    assert "student medycyny" in capsys.readouterr().out


def test_cli_nie_degraduje_jedynego_administratora(cli, capsys):
    from app.models import UserRole

    assert cli.main(["rola", "admin", "user"]) == 1
    assert "jedyny aktywny administrator" in capsys.readouterr().err
    assert _role("admin") == UserRole.ADMIN


def test_cli_odrzuca_nieznana_range(cli):
    with pytest.raises(SystemExit):
        cli.main(["rola", "admin", "superadmin"])
