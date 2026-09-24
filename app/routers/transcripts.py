"""Endpointy transkrypcji nagrań: wysyłka, śledzenie postępu i pobieranie wyników."""
from __future__ import annotations

from pathlib import Path
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import select

from .. import transkrypcje
from ..config import settings
from ..deps import DbSession, UnlockedUser
from ..models import Transcription, TranscriptionStatus
from ..schemas import (
    MessageOut,
    TranscriptionDetail,
    TranscriptionRename,
    TranscriptionSummary,
    WorkerStatus,
)
from ..services import log_action

router = APIRouter(prefix="/api/transkrypcje", tags=["transkrypcje"])

# Rozmiar porcji przy zapisie nagrania — plik trafia na dysk strumieniowo,
# nigdy w całości do pamięci.
PORCJA = 1024 * 1024


def _pobierz(db, user, transcription_id: int) -> Transcription:
    transcription = db.get(Transcription, transcription_id)
    if transcription is None or (transcription.user_id != user.id and not user.is_admin):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nie znaleziono transkrypcji.")
    return transcription


def _podsumowanie(transcription: Transcription) -> TranscriptionSummary:
    return TranscriptionSummary(
        id=transcription.id,
        title=transcription.title,
        original_filename=transcription.original_filename,
        size_bytes=transcription.size_bytes,
        duration_seconds=transcription.duration_seconds,
        language=transcription.language,
        model_name=transcription.model_name,
        status=transcription.status,
        progress=transcription.progress,
        message=transcription.message,
        error_message=transcription.error_message,
        segments_count=transcription.segments_count,
        word_count=transcription.word_count,
        has_audio=transkrypcje.nagranie_istnieje(transcription),
        created_at=transcription.created_at,
        started_at=transcription.started_at,
        finished_at=transcription.finished_at,
    )


@router.get("/worker", response_model=WorkerStatus)
def worker_status(user: UnlockedUser) -> WorkerStatus:
    """Informuje, czy proces transkrybujący daje znaki życia."""
    return WorkerStatus(**transkrypcje.stan_procesu())


@router.get("", response_model=list[TranscriptionSummary])
def lista(user: UnlockedUser, db: DbSession) -> list[TranscriptionSummary]:
    wiersze = list(
        db.scalars(
            select(Transcription)
            .where(Transcription.user_id == user.id)
            .order_by(Transcription.created_at.desc())
        )
    )

    zmiany = False
    for transcription in wiersze:
        zmiany = transkrypcje.zsynchronizuj(transcription) or zmiany
    if zmiany:
        db.commit()

    return [_podsumowanie(transcription) for transcription in wiersze]


@router.post("", response_model=TranscriptionSummary, status_code=status.HTTP_201_CREATED)
async def zglos(
    user: UnlockedUser,
    db: DbSession,
    file: UploadFile = File(...),
    title: str = Form(default=""),
    language: str = Form(default=""),
) -> TranscriptionSummary:
    """Przyjmuje nagranie i dopisuje zadanie do kolejki."""
    koncowka = transkrypcje.rozszerzenie(file.filename or "")
    if not koncowka:
        dozwolone = ", ".join(sorted(transkrypcje.DOZWOLONE_ROZSZERZENIA))
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Nieobsługiwany format pliku. Dozwolone rozszerzenia: {dozwolone}.",
        )

    transcription = Transcription(
        user_id=user.id,
        title=(title.strip() or Path(file.filename or "Nagranie").stem)[:200],
        original_filename=(file.filename or "nagranie")[:255],
        stored_filename="",
        language=(language.strip() or settings.whisper_language)[:8],
        model_name=settings.whisper_model,
        status=TranscriptionStatus.QUEUED,
        message="Nagranie czeka w kolejce.",
    )
    db.add(transcription)
    db.flush()

    katalog = transkrypcje.przygotuj_katalog(transcription.id)
    nazwa = transkrypcje.bezpieczna_nazwa(file.filename or "nagranie") + koncowka
    cel = katalog / nazwa

    rozmiar = 0
    try:
        with cel.open("wb") as wyjscie:
            while porcja := await file.read(PORCJA):
                rozmiar += len(porcja)
                if rozmiar > settings.max_audio_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=(
                            "Nagranie przekracza dopuszczalny rozmiar "
                            f"{settings.max_audio_bytes // (1024 * 1024)} MB."
                        ),
                    )
                wyjscie.write(porcja)
    except HTTPException:
        db.rollback()
        transkrypcje.usun_katalog(transcription.id)
        raise
    except OSError as exc:  # pragma: no cover - błąd systemu plików
        db.rollback()
        transkrypcje.usun_katalog(transcription.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Nie udało się zapisać nagrania: {exc}",
        ) from exc

    if rozmiar == 0:
        db.rollback()
        transkrypcje.usun_katalog(transcription.id)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Przesłany plik jest pusty.")

    transcription.stored_filename = nazwa
    transcription.size_bytes = rozmiar
    transkrypcje.zapisz_zadanie(transcription)
    log_action(db, user, "transkrypcja.zgloszenie", f"Zgłoszono nagranie „{transcription.title}” (#{transcription.id}).")
    db.commit()
    db.refresh(transcription)

    return _podsumowanie(transcription)


@router.get("/{transcription_id}", response_model=TranscriptionDetail)
def szczegoly(transcription_id: int, user: UnlockedUser, db: DbSession) -> TranscriptionDetail:
    transcription = _pobierz(db, user, transcription_id)
    if transkrypcje.zsynchronizuj(transcription):
        db.commit()
        db.refresh(transcription)

    podsumowanie = _podsumowanie(transcription)
    return TranscriptionDetail(
        **podsumowanie.model_dump(),
        text=transcription.text,
        segments=transkrypcje.segmenty(transcription),
    )


@router.patch("/{transcription_id}", response_model=TranscriptionSummary)
def zmien_nazwe(
    transcription_id: int, payload: TranscriptionRename, user: UnlockedUser, db: DbSession
) -> TranscriptionSummary:
    transcription = _pobierz(db, user, transcription_id)
    transcription.title = payload.title
    db.commit()
    db.refresh(transcription)
    return _podsumowanie(transcription)


@router.post("/{transcription_id}/ponow", response_model=TranscriptionSummary)
def ponow(transcription_id: int, user: UnlockedUser, db: DbSession) -> TranscriptionSummary:
    """Wstawia zadanie z powrotem do kolejki — po błędzie albo po zatrzymaniu procesu."""
    transcription = _pobierz(db, user, transcription_id)

    if not transkrypcje.nagranie_istnieje(transcription):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Nagranie źródłowe zostało usunięte — wyślij plik ponownie.",
        )

    transcription.status = TranscriptionStatus.QUEUED
    transcription.progress = 0
    transcription.message = "Nagranie czeka w kolejce."
    transcription.error_message = None
    transcription.started_at = None
    transcription.finished_at = None

    katalog = transkrypcje.katalog_zadania(transcription.id)
    (katalog / transkrypcje.PLIK_STANU).unlink(missing_ok=True)
    (katalog / transkrypcje.PLIK_BLOKADY).unlink(missing_ok=True)
    transkrypcje.zapisz_zadanie(transcription)
    db.commit()
    db.refresh(transcription)
    return _podsumowanie(transcription)


@router.delete("/{transcription_id}/nagranie", response_model=MessageOut)
def usun_nagranie(transcription_id: int, user: UnlockedUser, db: DbSession) -> MessageOut:
    """Kasuje sam plik audio, zachowując gotową transkrypcję."""
    transcription = _pobierz(db, user, transcription_id)
    if transcription.status != TranscriptionStatus.DONE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Nagranie można usunąć dopiero po zakończeniu transkrypcji.",
        )
    usunieto = transkrypcje.usun_nagranie(transcription)
    db.commit()
    return MessageOut(
        ok=usunieto,
        message="Plik nagrania został usunięty." if usunieto else "Nagranie zostało już wcześniej usunięte.",
    )


@router.delete("/{transcription_id}", response_model=MessageOut)
def usun(transcription_id: int, user: UnlockedUser, db: DbSession) -> MessageOut:
    transcription = _pobierz(db, user, transcription_id)
    tytul = transcription.title
    transkrypcje.usun_katalog(transcription.id)
    db.delete(transcription)
    log_action(db, user, "transkrypcja.usuniecie", f"Usunięto transkrypcję #{transcription_id} „{tytul}”.")
    db.commit()
    return MessageOut(ok=True, message=f"Transkrypcja „{tytul}” została usunięta.")


@router.get("/{transcription_id}/pobierz")
def pobierz(
    transcription_id: int,
    user: UnlockedUser,
    db: DbSession,
    format: Literal["txt", "md", "pdf", "tekst"] = Query(default="txt"),
) -> Response:
    """Zwraca transkrypcję w wybranym formacie.

    ``txt`` — ze znacznikami czasu, ``tekst`` — sam tekst do wklejenia modelowi,
    ``md`` — dokument Markdown, ``pdf`` — złożony dokument do druku.
    """
    transcription = _pobierz(db, user, transcription_id)
    if transcription.status != TranscriptionStatus.DONE or not transcription.text:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Transkrypcja nie jest jeszcze gotowa."
        )

    rdzen = transkrypcje.bezpieczna_nazwa(transcription.title, "transkrypcja")

    if format == "pdf":
        zawartosc: bytes = transkrypcje.jako_pdf(transcription)
        typ, nazwa = "application/pdf", f"{rdzen}.pdf"
    elif format == "md":
        zawartosc = transkrypcje.jako_markdown(transcription).encode("utf-8")
        typ, nazwa = "text/markdown; charset=utf-8", f"{rdzen}.md"
    elif format == "tekst":
        zawartosc = (transkrypcje.tekst_ciagly(transcription) + "\n").encode("utf-8")
        typ, nazwa = "text/plain; charset=utf-8", f"{rdzen}-sam-tekst.txt"
    else:
        zawartosc = transkrypcje.jako_txt(transcription).encode("utf-8")
        typ, nazwa = "text/plain; charset=utf-8", f"{rdzen}.txt"

    return Response(
        content=zawartosc,
        media_type=typ,
        headers={
            "Content-Disposition": f"attachment; filename=\"{nazwa}\"; filename*=UTF-8''{quote(nazwa)}",
            "Cache-Control": "no-store",
        },
    )
