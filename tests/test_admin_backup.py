"""Testy panelu administratora: moderacja, konta oraz kopie zapasowe."""
from __future__ import annotations

import copy
import io
import zipfile

from conftest import SAMPLE_SET, register, unlock_admin


def public_set_by(client, username, password):
    register(client, username, password)
    payload = copy.deepcopy(SAMPLE_SET)
    payload["visibility"] = "public"
    created = client.post("/api/sets", json=payload).json()
    client.post("/api/auth/logout")
    return created


def test_statystyki_instancji(client):
    created = public_set_by(client, "autor", "HasloAutora123")
    unlock_admin(client)

    stats = client.get("/api/admin/stats").json()
    assert stats["users_total"] == 2
    assert stats["admins"] == 1
    assert stats["sets_total"] == 1
    assert stats["sets_public"] == 1
    assert stats["cards_total"] == len(SAMPLE_SET["cards"])
    assert stats["database_size_bytes"] > 0
    assert stats["database_path"].endswith("quizapp.db")
    assert created["id"] > 0


def test_moderacja_zdejmuje_zestaw_z_bazy_publicznej(client):
    created = public_set_by(client, "autor", "HasloAutora123")
    unlock_admin(client)

    response = client.patch(f"/api/admin/sets/{created['id']}", json={"is_published": False, "moderation_note": "Naruszenie zasad"})
    assert response.status_code == 200
    assert response.json()["is_published"] is False

    client.post("/api/auth/logout")
    register(client, "czytelnik", "HasloCzytelnika1")
    assert client.get("/api/public/sets").json() == []
    assert client.get(f"/api/sets/{created['id']}").status_code == 403


def test_wlasciciel_widzi_wlasny_zdjety_zestaw(client):
    created = public_set_by(client, "autor", "HasloAutora123")
    unlock_admin(client)
    client.patch(f"/api/admin/sets/{created['id']}", json={"is_published": False})
    client.post("/api/auth/logout")

    client.post("/api/auth/login", json={"username": "autor", "password": "HasloAutora123"})
    detail = client.get(f"/api/sets/{created['id']}")
    assert detail.status_code == 200
    assert detail.json()["is_published"] is False


def test_nie_mozna_usunac_ostatniego_administratora(client):
    unlock_admin(client)
    me = client.get("/api/auth/me").json()

    assert client.patch(f"/api/admin/users/{me['id']}", json={"is_active": False}).status_code == 400
    assert client.patch(f"/api/admin/users/{me['id']}", json={"role": "user"}).status_code == 400
    assert client.delete(f"/api/admin/users/{me['id']}").status_code == 400


def test_reset_hasla_wymusza_zmiane_przy_logowaniu(client):
    register(client, "student", "StareHaslo12345")
    client.post("/api/auth/logout")
    unlock_admin(client)

    target = next(item for item in client.get("/api/admin/users").json() if item["username"] == "student")
    response = client.post(f"/api/admin/users/{target['id']}/reset-password", json={})
    assert response.status_code == 200

    message = response.json()["message"]
    temporary = message.split(": ", 1)[1].split(" —")[0]
    client.post("/api/auth/logout")

    assert client.post("/api/auth/login", json={"username": "student", "password": "StareHaslo12345"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "student", "password": temporary}).status_code == 200
    assert client.get("/api/auth/me").json()["must_change_password"] is True
    assert client.get("/api/sets").status_code == 403


def test_usuniecie_konta_kasuje_jego_zestawy(client):
    created = public_set_by(client, "autor", "HasloAutora123")
    unlock_admin(client)

    target = next(item for item in client.get("/api/admin/users").json() if item["username"] == "autor")
    assert client.delete(f"/api/admin/users/{target['id']}").status_code == 200
    assert client.get("/api/admin/stats").json()["sets_total"] == 0
    assert client.get(f"/api/sets/{created['id']}").status_code == 404


def test_dziennik_zdarzen_rejestruje_operacje(client):
    public_set_by(client, "autor", "HasloAutora123")
    unlock_admin(client)

    actions = {entry["action"] for entry in client.get("/api/admin/audit").json()}
    assert "bootstrap.admin_created" in actions
    assert "user.register" in actions
    assert "set.create" in actions
    assert "user.password_changed" in actions


def test_kopia_zapasowa_zawiera_baze_i_manifest(client, data_dir):
    public_set_by(client, "autor", "HasloAutora123")
    unlock_admin(client)

    response = client.post("/api/admin/backup")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"

    archive = zipfile.ZipFile(io.BytesIO(response.content))
    assert set(archive.namelist()) == {"quizapp.db", "manifest.json"}

    import json

    manifest = json.loads(archive.read("manifest.json"))
    assert manifest["schema"] == "medfiszki/backup"
    assert manifest["tables"]["study_sets"] == 1
    assert manifest["tables"]["users"] == 2

    # Archiwum zostaje również w katalogu danych.
    assert list((data_dir / "backups").glob("medfiszki-backup-*.zip"))


def test_przywrocenie_bazy_cofa_zmiany(client, data_dir):
    public_set_by(client, "autor", "HasloAutora123")
    unlock_admin(client)
    backup = client.post("/api/admin/backup").content

    # Zmiana stanu po wykonaniu kopii.
    target = next(item for item in client.get("/api/admin/users").json() if item["username"] == "autor")
    client.delete(f"/api/admin/users/{target['id']}")
    assert client.get("/api/admin/stats").json()["sets_total"] == 0

    response = client.post(
        "/api/admin/restore?confirm=PRZYWROC",
        files={"file": ("kopia.zip", io.BytesIO(backup), "application/zip")},
    )
    assert response.status_code == 200, response.text
    assert "przywrócona" in response.json()["message"]

    client.post("/api/auth/login", json={"username": "admin", "password": "NoweHasloAdmina1"})
    stats = client.get("/api/admin/stats").json()
    assert stats["sets_total"] == 1
    assert stats["users_total"] == 2

    # Kopia bezpieczeństwa sprzed przywrócenia została zapisana.
    assert list((data_dir / "backups").glob("medfiszki-przed-przywroceniem-*.db"))


def test_przywrocenie_bez_potwierdzenia_jest_blokowane(client):
    unlock_admin(client)
    backup = client.post("/api/admin/backup").content

    response = client.post(
        "/api/admin/restore",
        files={"file": ("kopia.zip", io.BytesIO(backup), "application/zip")},
    )
    assert response.status_code == 400


def test_przywrocenie_smieciowego_pliku_jest_odrzucane(client):
    unlock_admin(client)
    response = client.post(
        "/api/admin/restore?confirm=PRZYWROC",
        files={"file": ("plik.zip", io.BytesIO(b"to nie jest baza danych"), "application/zip")},
    )
    assert response.status_code == 422
    assert "SQLite" in response.json()["detail"] or "ZIP" in response.json()["detail"]


def test_przywrocenie_bazy_bez_administratora_jest_odrzucane(client, data_dir):
    unlock_admin(client)
    backup = client.post("/api/admin/backup").content

    # Przygotowanie archiwum z bazą pozbawioną kont administracyjnych.
    import sqlite3
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        source = zipfile.ZipFile(io.BytesIO(backup))
        db_path = Path(tmp) / "quizapp.db"
        db_path.write_bytes(source.read("quizapp.db"))
        # Połączenie zamykamy jawnie, aby dziennik WAL trafił do pliku bazy.
        connection = sqlite3.connect(db_path)
        connection.execute("UPDATE users SET role = 'USER'")
        connection.commit()
        connection.close()

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.write(db_path, "quizapp.db")
        payload = buffer.getvalue()

    response = client.post(
        "/api/admin/restore?confirm=PRZYWROC",
        files={"file": ("kopia.zip", io.BytesIO(payload), "application/zip")},
    )
    assert response.status_code == 422
    assert "administratora" in response.json()["detail"]
