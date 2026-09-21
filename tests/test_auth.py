"""Testy uwierzytelniania, ról i wymuszonej zmiany hasła."""
from __future__ import annotations

from conftest import login_admin, register, unlock_admin


def test_bootstrap_admin_wymusza_zmiane_hasla(client):
    login_admin(client)
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["must_change_password"] is True
    assert me.json()["role"] == "admin"

    # Do czasu zmiany hasła funkcje aplikacji pozostają zablokowane.
    blocked = client.get("/api/sets")
    assert blocked.status_code == 403


def test_zmiana_hasla_odblokowuje_konto_i_uniewaznia_stare_haslo(client):
    unlock_admin(client)

    me = client.get("/api/auth/me").json()
    assert me["must_change_password"] is False
    assert client.get("/api/sets").status_code == 200

    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={"username": "admin", "password": "admin"}).status_code == 401
    assert (
        client.post("/api/auth/login", json={"username": "admin", "password": "NoweHasloAdmina1"}).status_code == 200
    )


def test_rejestracja_i_konflikt_nazwy(client):
    user = register(client)
    assert user["role"] == "user"
    assert user["must_change_password"] is False

    duplicate = client.post("/api/auth/register", json={"username": "student", "password": "InneHaslo123"})
    assert duplicate.status_code == 409


def test_zbyt_slabe_haslo_jest_odrzucane(client):
    response = client.post("/api/auth/register", json={"username": "nowy", "password": "1234567"})
    assert response.status_code == 422


def test_zmiana_hasla_uniewaznia_wydane_tokeny(client):
    register(client, "kasia", "PierwszeHaslo123")
    token = client.cookies.get("mtquiz_session")
    assert token

    client.post(
        "/api/auth/change-password",
        json={"current_password": "PierwszeHaslo123", "new_password": "DrugieHaslo456"},
    )

    fresh_token = client.cookies.get("mtquiz_session")
    assert fresh_token and fresh_token != token
    assert client.get("/api/auth/me").status_code == 200

    # Stary token nie może już autoryzować żądań.
    client.cookies.clear()
    stale = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert stale.status_code == 401


def test_nieaktywne_konto_nie_moze_sie_zalogowac(client):
    register(client, "zablokowany", "HasloTestowe123")
    client.post("/api/auth/logout")

    unlock_admin(client)
    users = client.get("/api/admin/users").json()
    target = next(item for item in users if item["username"] == "zablokowany")
    assert client.patch(f"/api/admin/users/{target['id']}", json={"is_active": False}).status_code == 200
    client.post("/api/auth/logout")

    response = client.post("/api/auth/login", json={"username": "zablokowany", "password": "HasloTestowe123"})
    assert response.status_code == 403


def test_uzytkownik_bez_uprawnien_nie_wejdzie_do_panelu(client):
    register(client)
    assert client.get("/api/admin/stats").status_code == 403
