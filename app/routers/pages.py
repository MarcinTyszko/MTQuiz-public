"""Widoki HTML renderowane po stronie serwera."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select

from ..config import settings
from ..deps import DbSession, OptionalUser
from ..models import Favorite, StudySession, StudySet, Visibility
from ..services import (
    can_edit,
    can_view,
    counts_for_sets,
    dashboard_stats,
    favorite_ids,
    set_query_with_relations,
    to_detail,
    to_summary,
)
from ..templating import templates

router = APIRouter(include_in_schema=False)


def _render(request: Request, template: str, context: dict, status_code: int = 200) -> HTMLResponse:
    context.setdefault("settings", settings)
    return templates.TemplateResponse(request, template, context, status_code=status_code)


def _require_user(user, request: Request):
    """Przekierowuje niezalogowanych na ekran logowania."""
    if user is None:
        return RedirectResponse(
            url=f"/logowanie?next={request.url.path}", status_code=status.HTTP_303_SEE_OTHER
        )
    if user.must_change_password:
        return RedirectResponse(url="/zmiana-hasla", status_code=status.HTTP_303_SEE_OTHER)
    return None


@router.get("/", response_class=HTMLResponse)
def home(request: Request, user: OptionalUser, db: DbSession):
    if user is not None and not user.must_change_password:
        return RedirectResponse(url="/pulpit", status_code=status.HTTP_303_SEE_OTHER)
    if user is not None and user.must_change_password:
        return RedirectResponse(url="/zmiana-hasla", status_code=status.HTTP_303_SEE_OTHER)

    stmt = (
        set_query_with_relations()
        .where(StudySet.visibility == Visibility.PUBLIC, StudySet.is_published.is_(True))
        .order_by(StudySet.created_at.desc())
        .limit(6)
    )
    rows = list(db.scalars(stmt).unique())
    counts = counts_for_sets(db, [row.id for row in rows])
    featured = [to_summary(row, counts=counts.get(row.id)) for row in rows]
    return _render(request, "landing.html", {"user": None, "featured": featured})


@router.get("/logowanie", response_class=HTMLResponse)
def login_page(request: Request, user: OptionalUser, next: str = "/pulpit"):
    if user is not None:
        target = "/zmiana-hasla" if user.must_change_password else "/pulpit"
        return RedirectResponse(url=target, status_code=status.HTTP_303_SEE_OTHER)
    safe_next = next if next.startswith("/") and not next.startswith("//") else "/pulpit"
    return _render(request, "login.html", {"user": None, "next_url": safe_next, "mode": "login"})


@router.get("/rejestracja", response_class=HTMLResponse)
def register_page(request: Request, user: OptionalUser):
    if user is not None:
        return RedirectResponse(url="/pulpit", status_code=status.HTTP_303_SEE_OTHER)
    if not settings.allow_registration:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Rejestracja nowych kont jest wyłączona.")
    return _render(request, "login.html", {"user": None, "next_url": "/pulpit", "mode": "register"})


@router.get("/zmiana-hasla", response_class=HTMLResponse)
def change_password_page(request: Request, user: OptionalUser):
    if user is None:
        return RedirectResponse(url="/logowanie", status_code=status.HTTP_303_SEE_OTHER)
    return _render(request, "change_password.html", {"user": user})


@router.get("/pulpit", response_class=HTMLResponse)
def dashboard(request: Request, user: OptionalUser, db: DbSession):
    guard = _require_user(user, request)
    if guard is not None:
        return guard
    assert user is not None

    owned_rows = list(
        db.scalars(
            set_query_with_relations()
            .where(StudySet.author_id == user.id)
            .order_by(StudySet.updated_at.desc())
        ).unique()
    )
    favorite_rows = list(
        db.scalars(
            set_query_with_relations()
            .join(Favorite, Favorite.set_id == StudySet.id)
            .where(Favorite.user_id == user.id)
            .order_by(Favorite.created_at.desc())
        ).unique()
    )

    all_ids = [row.id for row in owned_rows] + [row.id for row in favorite_rows]
    counts = counts_for_sets(db, all_ids)
    favourites = favorite_ids(db, user, all_ids)

    owned = [
        to_summary(row, counts=counts.get(row.id), is_favorite=row.id in favourites, viewer=user)
        for row in owned_rows
    ]
    favorites = [
        to_summary(row, counts=counts.get(row.id), is_favorite=True, viewer=user) for row in favorite_rows
    ]

    recent = list(
        db.scalars(
            select(StudySession)
            .where(StudySession.user_id == user.id)
            .order_by(StudySession.created_at.desc())
            .limit(8)
        )
    )
    titles = {}
    if recent:
        titles = dict(
            db.execute(
                select(StudySet.id, StudySet.title).where(StudySet.id.in_({r.set_id for r in recent}))
            ).all()
        )

    return _render(
        request,
        "dashboard.html",
        {
            "user": user,
            "owned": owned,
            "favorites": favorites,
            "stats": dashboard_stats(db, user),
            "recent": recent,
            "recent_titles": titles,
        },
    )


@router.get("/baza-publiczna", response_class=HTMLResponse)
def explore(
    request: Request,
    user: OptionalUser,
    db: DbSession,
    q: str = Query(default="", max_length=120),
    tag: str = Query(default="", max_length=64),
    sort: str = Query(default="newest"),
):
    if user is not None and user.must_change_password:
        return RedirectResponse(url="/zmiana-hasla", status_code=status.HTTP_303_SEE_OTHER)
    return _render(
        request,
        "explore.html",
        {"user": user, "initial_query": q, "initial_tag": tag, "initial_sort": sort},
    )


@router.get("/zestawy/nowy", response_class=HTMLResponse)
def new_set_page(request: Request, user: OptionalUser):
    guard = _require_user(user, request)
    if guard is not None:
        return guard
    return _render(request, "set_editor.html", {"user": user, "set_data": None, "mode": "create"})


@router.get("/zestawy/import", response_class=HTMLResponse)
def import_page(request: Request, user: OptionalUser):
    guard = _require_user(user, request)
    if guard is not None:
        return guard
    return _render(request, "import.html", {"user": user})


@router.get("/zestawy/{set_id}", response_class=HTMLResponse)
def set_detail_page(request: Request, set_id: int, user: OptionalUser, db: DbSession):
    if user is not None and user.must_change_password:
        return RedirectResponse(url="/zmiana-hasla", status_code=status.HTTP_303_SEE_OTHER)

    study_set = db.scalar(set_query_with_relations().where(StudySet.id == set_id))
    if study_set is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nie znaleziono zestawu.")
    if not can_view(study_set, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Ten zestaw jest prywatny.")

    if user is None or user.id != study_set.author_id:
        study_set.view_count += 1
        db.commit()
        study_set = db.scalar(set_query_with_relations().where(StudySet.id == set_id))
        assert study_set is not None

    is_favorite = bool(favorite_ids(db, user, [set_id]))
    detail = to_detail(db, study_set, viewer=user, is_favorite=is_favorite)

    best = None
    if user is not None:
        best = db.scalar(
            select(func.max(StudySession.score * 100.0 / func.nullif(StudySession.total, 0))).where(
                StudySession.user_id == user.id,
                StudySession.set_id == set_id,
            )
        )

    return _render(
        request,
        "set_detail.html",
        {
            "user": user,
            "study_set": detail,
            "can_edit": can_edit(study_set, user),
            "best_score": round(best, 1) if best else None,
        },
    )


@router.get("/zestawy/{set_id}/edycja", response_class=HTMLResponse)
def edit_set_page(request: Request, set_id: int, user: OptionalUser, db: DbSession):
    guard = _require_user(user, request)
    if guard is not None:
        return guard

    study_set = db.scalar(set_query_with_relations().where(StudySet.id == set_id))
    if study_set is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nie znaleziono zestawu.")
    if not can_edit(study_set, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Brak uprawnień do edycji tego zestawu.")

    detail = to_detail(db, study_set, viewer=user)
    return _render(
        request,
        "set_editor.html",
        {"user": user, "set_data": detail.model_dump(mode="json"), "mode": "edit"},
    )


@router.get("/zestawy/{set_id}/fiszki", response_class=HTMLResponse)
def flashcards_page(request: Request, set_id: int, user: OptionalUser, db: DbSession):
    guard = _require_user(user, request)
    if guard is not None:
        return guard

    study_set = db.scalar(set_query_with_relations().where(StudySet.id == set_id))
    if study_set is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nie znaleziono zestawu.")
    if not can_view(study_set, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Ten zestaw jest prywatny.")

    detail = to_detail(db, study_set, viewer=user)
    if not detail.cards:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ten zestaw nie zawiera fiszek.")

    return _render(
        request,
        "runner_flashcards.html",
        {"user": user, "study_set": detail.model_dump(mode="json"), "set_title": detail.title},
    )


@router.get("/zestawy/{set_id}/quiz", response_class=HTMLResponse)
def quiz_page(request: Request, set_id: int, user: OptionalUser, db: DbSession):
    guard = _require_user(user, request)
    if guard is not None:
        return guard

    study_set = db.scalar(set_query_with_relations().where(StudySet.id == set_id))
    if study_set is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nie znaleziono zestawu.")
    if not can_view(study_set, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Ten zestaw jest prywatny.")

    detail = to_detail(db, study_set, viewer=user)
    if not detail.questions:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ten zestaw nie zawiera pytań quizowych.")

    return _render(
        request,
        "runner_quiz.html",
        {"user": user, "study_set": detail.model_dump(mode="json"), "set_title": detail.title},
    )


@router.get("/panel", response_class=HTMLResponse)
def admin_page(request: Request, user: OptionalUser):
    guard = _require_user(user, request)
    if guard is not None:
        return guard
    assert user is not None
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Wymagane uprawnienia administratora.")
    return _render(request, "admin.html", {"user": user})


@router.get("/konto", response_class=HTMLResponse)
def account_page(request: Request, user: OptionalUser, db: DbSession):
    guard = _require_user(user, request)
    if guard is not None:
        return guard
    assert user is not None
    return _render(request, "account.html", {"user": user, "stats": dashboard_stats(db, user)})
