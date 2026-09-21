"""Testy inicjalizacji instancji: konto startowe i zestaw pokazowy."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


@pytest.fixture()
def seeded_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Instancja uruchomiona z domyślnym ustawieniem zestawu pokazowego."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("QUIZAPP_DATA_DIR", str(data_dir))
    monkeypatch.setenv("QUIZAPP_SECRET_KEY", "testowy-klucz-podpisu-sesji-0123456789")
    monkeypatch.setenv("QUIZAPP_SEED_EXAMPLE_SET", "true")

    for name in [key for key in list(sys.modules) if key == "app" or key.startswith("app.")]:
        del sys.modules[name]

    config = importlib.import_module("app.config")
    config.get_settings.cache_clear()
    importlib.reload(config)
    importlib.import_module("app.database").reset_engine()
    main = importlib.import_module("app.main")

    from fastapi.testclient import TestClient

    with TestClient(main.app) as client:
        yield client


def test_pierwsze_uruchomienie_tworzy_admina_i_zestaw_pokazowy(seeded_client):
    feed = seeded_client.get("/api/public/sets").json()
    assert len(feed) == 1

    example = feed[0]
    assert example["author_username"] == "admin"
    assert example["subject"] == "Anatomia"
    assert example["cards_count"] >= 12
    assert example["questions_count"] >= 5
    assert "Neuroanatomia" in example["tags"]

    detail = seeded_client.get(f"/api/sets/{example['id']}").json()
    assert all(card["front"] and card["back"] for card in detail["cards"])
    assert all(
        any(option["is_correct"] for option in question["options"]) for question in detail["questions"]
    )


def test_ponowny_start_nie_duplikuje_danych(seeded_client):
    from app.bootstrap import initialise

    before = seeded_client.get("/api/public/sets").json()
    initialise()
    initialise()
    after = seeded_client.get("/api/public/sets").json()

    assert len(after) == len(before) == 1


def test_konto_startowe_ma_role_admina_i_blokade(seeded_client):
    seeded_client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    me = seeded_client.get("/api/auth/me").json()

    assert me["role"] == "admin"
    assert me["must_change_password"] is True
