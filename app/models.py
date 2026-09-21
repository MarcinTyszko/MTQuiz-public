"""Modele ORM platformy MTQuiz."""
from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    """Zwraca bieżący czas UTC (świadomy strefy)."""
    return datetime.now(timezone.utc)


class UserRole(str, enum.Enum):
    USER = "user"
    ADMIN = "admin"


class Visibility(str, enum.Enum):
    PRIVATE = "private"
    PUBLIC = "public"


class StudyMode(str, enum.Enum):
    FLASHCARDS = "flashcards"
    QUIZ = "quiz"


class TranscriptionStatus(str, enum.Enum):
    """Stan zadania transkrypcji — wspólny dla aplikacji i procesu liczącego."""

    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, native_enum=False), default=UserRole.USER, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    sets: Mapped[list["StudySet"]] = relationship(
        back_populates="author", cascade="all, delete-orphan", passive_deletes=True
    )
    favorites: Mapped[list["Favorite"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    sessions: Mapped[list["StudySession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    card_stars: Mapped[list["CardStar"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    transcriptions: Mapped[list["Transcription"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN

    @property
    def label(self) -> str:
        return self.display_name or self.username


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)

    links: Mapped[list["SetTag"]] = relationship(
        back_populates="tag", cascade="all, delete-orphan", passive_deletes=True
    )


class SetTag(Base):
    """Powiązanie zestawu z tagiem (jawny model dla prostych zapytań i kaskad)."""

    __tablename__ = "set_tags"
    __table_args__ = (UniqueConstraint("set_id", "tag_id", name="uq_set_tag"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    set_id: Mapped[int] = mapped_column(ForeignKey("study_sets.id", ondelete="CASCADE"), index=True, nullable=False)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), index=True, nullable=False)

    study_set: Mapped["StudySet"] = relationship(back_populates="tag_links")
    tag: Mapped["Tag"] = relationship(back_populates="links")


class StudySet(Base):
    """Teczka nauki — kontener na fiszki i pytania quizowe."""

    __tablename__ = "study_sets"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    subject: Mapped[str] = mapped_column(String(120), default="", nullable=False, index=True)
    visibility: Mapped[Visibility] = mapped_column(
        Enum(Visibility, native_enum=False), default=Visibility.PRIVATE, nullable=False, index=True
    )
    # Flaga moderacyjna: administrator może zdjąć zestaw z bazy publicznej.
    is_published: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    moderation_note: Mapped[str | None] = mapped_column(Text)

    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    forked_from_id: Mapped[int | None] = mapped_column(ForeignKey("study_sets.id", ondelete="SET NULL"), index=True)

    view_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    fork_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False, index=True
    )

    author: Mapped["User"] = relationship(back_populates="sets")
    forked_from: Mapped["StudySet | None"] = relationship(remote_side="StudySet.id")
    cards: Mapped[list["Flashcard"]] = relationship(
        back_populates="study_set",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Flashcard.position",
    )
    questions: Mapped[list["Question"]] = relationship(
        back_populates="study_set",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Question.position",
    )
    tag_links: Mapped[list["SetTag"]] = relationship(
        back_populates="study_set", cascade="all, delete-orphan", passive_deletes=True
    )
    favorites: Mapped[list["Favorite"]] = relationship(
        back_populates="study_set", cascade="all, delete-orphan", passive_deletes=True
    )
    sessions: Mapped[list["StudySession"]] = relationship(
        back_populates="study_set", cascade="all, delete-orphan", passive_deletes=True
    )

    @property
    def tags(self) -> list[str]:
        return [link.tag.name for link in self.tag_links]

    @property
    def is_public(self) -> bool:
        return self.visibility == Visibility.PUBLIC and self.is_published


class Flashcard(Base):
    __tablename__ = "flashcards"

    id: Mapped[int] = mapped_column(primary_key=True)
    set_id: Mapped[int] = mapped_column(ForeignKey("study_sets.id", ondelete="CASCADE"), index=True, nullable=False)
    front: Mapped[str] = mapped_column(Text, nullable=False)
    back: Mapped[str] = mapped_column(Text, nullable=False)
    hint: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    study_set: Mapped["StudySet"] = relationship(back_populates="cards")
    stars: Mapped[list["CardStar"]] = relationship(
        back_populates="card", cascade="all, delete-orphan", passive_deletes=True
    )


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    set_id: Mapped[int] = mapped_column(ForeignKey("study_sets.id", ondelete="CASCADE"), index=True, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text)
    # True, gdy poprawnych odpowiedzi jest więcej niż jedna (wybór wielokrotny).
    multiple: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    study_set: Mapped["StudySet"] = relationship(back_populates="questions")
    options: Mapped[list["AnswerOption"]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="AnswerOption.position",
    )


class AnswerOption(Base):
    __tablename__ = "answer_options"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), index=True, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    feedback: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    question: Mapped["Question"] = relationship(back_populates="options")

    @property
    def letter(self) -> str:
        return chr(ord("A") + self.position)


class Favorite(Base):
    __tablename__ = "favorites"
    __table_args__ = (UniqueConstraint("user_id", "set_id", name="uq_favorite"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    set_id: Mapped[int] = mapped_column(ForeignKey("study_sets.id", ondelete="CASCADE"), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    user: Mapped["User"] = relationship(back_populates="favorites")
    study_set: Mapped["StudySet"] = relationship(back_populates="favorites")


class CardStar(Base):
    """Oznaczenie fiszki jako trudnej — indywidualnie dla użytkownika."""

    __tablename__ = "card_stars"
    __table_args__ = (UniqueConstraint("user_id", "card_id", name="uq_card_star"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    card_id: Mapped[int] = mapped_column(ForeignKey("flashcards.id", ondelete="CASCADE"), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    user: Mapped["User"] = relationship(back_populates="card_stars")
    card: Mapped["Flashcard"] = relationship(back_populates="stars")


class StudySession(Base):
    """Zapis pojedynczej sesji nauki — zasila statystyki i historię aktywności."""

    __tablename__ = "study_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    set_id: Mapped[int] = mapped_column(ForeignKey("study_sets.id", ondelete="CASCADE"), index=True, nullable=False)
    mode: Mapped[StudyMode] = mapped_column(Enum(StudyMode, native_enum=False), nullable=False)
    score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)

    user: Mapped["User"] = relationship(back_populates="sessions")
    study_set: Mapped["StudySet"] = relationship(back_populates="sessions")

    @property
    def accuracy(self) -> float:
        return round(100 * self.score / self.total, 1) if self.total else 0.0


class Transcription(Base):
    """Nagranie zgłoszone do transkrypcji wraz z jej wynikiem.

    Plik audio i wynik pracy procesu liczącego leżą w katalogu
    ``/data/transkrypcje/<id>``; tutaj trzymamy metadane, stan i gotowy tekst,
    dzięki czemu pobieranie i podgląd nie zależą od obecności procesu roboczego.
    """

    __tablename__ = "transcriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    language: Mapped[str] = mapped_column(String(8), default="pl", nullable=False)
    model_name: Mapped[str] = mapped_column(String(40), default="large-v3", nullable=False)

    status: Mapped[TranscriptionStatus] = mapped_column(
        Enum(TranscriptionStatus, native_enum=False), default=TranscriptionStatus.QUEUED, nullable=False, index=True
    )
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    message: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)

    text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    segments_json: Mapped[str | None] = mapped_column(Text)
    segments_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(back_populates="transcriptions")

    @property
    def is_finished(self) -> bool:
        return self.status in (TranscriptionStatus.DONE, TranscriptionStatus.ERROR)

    @property
    def word_count(self) -> int:
        return len(self.text.split()) if self.text else 0


class AuditLog(Base):
    """Dziennik działań administracyjnych (moderacja, kopie zapasowe, konta)."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    actor_label: Mapped[str] = mapped_column(String(64), default="system", nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    detail: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)


Index("ix_study_sets_public_feed", StudySet.visibility, StudySet.is_published, StudySet.updated_at)
Index("ix_flashcards_set_position", Flashcard.set_id, Flashcard.position)
Index("ix_questions_set_position", Question.set_id, Question.position)

__all__ = [
    "AnswerOption",
    "AuditLog",
    "Base",
    "CardStar",
    "Favorite",
    "Flashcard",
    "Question",
    "SetTag",
    "StudyMode",
    "StudySession",
    "StudySet",
    "Tag",
    "Transcription",
    "TranscriptionStatus",
    "User",
    "UserRole",
    "Visibility",
    "utcnow",
]
