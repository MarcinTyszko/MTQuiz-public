"""Tworzenie i przywracanie kopii zapasowych bazy SQLite."""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from .config import settings
from .database import create_all, get_engine, reset_engine

SQLITE_MAGIC = b"SQLite format 3\x00"
REQUIRED_TABLES = {"users", "study_sets", "flashcards", "questions", "answer_options"}
ARCHIVE_DB_NAME = "quizapp.db"
MANIFEST_NAME = "manifest.json"


class BackupError(Exception):
    """Błąd operacji kopii zapasowej lub przywracania."""


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def snapshot_database(target: Path) -> None:
    """Tworzy spójną migawkę bazy przy użyciu API `sqlite3.backup`.

    Dzięki temu kopia jest poprawna nawet podczas aktywnego zapisu (tryb WAL).
    """
    settings.ensure_directories()
    source_path = settings.database_path
    if not source_path.exists():
        create_all()

    target.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
    destination = sqlite3.connect(target)
    try:
        with destination:
            source.backup(destination)
    finally:
        destination.close()
        source.close()


def _collect_stats() -> dict[str, int]:
    stats: dict[str, int] = {}
    try:
        with sqlite3.connect(f"file:{settings.database_path}?mode=ro", uri=True) as connection:
            for table in sorted(REQUIRED_TABLES):
                try:
                    stats[table] = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                except sqlite3.Error:
                    stats[table] = -1
    except sqlite3.Error:  # pragma: no cover - baza może jeszcze nie istnieć
        return {}
    return stats


def create_backup_archive() -> tuple[Path, dict]:
    """Buduje archiwum ZIP z migawką bazy i manifestem. Zwraca ścieżkę i manifest."""
    settings.ensure_directories()
    stamp = _timestamp()
    archive_path = settings.backup_dir / f"medfiszki-backup-{stamp}.zip"

    with tempfile.TemporaryDirectory() as tmp:
        snapshot = Path(tmp) / ARCHIVE_DB_NAME
        snapshot_database(snapshot)

        manifest = {
            "application": settings.app_name,
            "schema": "medfiszki/backup",
            "version": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "database_file": ARCHIVE_DB_NAME,
            "database_bytes": snapshot.stat().st_size,
            "tables": _collect_stats(),
        }

        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            archive.write(snapshot, ARCHIVE_DB_NAME)
            archive.writestr(MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False, indent=2))

    _prune_old_backups()
    return archive_path, manifest


def _prune_old_backups(keep: int = 10) -> None:
    """Zachowuje wyłącznie `keep` najnowszych archiwów w katalogu kopii."""
    archives = sorted(settings.backup_dir.glob("medfiszki-backup-*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    for stale in archives[keep:]:
        try:
            stale.unlink()
        except OSError:  # pragma: no cover
            pass


def _extract_database(raw: bytes, workdir: Path) -> Path:
    """Wydobywa plik bazy z przesłanych danych (archiwum ZIP albo surowy `.db`)."""
    if raw[: len(SQLITE_MAGIC)] == SQLITE_MAGIC:
        candidate = workdir / "uploaded.db"
        candidate.write_bytes(raw)
        return candidate

    upload = workdir / "upload.zip"
    upload.write_bytes(raw)
    if not zipfile.is_zipfile(upload):
        raise BackupError("Przesłany plik nie jest ani bazą SQLite, ani archiwum ZIP z kopią zapasową.")

    with zipfile.ZipFile(upload) as archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        db_names = [name for name in names if Path(name).name == ARCHIVE_DB_NAME]
        if not db_names:
            db_names = [name for name in names if name.lower().endswith((".db", ".sqlite", ".sqlite3"))]
        if not db_names:
            raise BackupError("Archiwum nie zawiera pliku bazy danych (oczekiwano „quizapp.db”).")

        name = db_names[0]
        info = archive.getinfo(name)
        if info.file_size > settings.max_restore_bytes:
            raise BackupError("Baza w archiwum przekracza dopuszczalny rozmiar przywracania.")

        target = workdir / "restored.db"
        with archive.open(name) as source, target.open("wb") as destination:
            shutil.copyfileobj(source, destination, length=1024 * 1024)
        return target


def _validate_database_file(path: Path) -> dict[str, int]:
    """Sprawdza integralność i obecność wymaganych tabel. Zwraca liczności tabel."""
    if path.stat().st_size < len(SQLITE_MAGIC):
        raise BackupError("Plik bazy danych jest uszkodzony (zbyt mały).")
    with path.open("rb") as handle:
        if handle.read(len(SQLITE_MAGIC)) != SQLITE_MAGIC:
            raise BackupError("Plik nie jest poprawną bazą SQLite.")

    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        check = connection.execute("PRAGMA integrity_check").fetchone()
        if not check or check[0] != "ok":
            raise BackupError("Kontrola spójności bazy zakończyła się niepowodzeniem.")

        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        missing = REQUIRED_TABLES - tables
        if missing:
            raise BackupError(
                "Baza nie zawiera wymaganych tabel: " + ", ".join(sorted(missing)) + "."
            )

        admins = connection.execute(
            "SELECT COUNT(*) FROM users WHERE role = 'ADMIN' OR role = 'admin'"
        ).fetchone()[0]
        if admins == 0:
            raise BackupError("Przywracana baza nie zawiera żadnego konta administratora.")

        return {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in sorted(REQUIRED_TABLES)}
    except sqlite3.DatabaseError as exc:
        raise BackupError(f"Nie udało się odczytać bazy danych: {exc}") from exc
    finally:
        connection.close()


def restore_from_bytes(raw: bytes) -> dict:
    """Przywraca bazę z przesłanych danych, tworząc wcześniej kopię bezpieczeństwa.

    Zwraca podsumowanie: liczności tabel i ścieżkę automatycznej kopii sprzed
    przywrócenia (ratunek w razie pomyłki administratora).
    """
    if not raw:
        raise BackupError("Nie przesłano żadnych danych.")
    if len(raw) > settings.max_restore_bytes:
        raise BackupError("Przesłany plik jest zbyt duży.")

    settings.ensure_directories()

    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        candidate = _extract_database(raw, workdir)
        table_stats = _validate_database_file(candidate)

        safety_copy = settings.backup_dir / f"medfiszki-przed-przywroceniem-{_timestamp()}.db"
        if settings.database_path.exists():
            snapshot_database(safety_copy)

        # Zwolnienie uchwytów do pliku przed podmianą.
        reset_engine()

        for suffix in ("-wal", "-shm"):
            sidecar = settings.database_path.with_name(settings.database_path.name + suffix)
            if sidecar.exists():
                sidecar.unlink()

        # Podmiana przez atomowe przeniesienie: ewentualne otwarte uchwyty do
        # starego pliku nie zobaczą częściowo zapisanych danych.
        staging = settings.database_path.with_name(settings.database_path.name + ".restore-tmp")
        shutil.copyfile(candidate, staging)
        os.replace(staging, settings.database_path)

    # Ponowne otwarcie puli i uzupełnienie ewentualnie brakujących tabel.
    get_engine()
    create_all()

    return {
        "tables": table_stats,
        "safety_copy": safety_copy.name if safety_copy.exists() else None,
        "database_bytes": settings.database_path.stat().st_size,
    }
