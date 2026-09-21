"""Schematy Pydantic: walidacja wejścia API i serializacja odpowiedzi."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from .models import StudyMode, UserRole, Visibility

NonEmptyStr = Annotated[str, Field(min_length=1)]


# --------------------------------------------------------------------------- #
# Uwierzytelnianie
# --------------------------------------------------------------------------- #
class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=8, max_length=256)
    email: EmailStr | None = None
    display_name: str | None = Field(default=None, max_length=120)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    remember: bool = True


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str | None = None
    display_name: str | None = None
    role: UserRole
    is_active: bool
    must_change_password: bool
    created_at: datetime
    last_login_at: datetime | None = None


class UserAdminOut(UserOut):
    sets_count: int = 0
    public_sets_count: int = 0
    sessions_count: int = 0


# --------------------------------------------------------------------------- #
# Treść zestawów
# --------------------------------------------------------------------------- #
class FlashcardIn(BaseModel):
    id: int | None = None
    front: str = Field(min_length=1, max_length=8000)
    back: str = Field(min_length=1, max_length=20000)
    hint: str | None = Field(default=None, max_length=4000)
    note: str | None = Field(default=None, max_length=8000)

    @field_validator("front", "back", mode="before")
    @classmethod
    def _strip_required(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("hint", "note", mode="before")
    @classmethod
    def _strip_optional(cls, value: object) -> object:
        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned or None
        return value


class FlashcardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    front: str
    back: str
    hint: str | None = None
    note: str | None = None
    position: int
    starred: bool = False


class AnswerOptionIn(BaseModel):
    id: int | None = None
    text: str = Field(min_length=1, max_length=4000)
    is_correct: bool = False
    feedback: str | None = Field(default=None, max_length=4000)

    @field_validator("text", mode="before")
    @classmethod
    def _strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("feedback", mode="before")
    @classmethod
    def _strip_feedback(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip() or None
        return value


class AnswerOptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    text: str
    is_correct: bool
    feedback: str | None = None
    position: int


class QuestionIn(BaseModel):
    id: int | None = None
    prompt: str = Field(min_length=1, max_length=8000)
    explanation: str | None = Field(default=None, max_length=20000)
    options: list[AnswerOptionIn] = Field(min_length=2, max_length=10)

    @field_validator("prompt", mode="before")
    @classmethod
    def _strip_prompt(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("explanation", mode="before")
    @classmethod
    def _strip_explanation(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip() or None
        return value

    @model_validator(mode="after")
    def _at_least_one_correct(self) -> "QuestionIn":
        if not any(option.is_correct for option in self.options):
            raise ValueError("Pytanie musi mieć co najmniej jedną poprawną odpowiedź.")
        return self

    @property
    def multiple(self) -> bool:
        return sum(1 for option in self.options if option.is_correct) > 1


class QuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    prompt: str
    explanation: str | None = None
    multiple: bool
    position: int
    options: list[AnswerOptionOut]


class StudySetBase(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    subject: str = Field(default="", max_length=120)
    visibility: Visibility = Visibility.PRIVATE
    tags: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("title", "subject", mode="before")
    @classmethod
    def _strip(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("description", mode="before")
    @classmethod
    def _strip_description(cls, value: object) -> object:
        if value is None:
            return ""
        return value.strip() if isinstance(value, str) else value

    @field_validator("tags", mode="before")
    @classmethod
    def _normalise_tags(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, str):
            value = [part for part in value.replace(";", ",").split(",")]
        if not isinstance(value, list):
            return value
        cleaned: list[str] = []
        seen: set[str] = set()
        for item in value:
            if not isinstance(item, str):
                continue
            tag = " ".join(item.split())[:64]
            key = tag.casefold()
            if tag and key not in seen:
                seen.add(key)
                cleaned.append(tag)
        return cleaned[:20]


class StudySetCreate(StudySetBase):
    cards: list[FlashcardIn] = Field(default_factory=list)
    questions: list[QuestionIn] = Field(default_factory=list)

    @model_validator(mode="after")
    def _not_empty(self) -> "StudySetCreate":
        if not self.cards and not self.questions:
            raise ValueError("Zestaw musi zawierać przynajmniej jedną fiszkę lub jedno pytanie quizowe.")
        return self


class StudySetUpdate(StudySetCreate):
    """Pełna aktualizacja zestawu (zastępuje listę fiszek i pytań)."""


class StudySetMetaUpdate(StudySetBase):
    """Aktualizacja wyłącznie metadanych, bez ruszania treści."""


class StudySetSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    subject: str
    visibility: Visibility
    is_published: bool
    tags: list[str] = Field(default_factory=list)
    author_id: int
    author_username: str
    cards_count: int = 0
    questions_count: int = 0
    favorites_count: int = 0
    fork_count: int = 0
    view_count: int = 0
    forked_from_id: int | None = None
    is_favorite: bool = False
    is_owner: bool = False
    created_at: datetime
    updated_at: datetime


class StudySetDetail(StudySetSummary):
    cards: list[FlashcardOut] = Field(default_factory=list)
    questions: list[QuestionOut] = Field(default_factory=list)
    moderation_note: str | None = None


# --------------------------------------------------------------------------- #
# Nauka
# --------------------------------------------------------------------------- #
class StudySessionIn(BaseModel):
    set_id: int
    mode: StudyMode
    score: int = Field(default=0, ge=0)
    total: int = Field(default=0, ge=0)
    duration_seconds: int = Field(default=0, ge=0, le=60 * 60 * 24)

    @model_validator(mode="after")
    def _score_within_total(self) -> "StudySessionIn":
        if self.score > self.total:
            raise ValueError("Liczba poprawnych odpowiedzi nie może przekraczać liczby pytań.")
        return self


class StudySessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    set_id: int
    set_title: str = ""
    mode: StudyMode
    score: int
    total: int
    duration_seconds: int
    accuracy: float = 0.0
    created_at: datetime


class DashboardStats(BaseModel):
    sets_owned: int = 0
    cards_total: int = 0
    questions_total: int = 0
    favorites: int = 0
    sessions_last_30_days: int = 0
    average_accuracy: float = 0.0
    starred_cards: int = 0


# --------------------------------------------------------------------------- #
# Administracja
# --------------------------------------------------------------------------- #
class AdminUserUpdate(BaseModel):
    is_active: bool | None = None
    role: UserRole | None = None
    must_change_password: bool | None = None
    display_name: str | None = Field(default=None, max_length=120)


class AdminPasswordReset(BaseModel):
    new_password: str | None = Field(default=None, min_length=8, max_length=256)


class AdminSetModeration(BaseModel):
    is_published: bool | None = None
    visibility: Visibility | None = None
    moderation_note: str | None = Field(default=None, max_length=2000)


class AdminStats(BaseModel):
    users_total: int = 0
    users_active: int = 0
    admins: int = 0
    sets_total: int = 0
    sets_public: int = 0
    sets_unpublished: int = 0
    cards_total: int = 0
    questions_total: int = 0
    sessions_total: int = 0
    database_size_bytes: int = 0
    database_path: str = ""


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_label: str
    action: str
    detail: str
    created_at: datetime


# --------------------------------------------------------------------------- #
# Import / eksport
# --------------------------------------------------------------------------- #
class ImportIssue(BaseModel):
    severity: Literal["error", "warning"]
    path: str
    message: str


class ImportPreview(BaseModel):
    ok: bool
    issues: list[ImportIssue] = Field(default_factory=list)
    payload: StudySetCreate | None = None
    stats: dict[str, int] = Field(default_factory=dict)


class ImportRequest(BaseModel):
    """Import z surowego JSON-a przesłanego jako tekst lub obiekt."""

    data: dict | list | str
    visibility: Visibility | None = None


class MessageOut(BaseModel):
    ok: bool = True
    message: str = ""
