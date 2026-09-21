"""Konfiguracja aplikacji odczytywana ze zmiennych środowiskowych."""
from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Ustawienia środowiskowe platformy MTQuiz."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="QUIZAPP_", extra="ignore")

    app_name: str = "MTQuiz"
    app_tagline: str = "Platforma nauki dla kierunków medycznych"

    # Katalog danych trwałych (montowany jako wolumen Dockera).
    data_dir: Path = Path("/data")
    database_filename: str = "quizapp.db"

    # Bezpieczeństwo
    secret_key: str = Field(default="")
    jwt_algorithm: str = "HS256"
    session_ttl_minutes: int = 60 * 24 * 14  # 14 dni
    cookie_name: str = "mtquiz_session"
    cookie_secure: bool = False
    cookie_samesite: str = "lax"

    # Konto startowe administratora
    bootstrap_admin_username: str = "admin"
    bootstrap_admin_password: str = "admin"

    # Limity walidacji importu
    max_upload_bytes: int = 25 * 1024 * 1024  # 25 MB
    max_restore_bytes: int = 512 * 1024 * 1024  # 512 MB
    max_cards_per_set: int = 5000
    max_questions_per_set: int = 5000

    # Rejestracja nowych użytkowników
    allow_registration: bool = True

    # Dodanie przykładowego zestawu pokazowego przy pierwszym uruchomieniu.
    seed_example_set: bool = True

    @field_validator("data_dir", mode="before")
    @classmethod
    def _expand(cls, value: str | Path) -> Path:
        return Path(str(value)).expanduser()

    @property
    def database_path(self) -> Path:
        return self.data_dir / self.database_filename

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_path}"

    @property
    def backup_dir(self) -> Path:
        return self.data_dir / "backups"

    def ensure_directories(self) -> None:
        """Tworzy katalogi trwałe, jeżeli jeszcze nie istnieją."""
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self.backup_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError as exc:
            raise RuntimeError(
                f"Brak prawa zapisu do katalogu danych „{self.data_dir}”. "
                "W konfiguracji Dockera ustaw QUIZAPP_UID i QUIZAPP_GID na wartości "
                "właściciela katalogu ./data (sprawdź poleceniem: id -u ; id -g) "
                "albo nadaj katalogowi odpowiednie uprawnienia."
            ) from exc

    def resolve_secret_key(self) -> str:
        """Zwraca klucz podpisu, generując trwały klucz przy pierwszym uruchomieniu.

        Dzięki zapisowi do pliku w wolumenie sesje użytkowników przeżywają restart
        kontenera nawet wtedy, gdy administrator nie ustawił QUIZAPP_SECRET_KEY.
        """
        if self.secret_key:
            return self.secret_key

        self.ensure_directories()
        key_file = self.data_dir / ".secret_key"
        if key_file.exists():
            stored = key_file.read_text(encoding="utf-8").strip()
            if stored:
                self.secret_key = stored
                return stored

        generated = secrets.token_urlsafe(64)
        key_file.write_text(generated, encoding="utf-8")
        try:
            key_file.chmod(0o600)
        except OSError:  # pragma: no cover - zależne od systemu plików
            pass
        self.secret_key = generated
        return generated


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    settings.resolve_secret_key()
    return settings


settings = get_settings()

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
