"""Wspólna konfiguracja testów: izolowana baza danych i klienci HTTP."""
from __future__ import annotations

import importlib
import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture()
def app_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Ładuje aplikację z czystym katalogiem danych dla każdego testu."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("QUIZAPP_DATA_DIR", str(data_dir))
    monkeypatch.setenv("QUIZAPP_SECRET_KEY", "testowy-klucz-podpisu-sesji-0123456789")
    monkeypatch.setenv("QUIZAPP_ALLOW_REGISTRATION", "true")
    # Domyślnie bez zestawu pokazowego — testy startują z pustą bazą treści.
    monkeypatch.setenv("QUIZAPP_SEED_EXAMPLE_SET", os.environ.get("QUIZAPP_SEED_EXAMPLE_SET", "false"))

    # Wymuszenie ponownego importu modułów zależnych od konfiguracji.
    for name in [key for key in list(sys.modules) if key == "app" or key.startswith("app.")]:
        del sys.modules[name]

    config = importlib.import_module("app.config")
    config.get_settings.cache_clear()
    importlib.reload(config)

    database = importlib.import_module("app.database")
    database.reset_engine()

    main = importlib.import_module("app.main")
    return main


@pytest.fixture()
def client(app_module) -> Iterator:
    from fastapi.testclient import TestClient

    with TestClient(app_module.app) as test_client:
        yield test_client


@pytest.fixture()
def data_dir(app_module) -> Path:
    from app.config import settings

    return settings.data_dir


def register(client, username: str = "student", password: str = "TajneHaslo123") -> dict:
    """Tworzy konto i pozostawia klienta zalogowanego."""
    response = client.post("/api/auth/register", json={"username": username, "password": password})
    assert response.status_code == 201, response.text
    return response.json()


def login_admin(client, password: str = "admin") -> None:
    response = client.post("/api/auth/login", json={"username": "admin", "password": password})
    assert response.status_code == 200, response.text


def unlock_admin(client, new_password: str = "NoweHasloAdmina1") -> None:
    """Loguje konto startowe i ustawia własne hasło (zdejmuje blokadę)."""
    login_admin(client)
    response = client.post(
        "/api/auth/change-password",
        json={"current_password": "admin", "new_password": new_password},
    )
    assert response.status_code == 200, response.text


SAMPLE_SET = {
    "title": "Farmakologia — beta-blokery",
    "description": "Podstawy kliniczne",
    "subject": "Farmakologia",
    "visibility": "private",
    "tags": ["Farmakologia", "Układ krążenia"],
    "cards": [
        {"front": "Mechanizm działania propranololu", "back": "Nieselektywny antagonista receptorów beta-1 i beta-2."},
        {"front": "Główne przeciwwskazanie", "back": "Astma oskrzelowa — ryzyko skurczu oskrzeli.", "hint": "Układ oddechowy"},
    ],
    "questions": [
        {
            "prompt": "Który lek jest kardioselektywnym beta-blokerem?",
            "explanation": "Bisoprolol wykazuje powinowactwo głównie do receptorów beta-1.",
            "options": [
                {"text": "Propranolol", "is_correct": False, "feedback": "Działa nieselektywnie."},
                {"text": "Bisoprolol", "is_correct": True, "feedback": "Kardioselektywny."},
                {"text": "Karwedilol", "is_correct": False},
                {"text": "Sotalol", "is_correct": False},
            ],
        }
    ],
}
