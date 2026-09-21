"""Testy narzędzi administracyjnych z wiersza poleceń (`python -m app.cli`)."""
from __future__ import annotations

import pytest
from sqlalchemy import select


@pytest.fixture()
def cli(app_module):
    """Moduł CLI zbudowany na izolowanej bazie testowej."""
    import importlib

    from app.bootstrap import initialise

    initialise()
    return importlib.import_module("app.cli")


def _konto(nazwa: str):
    from app.database import session_scope
    from app.models import User

    with session_scope() as db:
        return db.scalar(select(User).where(User.username == nazwa))


def test_wypisanie_kont(cli, capsys):
    assert cli.main(["konta"]) == 0
    wynik = capsys.readouterr().out

    assert "admin" in wynik
    assert "administrator" in wynik


def test_reset_admina_przywraca_haslo_startowe(cli, capsys):
    from app.security import verify_password

    # Symulacja utraty dostępu: hasło zmienione poza aplikacją.
    from app.database import session_scope
    from app.models import User
    from app.security import hash_password

    with session_scope() as db:
        konto = db.scalar(select(User).where(User.username == "admin"))
        konto.password_hash = hash_password("zapomnianeHaslo999")
        konto.must_change_password = False

    assert cli.main(["reset-admina"]) == 0
    wynik = capsys.readouterr().out
    assert "admin" in wynik

    konto = _konto("admin")
    assert verify_password("admin", konto.password_hash) is True
    assert konto.must_change_password is True
    assert konto.is_active is True


def test_reset_admina_z_wlasnym_haslem(cli, capsys):
    from app.security import verify_password

    assert cli.main(["reset-admina", "--haslo", "WlasneHaslo12345", "--bez-wymuszania"]) == 0
    capsys.readouterr()

    konto = _konto("admin")
    assert verify_password("WlasneHaslo12345", konto.password_hash) is True
    assert konto.must_change_password is False


def test_reset_admina_odrzuca_slabe_haslo(cli, capsys):
    assert cli.main(["reset-admina", "--haslo", "krotkie"]) == 1
    assert "co najmniej 8 znaków" in capsys.readouterr().err


def test_reset_nieistniejacego_konta_konczy_sie_bledem(cli, capsys):
    assert cli.main(["reset-admina", "--login", "nie-ma-takiego"]) == 1
    assert "Nie znaleziono konta" in capsys.readouterr().err


def test_reset_podnosi_uprawnienia_zwyklego_konta(cli, capsys):
    from app.database import session_scope
    from app.models import User, UserRole
    from app.security import hash_password

    with session_scope() as db:
        db.add(
            User(
                username="ratunkowy",
                password_hash=hash_password("HasloStartowe123"),
                role=UserRole.USER,
                is_active=False,
            )
        )

    assert cli.main(["reset-admina", "--login", "ratunkowy"]) == 0
    capsys.readouterr()

    konto = _konto("ratunkowy")
    assert konto.role.value == "admin"
    assert konto.is_active is True


def test_utworzenie_nowego_administratora(cli, capsys):
    assert cli.main(["utworz-admina", "zapasowy", "--haslo", "ZapasoweHaslo123"]) == 0
    assert "zapasowy" in capsys.readouterr().out

    konto = _konto("zapasowy")
    assert konto.role.value == "admin"
    assert konto.must_change_password is True

    # Ponowne utworzenie tego samego konta musi się nie powieść.
    assert cli.main(["utworz-admina", "zapasowy"]) == 1
    assert "już istnieje" in capsys.readouterr().err


def test_utworzenie_admina_odrzuca_niepoprawny_login(cli, capsys):
    assert cli.main(["utworz-admina", "zły login!"]) == 1
    assert "Nazwa użytkownika" in capsys.readouterr().err


def test_kopia_zapasowa_z_wiersza_polecen(cli, capsys, data_dir):
    assert cli.main(["kopia-zapasowa"]) == 0
    wynik = capsys.readouterr().out

    assert "Utworzono kopię zapasową" in wynik
    archiwa = list((data_dir / "backups").glob("mtquiz-backup-*.zip"))
    assert len(archiwa) == 1
