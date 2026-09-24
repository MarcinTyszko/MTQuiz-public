"""Obsługa zadań transkrypcji: kolejka plikowa, stan pracy i eksport wyników.

Aplikacja nie liczy transkrypcji samodzielnie. Zapisuje nagranie i opis zadania
w katalogu ``/data/transkrypcje/<id>``, a właściwą pracę wykonuje osobny proces
(``scripts/worker_transkrypcji.py``) uruchamiany tam, gdzie dostępna jest karta
graficzna. Wymiana odbywa się przez pliki, dzięki czemu proces liczący nie
potrzebuje dostępu do bazy ani do zależności aplikacji.

Protokół katalogu zadania:
    zadanie.json      — opis zadania zapisany przez aplikację
    audio.<ext>       — nagranie źródłowe
    stan.json         — stan i postęp zapisywany przez proces liczący
    transkrypcja.txt  — wynik w postaci czytelnej
    transkrypcja.json — wynik z segmentami i znacznikami czasu
"""
from __future__ import annotations

import json
import re
import shutil
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import settings
from .models import Transcription, TranscriptionStatus

PLIK_ZADANIA = "zadanie.json"
PLIK_STANU = "stan.json"
PLIK_TEKSTU = "transkrypcja.txt"
PLIK_SEGMENTOW = "transkrypcja.json"
PLIK_SYGNALU = "_worker.json"
PLIK_BLOKADY = "_przejete"  # zakłada proces liczący, gdy bierze zadanie

# Rozszerzenia akceptowane przy wysyłce nagrania.
DOZWOLONE_ROZSZERZENIA = {".mp3", ".m4a", ".wav", ".ogg", ".oga", ".opus", ".webm", ".flac", ".mp4", ".aac", ".wma"}


def katalog_zadania(transcription_id: int) -> Path:
    return settings.transcripts_dir / str(transcription_id)


def przygotuj_katalog(transcription_id: int) -> Path:
    katalog = katalog_zadania(transcription_id)
    katalog.mkdir(parents=True, exist_ok=True)
    return katalog


def bezpieczna_nazwa(nazwa: str, domyslna: str = "nagranie") -> str:
    """Sprowadza nazwę pliku do postaci bezpiecznej dla systemu plików."""
    rdzen = Path(nazwa).stem
    tekst = unicodedata.normalize("NFKD", rdzen)
    tekst = tekst.replace("ł", "l").replace("Ł", "L")
    tekst = "".join(znak for znak in tekst if not unicodedata.combining(znak))
    tekst = re.sub(r"[^A-Za-z0-9._-]+", "-", tekst).strip("-._")
    return (tekst[:80] or domyslna)


def rozszerzenie(nazwa: str) -> str:
    koncowka = Path(nazwa).suffix.lower()
    return koncowka if koncowka in DOZWOLONE_ROZSZERZENIA else ""


def zapisz_zadanie(transcription: Transcription) -> Path:
    """Zapisuje opis zadania, który odczyta proces liczący."""
    katalog = przygotuj_katalog(transcription.id)
    opis = {
        "id": transcription.id,
        "plik": transcription.stored_filename,
        "jezyk": transcription.language,
        "model": transcription.model_name,
        "tytul": transcription.title,
        "utworzono": datetime.now(timezone.utc).isoformat(),
    }
    sciezka = katalog / PLIK_ZADANIA
    sciezka.write_text(json.dumps(opis, ensure_ascii=False, indent=2), encoding="utf-8")
    return sciezka


def wczytaj_stan(transcription_id: int) -> dict[str, Any] | None:
    """Odczytuje stan zapisany przez proces liczący (jeżeli już powstał)."""
    sciezka = katalog_zadania(transcription_id) / PLIK_STANU
    if not sciezka.exists():
        return None
    try:
        return json.loads(sciezka.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _status_z_pliku(wartosc: Any) -> TranscriptionStatus | None:
    try:
        return TranscriptionStatus(str(wartosc))
    except ValueError:
        return None


def zsynchronizuj(transcription: Transcription) -> bool:
    """Przenosi stan z plików do rekordu bazy. Zwraca True, gdy coś się zmieniło.

    Dzięki temu proces liczący nie musi znać bazy danych — wystarczy, że pisze
    pliki, a aplikacja podnosi z nich stan przy każdym odpytaniu.
    """
    if transcription.status in (TranscriptionStatus.DONE, TranscriptionStatus.ERROR):
        return False

    stan = wczytaj_stan(transcription.id)
    if stan is None:
        return False

    zmieniono = False
    nowy_status = _status_z_pliku(stan.get("status"))
    if nowy_status is not None and nowy_status != transcription.status:
        transcription.status = nowy_status
        zmieniono = True

    postep = stan.get("postep")
    if isinstance(postep, (int, float)):
        postep = max(0, min(100, int(postep)))
        if postep != transcription.progress:
            transcription.progress = postep
            zmieniono = True

    komunikat = str(stan.get("komunikat") or "")[:255]
    if komunikat != transcription.message:
        transcription.message = komunikat
        zmieniono = True

    if transcription.started_at is None and stan.get("rozpoczeto"):
        transcription.started_at = _czas(stan["rozpoczeto"])
        zmieniono = True

    if nowy_status == TranscriptionStatus.RUNNING:
        return zmieniono

    if nowy_status == TranscriptionStatus.ERROR:
        transcription.error_message = str(stan.get("blad") or "Transkrypcja zakończyła się niepowodzeniem.")[:4000]
        transcription.finished_at = _czas(stan.get("zakonczono")) or datetime.now(timezone.utc)
        return True

    if nowy_status == TranscriptionStatus.DONE:
        zmieniono = _wczytaj_wynik(transcription) or zmieniono
        transcription.progress = 100
        transcription.finished_at = _czas(stan.get("zakonczono")) or datetime.now(timezone.utc)
        if stan.get("dlugosc"):
            transcription.duration_seconds = float(stan["dlugosc"])
        return True

    return zmieniono


def _czas(wartosc: Any) -> datetime | None:
    if not wartosc:
        return None
    try:
        czas = datetime.fromisoformat(str(wartosc))
    except ValueError:
        return None
    return czas if czas.tzinfo else czas.replace(tzinfo=timezone.utc)


def _wczytaj_wynik(transcription: Transcription) -> bool:
    """Przenosi wynik z plików do rekordu, żeby podgląd i eksport były niezależne."""
    katalog = katalog_zadania(transcription.id)
    plik_tekstu = katalog / PLIK_TEKSTU
    plik_segmentow = katalog / PLIK_SEGMENTOW

    if not plik_tekstu.exists():
        transcription.status = TranscriptionStatus.ERROR
        transcription.error_message = "Proces zgłosił zakończenie, ale plik z transkrypcją nie powstał."
        return True

    transcription.text = plik_tekstu.read_text(encoding="utf-8").strip()

    if plik_segmentow.exists():
        try:
            dane = json.loads(plik_segmentow.read_text(encoding="utf-8"))
            segmenty = dane.get("segmenty") or dane.get("segments") or []
            transcription.segments_json = json.dumps(segmenty, ensure_ascii=False)
            transcription.segments_count = len(segmenty)
            if dane.get("dlugosc") or dane.get("duration"):
                transcription.duration_seconds = float(dane.get("dlugosc") or dane.get("duration"))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            transcription.segments_json = None
    return True


def usun_katalog(transcription_id: int) -> None:
    shutil.rmtree(katalog_zadania(transcription_id), ignore_errors=True)


def usun_nagranie(transcription: Transcription) -> bool:
    """Kasuje plik audio, zostawiając wynik transkrypcji. Zwalnia miejsce na dysku."""
    plik = katalog_zadania(transcription.id) / transcription.stored_filename
    if plik.exists():
        plik.unlink()
        return True
    return False


def nagranie_istnieje(transcription: Transcription) -> bool:
    return (katalog_zadania(transcription.id) / transcription.stored_filename).exists()


# --------------------------------------------------------------------------- #
# Stan procesu liczącego
# --------------------------------------------------------------------------- #
def stan_procesu() -> dict[str, Any]:
    """Zwraca informację, czy proces transkrybujący daje znaki życia."""
    sciezka = settings.transcripts_dir / PLIK_SYGNALU
    if not sciezka.exists():
        return {
            "dostepny": False,
            "sygnal": None,
            "tryb": "brak",
            "opis": "Proces transkrypcji jeszcze nie wystartował.",
        }

    try:
        dane = json.loads(sciezka.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"dostepny": False, "sygnal": None, "opis": "Nie udało się odczytać sygnału procesu."}

    sygnal = _czas(dane.get("sygnal"))
    if sygnal is None:
        return {"dostepny": False, "sygnal": None, "opis": "Sygnał procesu jest niekompletny."}

    wiek = (datetime.now(timezone.utc) - sygnal).total_seconds()
    dostepny = wiek <= settings.worker_heartbeat_timeout
    tryb = dane.get("tryb") or "reczny"
    urzadzenie = dane.get("urzadzenie") or "nieznane urządzenie"

    if dostepny:
        zadanie = dane.get("zadanie")
        if zadanie:
            opis = f"Transkrypcja w toku: {zadanie}"
        elif urzadzenie == "oczekiwanie":
            # Model wczytuje się dopiero przy pierwszym nagraniu, więc urządzenie
            # nie jest jeszcze znane — nie ma o czym informować użytkownika.
            opis = (
                "Usługa transkrypcji działa i czeka na nagrania."
                if tryb == "usluga"
                else "Proces transkrypcji działa, uruchomiony ręcznie."
            )
        elif tryb == "usluga":
            opis = f"Usługa transkrypcji działa i czeka na nagrania ({urzadzenie})."
        else:
            opis = f"Proces transkrypcji działa ({urzadzenie}), uruchomiony ręcznie."
    else:
        opis = (
            f"Usługa transkrypcji nie odpowiada od {int(wiek)} s."
            if tryb == "usluga"
            else f"Ostatni sygnał {int(wiek)} s temu — proces transkrypcji nie działa."
        )

    return {
        "dostepny": dostepny,
        "sygnal": sygnal.isoformat(),
        "urzadzenie": dane.get("urzadzenie"),
        "model": dane.get("model"),
        "tryb": tryb,
        "zadanie": dane.get("zadanie"),
        "opis": opis,
    }


# --------------------------------------------------------------------------- #
# Eksport
# --------------------------------------------------------------------------- #
def czas_hhmmss(sekundy: float) -> str:
    sekundy = max(0.0, float(sekundy))
    godziny, reszta = divmod(int(sekundy), 3600)
    minuty, sek = divmod(reszta, 60)
    return f"{godziny:02d}:{minuty:02d}:{sek:02d}" if godziny else f"{minuty:02d}:{sek:02d}"


def segmenty(transcription: Transcription) -> list[dict[str, Any]]:
    if not transcription.segments_json:
        return []
    try:
        return json.loads(transcription.segments_json)
    except json.JSONDecodeError:
        return []


def tekst_ciagly(transcription: Transcription) -> str:
    """Sam tekst wypowiedzi, bez znaczników czasu — do wklejenia modelowi."""
    lista = segmenty(transcription)
    if lista:
        return " ".join((s.get("tekst") or s.get("text") or "").strip() for s in lista).strip()
    return re.sub(r"^\[\d{2}:\d{2}(?::\d{2})?(?: -> \d{2}:\d{2}(?::\d{2})?)?\]\s*", "", transcription.text, flags=re.M)


def jako_txt(transcription: Transcription, ze_znacznikami: bool = True) -> str:
    naglowek = [
        f"# {transcription.title}",
        f"# Nagranie: {transcription.original_filename}",
        f"# Długość: {czas_hhmmss(transcription.duration_seconds)}"
        f" · model: {transcription.model_name} · język: {transcription.language}",
        "",
    ]
    tresc = transcription.text if ze_znacznikami else tekst_ciagly(transcription)
    return "\n".join(naglowek) + tresc.strip() + "\n"


def jako_markdown(transcription: Transcription) -> str:
    wiersze = [
        f"# {transcription.title}",
        "",
        f"- **Nagranie:** {transcription.original_filename}",
        f"- **Długość:** {czas_hhmmss(transcription.duration_seconds)}",
        f"- **Model:** {transcription.model_name} · **język:** {transcription.language}",
        f"- **Segmentów:** {transcription.segments_count} · **słów:** {transcription.word_count}",
        "",
        "---",
        "",
    ]
    lista = segmenty(transcription)
    if lista:
        for segment in lista:
            start = czas_hhmmss(segment.get("start", 0))
            tekst = (segment.get("tekst") or segment.get("text") or "").strip()
            if tekst:
                wiersze.append(f"**[{start}]** {tekst}")
                wiersze.append("")
    else:
        wiersze.append(transcription.text.strip())
    return "\n".join(wiersze) + "\n"


def jako_pdf(transcription: Transcription) -> bytes:
    """Składa transkrypcję do PDF-a przygotowanego pod druk A4."""
    from fpdf import FPDF

    czcionka_zwykla = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    czcionka_pogrubiona = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_margins(20, 18, 20)

    if czcionka_zwykla.exists():
        pdf.add_font("DejaVu", "", str(czcionka_zwykla))
        pdf.add_font("DejaVu", "B", str(czcionka_pogrubiona) if czcionka_pogrubiona.exists() else str(czcionka_zwykla))
        rodzina = "DejaVu"
    else:  # pragma: no cover - awaryjnie, gdy w systemie brakuje czcionki
        rodzina = "Helvetica"

    pdf.add_page()

    pdf.set_font(rodzina, "B", 18)
    pdf.multi_cell(0, 9, transcription.title, align="L")
    pdf.ln(2)

    pdf.set_font(rodzina, "", 9)
    pdf.set_text_color(110, 110, 120)
    metadane = (
        f"Nagranie: {transcription.original_filename}\n"
        f"Długość: {czas_hhmmss(transcription.duration_seconds)}  ·  "
        f"model: {transcription.model_name}  ·  język: {transcription.language}\n"
        f"Segmentów: {transcription.segments_count}  ·  słów: {transcription.word_count}  ·  "
        f"transkrypcja z dnia {transcription.created_at:%d.%m.%Y}"
    )
    pdf.multi_cell(0, 5, metadane, align="L")
    pdf.ln(3)

    pdf.set_draw_color(210, 210, 216)
    pdf.line(20, pdf.get_y(), 190, pdf.get_y())
    pdf.ln(5)

    pdf.set_text_color(25, 25, 30)
    lista = segmenty(transcription)
    if lista:
        for segment in lista:
            tekst = (segment.get("tekst") or segment.get("text") or "").strip()
            if not tekst:
                continue
            pdf.set_font(rodzina, "B", 8)
            pdf.set_text_color(120, 120, 130)
            pdf.cell(0, 4.5, f"[{czas_hhmmss(segment.get('start', 0))}]", new_x="LMARGIN", new_y="NEXT")
            pdf.set_font(rodzina, "", 10.5)
            pdf.set_text_color(25, 25, 30)
            pdf.multi_cell(0, 5.6, tekst, align="L")
            pdf.ln(2)
    else:
        pdf.set_font(rodzina, "", 10.5)
        pdf.multi_cell(0, 5.6, transcription.text.strip() or "(brak treści)", align="L")

    return bytes(pdf.output())
