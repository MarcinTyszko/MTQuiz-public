"""Logika biznesowa: tworzenie i serializacja zestawów, tagi, ulubione, statystyki."""
from __future__ import annotations

import re
import unicodedata
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .models import (
    AnswerOption,
    AuditLog,
    CardStar,
    Favorite,
    Flashcard,
    Question,
    SetTag,
    StudySession,
    StudySet,
    Tag,
    User,
    Visibility,
    utcnow,
)
from .schemas import (
    AnswerOptionOut,
    DashboardStats,
    FlashcardOut,
    QuestionOut,
    StudySetCreate,
    StudySetDetail,
    StudySetSummary,
)


def slugify(value: str) -> str:
    """Tworzy identyfikator tagu odporny na polskie znaki diakrytyczne."""
    text = unicodedata.normalize("NFKD", value.strip().lower())
    text = text.replace("ł", "l").replace("Ł", "l")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:64] or "tag"


def get_or_create_tag(db: Session, name: str) -> Tag:
    slug = slugify(name)
    tag = db.scalar(select(Tag).where(Tag.slug == slug))
    if tag is None:
        tag = Tag(name=name.strip()[:64], slug=slug)
        db.add(tag)
        db.flush()
    return tag


def set_tags(db: Session, study_set: StudySet, tags: list[str]) -> None:
    """Ustawia dokładnie podaną listę tagów dla zestawu."""
    for link in list(study_set.tag_links):
        db.delete(link)
    study_set.tag_links = []
    db.flush()

    seen: set[str] = set()
    for name in tags:
        cleaned = " ".join(str(name).split())[:64]
        if not cleaned:
            continue
        slug = slugify(cleaned)
        if slug in seen:
            continue
        seen.add(slug)
        tag = get_or_create_tag(db, cleaned)
        db.add(SetTag(study_set=study_set, tag=tag))
    db.flush()


def replace_content(db: Session, study_set: StudySet, payload: StudySetCreate) -> None:
    """Zastępuje fiszki i pytania zestawu treścią z przesłanego ładunku.

    Elementy z istniejącym ``id`` są aktualizowane w miejscu, dzięki czemu
    oznaczenia „trudna fiszka” oraz historia nauki nie giną przy zapisie edytora.
    Przypisanie nowej listy do relacji powoduje, że kaskada ``delete-orphan``
    usuwa elementy nieobecne w ładunku.
    """
    existing_cards = {card.id: card for card in study_set.cards}
    new_cards: list[Flashcard] = []
    for position, card_in in enumerate(payload.cards):
        card = existing_cards.get(card_in.id) if card_in.id else None
        if card is None:
            card = Flashcard()
        card.front = card_in.front
        card.back = card_in.back
        card.hint = card_in.hint
        card.note = card_in.note
        card.position = position
        new_cards.append(card)
    study_set.cards = new_cards

    existing_questions = {question.id: question for question in study_set.questions}
    new_questions: list[Question] = []
    for position, question_in in enumerate(payload.questions):
        question = existing_questions.get(question_in.id) if question_in.id else None
        if question is None:
            question = Question()
        question.prompt = question_in.prompt
        question.explanation = question_in.explanation
        question.multiple = question_in.multiple
        question.position = position
        # Warianty odpowiedzi odtwarzamy w całości — są tanie i nie niosą stanu użytkownika.
        question.options = [
            AnswerOption(
                text=option_in.text,
                is_correct=option_in.is_correct,
                feedback=option_in.feedback,
                position=option_position,
            )
            for option_position, option_in in enumerate(question_in.options)
        ]
        new_questions.append(question)
    study_set.questions = new_questions

    db.flush()
    study_set.updated_at = utcnow()


def create_study_set(db: Session, author: User, payload: StudySetCreate) -> StudySet:
    study_set = StudySet(
        title=payload.title,
        description=payload.description,
        subject=payload.subject,
        visibility=payload.visibility,
        author=author,
        is_published=True,
    )
    db.add(study_set)
    db.flush()
    set_tags(db, study_set, payload.tags)
    replace_content(db, study_set, payload)
    db.flush()
    return study_set


def fork_study_set(db: Session, source: StudySet, user: User) -> StudySet:
    """Tworzy prywatną kopię zestawu w bibliotece użytkownika."""
    clone = StudySet(
        title=f"{source.title} (kopia)"[:200],
        description=source.description,
        subject=source.subject,
        visibility=Visibility.PRIVATE,
        author=user,
        forked_from_id=source.id,
        is_published=True,
    )
    db.add(clone)
    db.flush()
    set_tags(db, clone, source.tags)

    for card in sorted(source.cards, key=lambda item: item.position):
        db.add(
            Flashcard(
                study_set=clone,
                front=card.front,
                back=card.back,
                hint=card.hint,
                note=card.note,
                position=card.position,
            )
        )
    for question in sorted(source.questions, key=lambda item: item.position):
        clone_question = Question(
            study_set=clone,
            prompt=question.prompt,
            explanation=question.explanation,
            multiple=question.multiple,
            position=question.position,
        )
        db.add(clone_question)
        db.flush()
        for option in sorted(question.options, key=lambda item: item.position):
            db.add(
                AnswerOption(
                    question=clone_question,
                    text=option.text,
                    is_correct=option.is_correct,
                    feedback=option.feedback,
                    position=option.position,
                )
            )

    source.fork_count += 1
    db.flush()
    return clone


def set_query_with_relations():
    """Zapytanie bazowe z dociągniętymi relacjami (unika problemu N+1)."""
    return select(StudySet).options(
        selectinload(StudySet.author),
        selectinload(StudySet.tag_links).selectinload(SetTag.tag),
        selectinload(StudySet.cards),
        selectinload(StudySet.questions).selectinload(Question.options),
    )


def counts_for_sets(db: Session, set_ids: list[int]) -> dict[int, dict[str, int]]:
    """Zwraca liczniki fiszek, pytań i polubień dla podanych zestawów."""
    result: dict[int, dict[str, int]] = {
        set_id: {"cards": 0, "questions": 0, "favorites": 0} for set_id in set_ids
    }
    if not set_ids:
        return result

    for set_id, total in db.execute(
        select(Flashcard.set_id, func.count(Flashcard.id))
        .where(Flashcard.set_id.in_(set_ids))
        .group_by(Flashcard.set_id)
    ):
        result[set_id]["cards"] = total
    for set_id, total in db.execute(
        select(Question.set_id, func.count(Question.id))
        .where(Question.set_id.in_(set_ids))
        .group_by(Question.set_id)
    ):
        result[set_id]["questions"] = total
    for set_id, total in db.execute(
        select(Favorite.set_id, func.count(Favorite.id))
        .where(Favorite.set_id.in_(set_ids))
        .group_by(Favorite.set_id)
    ):
        result[set_id]["favorites"] = total
    return result


def favorite_ids(db: Session, user: User | None, set_ids: list[int]) -> set[int]:
    if user is None or not set_ids:
        return set()
    rows = db.scalars(
        select(Favorite.set_id).where(Favorite.user_id == user.id, Favorite.set_id.in_(set_ids))
    )
    return set(rows)


def to_summary(
    study_set: StudySet,
    *,
    counts: dict[str, int] | None = None,
    is_favorite: bool = False,
    viewer: User | None = None,
) -> StudySetSummary:
    counts = counts or {}
    return StudySetSummary(
        id=study_set.id,
        title=study_set.title,
        description=study_set.description,
        subject=study_set.subject,
        visibility=study_set.visibility,
        is_published=study_set.is_published,
        tags=study_set.tags,
        author_id=study_set.author_id,
        author_username=study_set.author.username if study_set.author else "—",
        cards_count=counts.get("cards", len(study_set.cards)),
        questions_count=counts.get("questions", len(study_set.questions)),
        favorites_count=counts.get("favorites", len(study_set.favorites)),
        fork_count=study_set.fork_count,
        view_count=study_set.view_count,
        forked_from_id=study_set.forked_from_id,
        is_favorite=is_favorite,
        is_owner=bool(viewer and viewer.id == study_set.author_id),
        created_at=study_set.created_at,
        updated_at=study_set.updated_at,
    )


def to_detail(
    db: Session,
    study_set: StudySet,
    *,
    viewer: User | None = None,
    is_favorite: bool = False,
) -> StudySetDetail:
    starred: set[int] = set()
    if viewer is not None:
        card_ids = [card.id for card in study_set.cards]
        if card_ids:
            starred = set(
                db.scalars(
                    select(CardStar.card_id).where(
                        CardStar.user_id == viewer.id, CardStar.card_id.in_(card_ids)
                    )
                )
            )

    summary = to_summary(study_set, is_favorite=is_favorite, viewer=viewer)
    return StudySetDetail(
        **summary.model_dump(),
        moderation_note=study_set.moderation_note,
        cards=[
            FlashcardOut(
                id=card.id,
                front=card.front,
                back=card.back,
                hint=card.hint,
                note=card.note,
                position=card.position,
                starred=card.id in starred,
            )
            for card in sorted(study_set.cards, key=lambda item: item.position)
        ],
        questions=[
            QuestionOut(
                id=question.id,
                prompt=question.prompt,
                explanation=question.explanation,
                multiple=question.multiple,
                position=question.position,
                options=[
                    AnswerOptionOut(
                        id=option.id,
                        text=option.text,
                        is_correct=option.is_correct,
                        feedback=option.feedback,
                        position=option.position,
                    )
                    for option in sorted(question.options, key=lambda item: item.position)
                ],
            )
            for question in sorted(study_set.questions, key=lambda item: item.position)
        ],
    )


def can_view(study_set: StudySet, user: User | None) -> bool:
    if study_set.visibility == Visibility.PUBLIC and study_set.is_published:
        return True
    if user is None:
        return False
    return user.id == study_set.author_id or user.is_admin


def can_edit(study_set: StudySet, user: User | None) -> bool:
    if user is None:
        return False
    return user.id == study_set.author_id or user.is_admin


def dashboard_stats(db: Session, user: User) -> DashboardStats:
    owned_ids = list(db.scalars(select(StudySet.id).where(StudySet.author_id == user.id)))
    cards_total = 0
    questions_total = 0
    if owned_ids:
        cards_total = db.scalar(select(func.count(Flashcard.id)).where(Flashcard.set_id.in_(owned_ids))) or 0
        questions_total = db.scalar(select(func.count(Question.id)).where(Question.set_id.in_(owned_ids))) or 0

    favorites = db.scalar(select(func.count(Favorite.id)).where(Favorite.user_id == user.id)) or 0
    starred = db.scalar(select(func.count(CardStar.id)).where(CardStar.user_id == user.id)) or 0

    since = utcnow() - timedelta(days=30)
    recent_sessions = list(
        db.scalars(
            select(StudySession).where(StudySession.user_id == user.id, StudySession.created_at >= since)
        )
    )
    scored = [session for session in recent_sessions if session.total > 0]
    average = round(sum(s.score / s.total for s in scored) * 100 / len(scored), 1) if scored else 0.0

    return DashboardStats(
        sets_owned=len(owned_ids),
        cards_total=cards_total,
        questions_total=questions_total,
        favorites=favorites,
        sessions_last_30_days=len(recent_sessions),
        average_accuracy=average,
        starred_cards=starred,
    )


def log_action(db: Session, actor: User | None, action: str, detail: str = "") -> None:
    """Zapisuje wpis w dzienniku administracyjnym."""
    db.add(
        AuditLog(
            actor_id=actor.id if actor else None,
            actor_label=actor.username if actor else "system",
            action=action,
            detail=detail[:4000],
        )
    )
