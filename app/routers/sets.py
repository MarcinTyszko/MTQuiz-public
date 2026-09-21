"""Endpointy zarządzania zestawami nauki, importem i eksportem."""
from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from fastapi.responses import JSONResponse, Response
from sqlalchemy import func, or_, select

from ..config import settings
from ..deps import DbSession, OptionalUser, UnlockedUser
from ..importer import export_payload, normalise_payload
from ..models import (
    CardStar,
    Favorite,
    Flashcard,
    SetTag,
    StudySet,
    Tag,
    Visibility,
)
from ..schemas import (
    ImportPreview,
    ImportRequest,
    MessageOut,
    StudySetCreate,
    StudySetDetail,
    StudySetSummary,
    StudySetUpdate,
)
from ..services import (
    can_edit,
    can_view,
    counts_for_sets,
    create_study_set,
    favorite_ids,
    fork_study_set,
    log_action,
    replace_content,
    set_query_with_relations,
    set_tags,
    to_detail,
    to_summary,
)

router = APIRouter(prefix="/api", tags=["sets"])

SortKey = Literal["newest", "oldest", "popular", "alpha", "updated"]


def _load_set(db, set_id: int) -> StudySet:
    study_set = db.scalar(set_query_with_relations().where(StudySet.id == set_id))
    if study_set is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nie znaleziono zestawu.")
    return study_set


def _apply_sort(stmt, sort: SortKey):
    if sort == "oldest":
        return stmt.order_by(StudySet.created_at.asc())
    if sort == "alpha":
        return stmt.order_by(func.lower(StudySet.title).asc())
    if sort == "updated":
        return stmt.order_by(StudySet.updated_at.desc())
    if sort == "popular":
        return stmt.order_by(StudySet.fork_count.desc(), StudySet.view_count.desc(), StudySet.updated_at.desc())
    return stmt.order_by(StudySet.created_at.desc())


def _summaries(db, rows: list[StudySet], viewer) -> list[StudySetSummary]:
    ids = [row.id for row in rows]
    counts = counts_for_sets(db, ids)
    favourites = favorite_ids(db, viewer, ids)
    return [
        to_summary(row, counts=counts.get(row.id), is_favorite=row.id in favourites, viewer=viewer)
        for row in rows
    ]


# --------------------------------------------------------------------------- #
# Biblioteka użytkownika
# --------------------------------------------------------------------------- #
@router.get("/sets", response_model=list[StudySetSummary])
def list_my_sets(
    user: UnlockedUser,
    db: DbSession,
    q: str = Query(default="", max_length=120),
    sort: SortKey = "updated",
    visibility: Visibility | None = None,
) -> list[StudySetSummary]:
    stmt = set_query_with_relations().where(StudySet.author_id == user.id)
    if q.strip():
        needle = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(StudySet.title).like(needle),
                func.lower(StudySet.description).like(needle),
                func.lower(StudySet.subject).like(needle),
            )
        )
    if visibility is not None:
        stmt = stmt.where(StudySet.visibility == visibility)
    rows = list(db.scalars(_apply_sort(stmt, sort)).unique())
    return _summaries(db, rows, user)


@router.get("/sets/favorites", response_model=list[StudySetSummary])
def list_favorites(user: UnlockedUser, db: DbSession) -> list[StudySetSummary]:
    stmt = (
        set_query_with_relations()
        .join(Favorite, Favorite.set_id == StudySet.id)
        .where(Favorite.user_id == user.id)
        .order_by(Favorite.created_at.desc())
    )
    rows = list(db.scalars(stmt).unique())
    return _summaries(db, rows, user)


@router.get("/sets/{set_id}", response_model=StudySetDetail)
def get_set(set_id: int, db: DbSession, user: OptionalUser) -> StudySetDetail:
    study_set = _load_set(db, set_id)
    if not can_view(study_set, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Ten zestaw jest prywatny.")
    is_favorite = bool(favorite_ids(db, user, [study_set.id]))
    return to_detail(db, study_set, viewer=user, is_favorite=is_favorite)


@router.post("/sets", response_model=StudySetDetail, status_code=status.HTTP_201_CREATED)
def create_set(payload: StudySetCreate, user: UnlockedUser, db: DbSession) -> StudySetDetail:
    if len(payload.cards) > settings.max_cards_per_set or len(payload.questions) > settings.max_questions_per_set:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Zestaw jest zbyt duży.")
    study_set = create_study_set(db, user, payload)
    log_action(db, user, "set.create", f"Utworzono zestaw #{study_set.id} „{study_set.title}”.")
    db.commit()
    study_set = _load_set(db, study_set.id)
    return to_detail(db, study_set, viewer=user)


@router.put("/sets/{set_id}", response_model=StudySetDetail)
def update_set(set_id: int, payload: StudySetUpdate, user: UnlockedUser, db: DbSession) -> StudySetDetail:
    study_set = _load_set(db, set_id)
    if not can_edit(study_set, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Brak uprawnień do edycji tego zestawu.")

    study_set.title = payload.title
    study_set.description = payload.description
    study_set.subject = payload.subject
    study_set.visibility = payload.visibility
    set_tags(db, study_set, payload.tags)
    replace_content(db, study_set, payload)
    log_action(db, user, "set.update", f"Zaktualizowano zestaw #{study_set.id}.")
    db.commit()

    study_set = _load_set(db, set_id)
    is_favorite = bool(favorite_ids(db, user, [set_id]))
    return to_detail(db, study_set, viewer=user, is_favorite=is_favorite)


@router.delete("/sets/{set_id}", response_model=MessageOut)
def delete_set(set_id: int, user: UnlockedUser, db: DbSession) -> MessageOut:
    study_set = _load_set(db, set_id)
    if not can_edit(study_set, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Brak uprawnień do usunięcia zestawu.")
    title = study_set.title
    db.delete(study_set)
    log_action(db, user, "set.delete", f"Usunięto zestaw #{set_id} „{title}”.")
    db.commit()
    return MessageOut(ok=True, message=f"Zestaw „{title}” został usunięty.")


@router.post("/sets/{set_id}/fork", response_model=StudySetDetail, status_code=status.HTTP_201_CREATED)
def fork_set(set_id: int, user: UnlockedUser, db: DbSession) -> StudySetDetail:
    source = _load_set(db, set_id)
    if not can_view(source, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Ten zestaw jest prywatny.")
    if source.author_id == user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="To już jest Twój zestaw.")

    clone = fork_study_set(db, source, user)
    log_action(db, user, "set.fork", f"Skopiowano zestaw #{source.id} jako #{clone.id}.")
    db.commit()
    clone = _load_set(db, clone.id)
    return to_detail(db, clone, viewer=user)


# --------------------------------------------------------------------------- #
# Ulubione i oznaczanie trudnych fiszek
# --------------------------------------------------------------------------- #
@router.post("/sets/{set_id}/favorite", response_model=MessageOut)
def add_favorite(set_id: int, user: UnlockedUser, db: DbSession) -> MessageOut:
    study_set = _load_set(db, set_id)
    if not can_view(study_set, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Ten zestaw jest prywatny.")
    existing = db.scalar(select(Favorite).where(Favorite.user_id == user.id, Favorite.set_id == set_id))
    if existing is None:
        db.add(Favorite(user_id=user.id, set_id=set_id))
        db.commit()
    return MessageOut(ok=True, message="Dodano do ulubionych.")


@router.delete("/sets/{set_id}/favorite", response_model=MessageOut)
def remove_favorite(set_id: int, user: UnlockedUser, db: DbSession) -> MessageOut:
    existing = db.scalar(select(Favorite).where(Favorite.user_id == user.id, Favorite.set_id == set_id))
    if existing is not None:
        db.delete(existing)
        db.commit()
    return MessageOut(ok=True, message="Usunięto z ulubionych.")


@router.post("/cards/{card_id}/star", response_model=MessageOut)
def toggle_star(card_id: int, user: UnlockedUser, db: DbSession) -> MessageOut:
    card = db.get(Flashcard, card_id)
    if card is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nie znaleziono fiszki.")
    study_set = _load_set(db, card.set_id)
    if not can_view(study_set, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Ten zestaw jest prywatny.")

    existing = db.scalar(select(CardStar).where(CardStar.user_id == user.id, CardStar.card_id == card_id))
    if existing is None:
        db.add(CardStar(user_id=user.id, card_id=card_id))
        db.commit()
        return MessageOut(ok=True, message="Oznaczono jako trudną.")
    db.delete(existing)
    db.commit()
    return MessageOut(ok=False, message="Usunięto oznaczenie.")


# --------------------------------------------------------------------------- #
# Baza publiczna
# --------------------------------------------------------------------------- #
@router.get("/public/sets", response_model=list[StudySetSummary])
def public_feed(
    db: DbSession,
    user: OptionalUser,
    q: str = Query(default="", max_length=120),
    tag: str = Query(default="", max_length=64),
    subject: str = Query(default="", max_length=120),
    sort: SortKey = "newest",
    limit: int = Query(default=48, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[StudySetSummary]:
    stmt = set_query_with_relations().where(
        StudySet.visibility == Visibility.PUBLIC, StudySet.is_published.is_(True)
    )
    if q.strip():
        needle = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(StudySet.title).like(needle),
                func.lower(StudySet.description).like(needle),
                func.lower(StudySet.subject).like(needle),
            )
        )
    if subject.strip():
        stmt = stmt.where(func.lower(StudySet.subject) == subject.strip().lower())
    if tag.strip():
        stmt = (
            stmt.join(SetTag, SetTag.set_id == StudySet.id)
            .join(Tag, Tag.id == SetTag.tag_id)
            .where(func.lower(Tag.name) == tag.strip().lower())
        )

    if sort == "popular":
        favourite_counts = (
            select(Favorite.set_id, func.count(Favorite.id).label("total"))
            .group_by(Favorite.set_id)
            .subquery()
        )
        stmt = stmt.outerjoin(favourite_counts, favourite_counts.c.set_id == StudySet.id).order_by(
            func.coalesce(favourite_counts.c.total, 0).desc(),
            StudySet.fork_count.desc(),
            StudySet.view_count.desc(),
        )
    else:
        stmt = _apply_sort(stmt, sort)

    rows = list(db.scalars(stmt.limit(limit).offset(offset)).unique())
    return _summaries(db, rows, user)


@router.get("/public/tags", response_model=list[dict])
def public_tags(db: DbSession, limit: int = Query(default=40, ge=1, le=200)) -> list[dict]:
    """Najczęściej używane tagi zestawów publicznych — zasila filtry w widoku „Baza publiczna”."""
    stmt = (
        select(Tag.name, func.count(SetTag.id).label("total"))
        .join(SetTag, SetTag.tag_id == Tag.id)
        .join(StudySet, StudySet.id == SetTag.set_id)
        .where(StudySet.visibility == Visibility.PUBLIC, StudySet.is_published.is_(True))
        .group_by(Tag.id)
        .order_by(func.count(SetTag.id).desc(), Tag.name.asc())
        .limit(limit)
    )
    return [{"name": name, "count": total} for name, total in db.execute(stmt)]


@router.post("/sets/{set_id}/view", response_model=MessageOut)
def register_view(set_id: int, db: DbSession, user: OptionalUser) -> MessageOut:
    study_set = db.get(StudySet, set_id)
    if study_set is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nie znaleziono zestawu.")
    if not can_view(study_set, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Ten zestaw jest prywatny.")
    if user is None or user.id != study_set.author_id:
        study_set.view_count += 1
        db.commit()
    return MessageOut(ok=True, message="")


# --------------------------------------------------------------------------- #
# Import / eksport
# --------------------------------------------------------------------------- #
@router.post("/import/validate", response_model=ImportPreview)
def validate_import(payload: ImportRequest, user: UnlockedUser) -> ImportPreview:
    """Walidacja „na sucho” — zwraca podgląd zestawu i listę uwag bez zapisu."""
    return normalise_payload(payload.data, default_visibility=payload.visibility)


@router.post("/import/upload", response_model=ImportPreview)
async def validate_uploaded_file(user: UnlockedUser, file: UploadFile = File(...)) -> ImportPreview:
    """Walidacja pliku `.json` przesłanego z dysku użytkownika."""
    raw = await file.read()
    if len(raw) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Plik przekracza dopuszczalny rozmiar {settings.max_upload_bytes // (1024 * 1024)} MB.",
        )
    return normalise_payload(raw)


@router.post("/import/commit", response_model=StudySetDetail, status_code=status.HTTP_201_CREATED)
def commit_import(payload: ImportRequest, user: UnlockedUser, db: DbSession) -> StudySetDetail:
    """Waliduje dane i od razu zapisuje je jako nowy zestaw użytkownika."""
    preview = normalise_payload(payload.data, default_visibility=payload.visibility)
    if not preview.ok or preview.payload is None:
        return JSONResponse(  # type: ignore[return-value]
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=json.loads(preview.model_dump_json()),
        )
    study_set = create_study_set(db, user, preview.payload)
    log_action(db, user, "set.import", f"Zaimportowano zestaw #{study_set.id} „{study_set.title}”.")
    db.commit()
    study_set = _load_set(db, study_set.id)
    return to_detail(db, study_set, viewer=user)


@router.get("/sets/{set_id}/export")
def export_set(set_id: int, db: DbSession, user: OptionalUser) -> Response:
    study_set = _load_set(db, set_id)
    if not can_view(study_set, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Ten zestaw jest prywatny.")

    data = export_payload(study_set)
    filename = f"zestaw-{set_id}.json"
    return Response(
        content=json.dumps(data, ensure_ascii=False, indent=2),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
