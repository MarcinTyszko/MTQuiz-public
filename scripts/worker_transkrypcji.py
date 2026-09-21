#!/usr/bin/env python3
"""Proces transkrybujący nagrania zgłoszone w MTQuiz.

Działa poza kontenerem — tam, gdzie dostępna jest karta graficzna — i komunikuje
się z aplikacją wyłącznie przez pliki w katalogu danych. Nie potrzebuje dostępu
do bazy ani do zależności aplikacji; jedynym wymaganiem jest ``faster-whisper``.

    python scripts/worker_transkrypcji.py --dane ./data

Protokół katalogu ``<dane>/transkrypcje/<id>``:
    zadanie.json      — opis zadania (czyta proces)
    audio.<ext>       — nagranie źródłowe
    stan.json         — stan i postęp (pisze proces)
    transkrypcja.txt  — wynik czytelny
    transkrypcja.json — wynik z segmentami

Plik ``<dane>/transkrypcje/_worker.json`` jest sygnałem życia: aplikacja pokazuje
na jego podstawie, czy proces działa.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

PLIK_ZADANIA = "zadanie.json"
PLIK_STANU = "stan.json"
PLIK_TEKSTU = "transkrypcja.txt"
PLIK_SEGMENTOW = "transkrypcja.json"
PLIK_SYGNALU = "_worker.json"

_zatrzymaj = False


def _teraz() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log(tresc: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {tresc}", flush=True)


def _obsluz_sygnal(_numer, _ramka) -> None:
    global _zatrzymaj
    _zatrzymaj = True
    _log("Otrzymano sygnał zatrzymania — kończę po bieżącym zadaniu.")


def hhmmss(sekundy: float) -> str:
    sekundy = max(0.0, float(sekundy))
    godziny, reszta = divmod(int(sekundy), 3600)
    minuty, sek = divmod(reszta, 60)
    return f"{godziny:02d}:{minuty:02d}:{sek:02d}" if godziny else f"{minuty:02d}:{sek:02d}"


def zapisz_atomowo(sciezka: Path, tresc: str) -> None:
    """Zapis przez plik tymczasowy — aplikacja nigdy nie zobaczy połowy pliku."""
    tymczasowy = sciezka.with_suffix(sciezka.suffix + ".tmp")
    tymczasowy.write_text(tresc, encoding="utf-8")
    os.replace(tymczasowy, sciezka)


def zapisz_stan(katalog: Path, **pola) -> None:
    zapisz_atomowo(katalog / PLIK_STANU, json.dumps(pola, ensure_ascii=False, indent=1))


def tryb_uruchomienia() -> str:
    """Rozpoznaje, czy proces działa jako usługa systemd, czy uruchomiono go ręcznie."""
    return "usluga" if os.environ.get("INVOCATION_ID") else "reczny"


def sygnal_zycia(katalog_transkrypcji: Path, urzadzenie: str, model: str, zadanie: str | None = None) -> None:
    """Zapisuje znak życia odczytywany przez aplikację.

    Wywoływany również w trakcie długiej transkrypcji — inaczej aplikacja uznałaby
    pracujący proces za nieczynny.
    """
    zapisz_atomowo(
        katalog_transkrypcji / PLIK_SYGNALU,
        json.dumps(
            {
                "sygnal": _teraz(),
                "urzadzenie": urzadzenie,
                "model": model,
                "tryb": tryb_uruchomienia(),
                "zadanie": zadanie,
                "pid": os.getpid(),
            },
            ensure_ascii=False,
        ),
    )


def znajdz_zadania(katalog_transkrypcji: Path) -> list[Path]:
    """Zwraca katalogi zadań czekających na transkrypcję, od najstarszego."""
    czekajace = []
    for katalog in katalog_transkrypcji.iterdir():
        if not katalog.is_dir() or katalog.name.startswith("_"):
            continue
        plik_zadania = katalog / PLIK_ZADANIA
        if not plik_zadania.exists():
            continue

        plik_stanu = katalog / PLIK_STANU
        if plik_stanu.exists():
            try:
                stan = json.loads(plik_stanu.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                stan = {}
            if stan.get("status") in ("running", "done", "error"):
                continue
        czekajace.append(katalog)

    return sorted(czekajace, key=lambda k: k.stat().st_mtime)


class Transkryptor:
    """Leniwie ładowany model Whispera wraz z wyborem urządzenia."""

    def __init__(self, nazwa_modelu: str, wymus_cpu: bool) -> None:
        self.nazwa_modelu = nazwa_modelu
        self.wymus_cpu = wymus_cpu
        self.model = None
        self.urzadzenie = "cpu" if wymus_cpu else "cuda"
        self.obliczenia = "int8" if wymus_cpu else "float16"

    def _biblioteki_cuda(self) -> None:
        """Dokłada ścieżki bibliotek CUDA z pakietów pip do LD_LIBRARY_PATH."""
        try:
            import glob

            import nvidia
        except ImportError:
            return
        sciezki = {
            p
            for baza in list(nvidia.__path__)
            for p in glob.glob(os.path.join(baza, "*", "lib"))
        }
        if sciezki:
            os.environ["LD_LIBRARY_PATH"] = ":".join(sorted(sciezki)) + ":" + os.environ.get("LD_LIBRARY_PATH", "")

    def zaladuj(self) -> None:
        if self.model is not None:
            return

        from faster_whisper import WhisperModel

        if not self.wymus_cpu:
            self._biblioteki_cuda()

        start = time.time()
        try:
            self.model = WhisperModel(self.nazwa_modelu, device=self.urzadzenie, compute_type=self.obliczenia)
        except Exception as exc:  # noqa: BLE001 - każdy błąd GPU ma kończyć się zejściem na CPU
            if self.wymus_cpu:
                raise
            _log(f"GPU niedostępne ({exc.__class__.__name__}: {exc}) — przechodzę na CPU/int8.")
            self.urzadzenie, self.obliczenia = "cpu", "int8"
            self.model = WhisperModel(
                self.nazwa_modelu, device="cpu", compute_type="int8", cpu_threads=os.cpu_count() or 4
            )
        _log(f"Model {self.nazwa_modelu} gotowy na {self.urzadzenie}/{self.obliczenia} w {time.time() - start:.1f} s.")

    def transkrybuj(self, audio: Path, jezyk: str):
        self.zaladuj()
        return self.model.transcribe(
            str(audio),
            language=jezyk or None,
            task="transcribe",
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
            word_timestamps=False,
            condition_on_previous_text=True,
            temperature=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
        )


def wykonaj(katalog: Path, transkryptor: Transkryptor, katalog_transkrypcji: Path) -> None:
    zadanie = json.loads((katalog / PLIK_ZADANIA).read_text(encoding="utf-8"))
    audio = katalog / zadanie["plik"]
    tytul = zadanie.get("tytul") or audio.name

    if not audio.exists():
        zapisz_stan(
            katalog,
            status="error",
            postep=0,
            komunikat="Brak pliku nagrania.",
            blad=f"Nie znaleziono pliku {zadanie['plik']} w katalogu zadania.",
            zakonczono=_teraz(),
        )
        _log(f"#{zadanie['id']} — brak pliku nagrania, pomijam.")
        return

    rozpoczeto = _teraz()
    zapisz_stan(katalog, status="running", postep=0, komunikat="Wczytywanie modelu…", rozpoczeto=rozpoczeto)
    sygnal_zycia(katalog_transkrypcji, transkryptor.urzadzenie, transkryptor.nazwa_modelu, tytul)
    _log(f"#{zadanie['id']} „{tytul}” — start ({audio.stat().st_size / 1024 / 1024:.1f} MB).")

    segmenty_wynik: list[dict] = []
    start = time.time()

    segmenty, info = transkryptor.transkrybuj(audio, zadanie.get("jezyk") or "pl")
    dlugosc = float(getattr(info, "duration", 0.0) or 0.0)
    zapisz_stan(
        katalog,
        status="running",
        postep=1,
        komunikat=f"Transkrypcja nagrania ({hhmmss(dlugosc)})…",
        rozpoczeto=rozpoczeto,
        dlugosc=dlugosc,
    )

    plik_tekstu = katalog / PLIK_TEKSTU
    ostatni_zapis = 0.0
    with plik_tekstu.open("w", encoding="utf-8") as wyjscie:
        for segment in segmenty:
            tekst = segment.text.strip()
            if tekst:
                wyjscie.write(f"[{hhmmss(segment.start)} -> {hhmmss(segment.end)}] {tekst}\n")
                wyjscie.flush()
                segmenty_wynik.append(
                    {
                        "start": round(float(segment.start), 2),
                        "koniec": round(float(segment.end), 2),
                        "tekst": tekst,
                    }
                )

            if dlugosc > 0 and time.time() - ostatni_zapis >= 3:
                ostatni_zapis = time.time()
                postep = max(1, min(99, int(segment.end / dlugosc * 100)))
                zapisz_stan(
                    katalog,
                    status="running",
                    postep=postep,
                    komunikat=f"Przetworzono {hhmmss(segment.end)} z {hhmmss(dlugosc)}.",
                    rozpoczeto=rozpoczeto,
                    dlugosc=dlugosc,
                )
                # Znak życia także w trakcie pracy — transkrypcja bywa dłuższa
                # niż dopuszczalna przerwa między sygnałami.
                sygnal_zycia(katalog_transkrypcji, transkryptor.urzadzenie, transkryptor.nazwa_modelu, tytul)

    zapisz_atomowo(
        katalog / PLIK_SEGMENTOW,
        json.dumps(
            {
                "id": zadanie["id"],
                "nagranie": audio.name,
                "model": transkryptor.nazwa_modelu,
                "urzadzenie": transkryptor.urzadzenie,
                "jezyk": zadanie.get("jezyk"),
                "dlugosc": dlugosc,
                "segmenty": segmenty_wynik,
            },
            ensure_ascii=False,
            indent=1,
        ),
    )

    czas = time.time() - start
    zapisz_stan(
        katalog,
        status="done",
        postep=100,
        komunikat=f"Gotowe: {len(segmenty_wynik)} segmentów w {czas:.0f} s.",
        rozpoczeto=rozpoczeto,
        zakonczono=_teraz(),
        dlugosc=dlugosc,
    )
    _log(f"#{zadanie['id']} — gotowe: {len(segmenty_wynik)} segmentów, {czas:.0f} s.")


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="worker_transkrypcji.py",
        description="Transkrybuje nagrania zgłoszone w MTQuiz, korzystając z karty graficznej.",
    )
    parser.add_argument("--dane", default="./data", help="katalog danych aplikacji (domyślnie ./data)")
    parser.add_argument("--model", default=os.environ.get("QUIZAPP_WHISPER_MODEL", "large-v3"))
    parser.add_argument("--cpu", action="store_true", help="wymusza pracę na procesorze")
    parser.add_argument("--odstep", type=float, default=3.0, help="co ile sekund sprawdzać kolejkę")
    parser.add_argument("--raz", action="store_true", help="przetwórz to, co w kolejce, i zakończ")
    args = parser.parse_args()

    katalog_transkrypcji = Path(args.dane).expanduser().resolve() / "transkrypcje"
    katalog_transkrypcji.mkdir(parents=True, exist_ok=True)

    signal.signal(signal.SIGINT, _obsluz_sygnal)
    signal.signal(signal.SIGTERM, _obsluz_sygnal)

    transkryptor = Transkryptor(args.model, args.cpu)
    _log(f"Nasłuchuję na {katalog_transkrypcji} (model {args.model}). Zatrzymanie: Ctrl+C.")
    sygnal_zycia(katalog_transkrypcji, "ładowanie" if not args.cpu else "cpu", args.model)

    ostatni_sygnal = 0.0
    while not _zatrzymaj:
        if time.time() - ostatni_sygnal >= 15:
            ostatni_sygnal = time.time()
            sygnal_zycia(
                katalog_transkrypcji,
                transkryptor.urzadzenie if transkryptor.model is not None else "oczekiwanie",
                args.model,
            )

        zadania = znajdz_zadania(katalog_transkrypcji)
        if not zadania:
            if args.raz:
                break
            time.sleep(args.odstep)
            continue

        for katalog in zadania:
            if _zatrzymaj:
                break
            try:
                wykonaj(katalog, transkryptor, katalog_transkrypcji)
            except Exception as exc:  # noqa: BLE001 - błąd jednego zadania nie może zabić procesu
                _log(f"Błąd zadania {katalog.name}: {exc}")
                traceback.print_exc()
                zapisz_stan(
                    katalog,
                    status="error",
                    postep=0,
                    komunikat="Transkrypcja nie powiodła się.",
                    blad=f"{exc.__class__.__name__}: {exc}",
                    zakonczono=_teraz(),
                )
            sygnal_zycia(katalog_transkrypcji, transkryptor.urzadzenie, args.model)

        if args.raz:
            break

    _log("Zatrzymano.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
