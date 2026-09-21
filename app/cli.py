"""Narzędzia administracyjne uruchamiane z wiersza poleceń.

Użycie w kontenerze:

    docker compose exec mtquiz python -m app.cli konta
    docker compose exec mtquiz python -m app.cli reset-admina
    docker compose exec mtquiz python -m app.cli kopia-zapasowa
"""
from __future__ import annotations

import argparse
import secrets
import sys

from sqlalchemy import func, select

from .database import create_all, session_scope
from .models import StudySet, User, UserRole
from .security import hash_password, validate_password_strength, validate_username
from .services import log_action


def _tabela_kont() -> int:
    with session_scope() as db:
        konta = list(db.scalars(select(User).order_by(User.id)))
        if not konta:
            print("Baza nie zawiera żadnych kont.")
            return 0

        zestawy = dict(
            db.execute(
                select(StudySet.author_id, func.count(StudySet.id)).group_by(StudySet.author_id)
            ).all()
        )

        print(f"{'ID':>3}  {'Login':<24} {'Rola':<14} {'Stan':<12} {'Zestawy':>7}  Ostatnie logowanie")
        print("-" * 92)
        for konto in konta:
            stan = "aktywne" if konto.is_active else "zablokowane"
            if konto.must_change_password:
                stan += "*"
            ostatnie = konto.last_login_at.strftime("%d.%m.%Y %H:%M") if konto.last_login_at else "—"
            rola = "administrator" if konto.is_admin else "użytkownik"
            print(f"{konto.id:>3}  {konto.username:<24} {rola:<14} {stan:<12} {zestawy.get(konto.id, 0):>7}  {ostatnie}")
        print("\n* konto musi ustawić nowe hasło przy najbliższym logowaniu")
    return 0


def _reset_admina(login: str, haslo: str | None, bez_wymuszania: bool) -> int:
    """Przywraca dostęp do konta administratora i wymusza zmianę hasła."""
    nowe_haslo = haslo or "admin"
    if haslo is not None:
        try:
            validate_password_strength(haslo)
        except ValueError as exc:
            print(f"Błąd: {exc}", file=sys.stderr)
            return 1

    with session_scope() as db:
        konto = db.scalar(select(User).where(func.lower(User.username) == login.lower()))
        if konto is None:
            print(f"Nie znaleziono konta „{login}”. Dostępne konta wypisze polecenie: konta", file=sys.stderr)
            return 1

        konto.password_hash = hash_password(nowe_haslo)
        konto.role = UserRole.ADMIN
        konto.is_active = True
        konto.must_change_password = not bez_wymuszania
        log_action(db, None, "cli.reset_admina", f"Zresetowano hasło konta {konto.username} z wiersza poleceń.")

    print(f"Konto „{login}” jest aktywne, ma uprawnienia administratora i hasło: {nowe_haslo}")
    if not bez_wymuszania:
        print("Przy pierwszym logowaniu aplikacja poprosi o ustawienie własnego hasła.")
    return 0


def _utworz_admina(login: str, haslo: str | None) -> int:
    nowe_haslo = haslo or secrets.token_urlsafe(9)
    try:
        login = validate_username(login)
        validate_password_strength(nowe_haslo)
    except ValueError as exc:
        print(f"Błąd: {exc}", file=sys.stderr)
        return 1

    with session_scope() as db:
        if db.scalar(select(User).where(func.lower(User.username) == login.lower())) is not None:
            print(f"Konto „{login}” już istnieje. Użyj polecenia: reset-admina --login {login}", file=sys.stderr)
            return 1

        db.add(
            User(
                username=login,
                display_name="Administrator",
                password_hash=hash_password(nowe_haslo),
                role=UserRole.ADMIN,
                is_active=True,
                must_change_password=True,
            )
        )
        log_action(db, None, "cli.utworz_admina", f"Utworzono konto administratora {login} z wiersza poleceń.")

    print(f"Utworzono konto administratora „{login}” z hasłem: {nowe_haslo}")
    print("Przy pierwszym logowaniu aplikacja poprosi o ustawienie własnego hasła.")
    return 0


def _kopia_zapasowa() -> int:
    from .backup import create_backup_archive

    sciezka, manifest = create_backup_archive()
    tabele = ", ".join(f"{nazwa}: {liczba}" for nazwa, liczba in manifest["tables"].items())
    print(f"Utworzono kopię zapasową: {sciezka}")
    print(f"Rozmiar bazy: {manifest['database_bytes'] / 1024:.1f} KB")
    print(f"Zawartość: {tabele}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description="Narzędzia administracyjne platformy MTQuiz.",
    )
    podpolecenia = parser.add_subparsers(dest="polecenie", required=True)

    podpolecenia.add_parser("konta", help="wypisuje wszystkie konta wraz ze stanem")

    reset = podpolecenia.add_parser(
        "reset-admina",
        help="przywraca dostęp do konta administratora (domyślnie login admin, hasło admin)",
    )
    reset.add_argument("--login", default="admin", help="login konta do odzyskania (domyślnie: admin)")
    reset.add_argument("--haslo", default=None, help="nowe hasło; pominięte ustawia hasło startowe „admin”")
    reset.add_argument(
        "--bez-wymuszania",
        action="store_true",
        help="nie wymuszaj zmiany hasła przy najbliższym logowaniu",
    )

    utworz = podpolecenia.add_parser("utworz-admina", help="tworzy nowe konto administratora")
    utworz.add_argument("login", help="login nowego konta")
    utworz.add_argument("--haslo", default=None, help="hasło; pominięte generuje losowe")

    podpolecenia.add_parser("kopia-zapasowa", help="tworzy archiwum ZIP z kopią bazy danych")

    args = parser.parse_args(argv)
    create_all()

    if args.polecenie == "konta":
        return _tabela_kont()
    if args.polecenie == "reset-admina":
        return _reset_admina(args.login, args.haslo, args.bez_wymuszania)
    if args.polecenie == "utworz-admina":
        return _utworz_admina(args.login, args.haslo)
    if args.polecenie == "kopia-zapasowa":
        return _kopia_zapasowa()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
