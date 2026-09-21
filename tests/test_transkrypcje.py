"""Testy transkrypcji: kolejka, synchronizacja stanu z procesem liczącym i eksport."""
from __future__ import annotations

import io
import json
from datetime import datetime, timezone

import pytest

from conftest import register


def wyslij(client, nazwa: str = "wyklad.mp3", tresc: bytes = b"UDANE-NAGRANIE" * 64, **pola):
    dane = {"title": pola.get("title", "Wykład 3"), "language": pola.get("language", "pl")}
    return client.post(
        "/api/transkrypcje",
        files={"file": (nazwa, io.BytesIO(tresc), "audio/mpeg")},
        data=dane,
    )


def katalog(app_module, transcription_id: int):
    from app.config import settings

    return settings.transcripts_dir / str(transcription_id)


def udaj_wynik(app_module, transcription_id: int, segmenty=None, dlugosc: float = 92.5):
    """Zapisuje pliki tak, jak zrobiłby to proces transkrybujący."""
    segmenty = segmenty or [
        {"start": 0.0, "koniec": 4.2, "tekst": "Dzień dobry, zaczynamy wykład o układzie krążenia."},
        {"start": 4.2, "koniec": 9.8, "tekst": "Serce składa się z czterech jam."},
    ]
    kat = katalog(app_module, transcription_id)
    (kat / "transkrypcja.txt").write_text(
        "\n".join(f"[{i:02d}:00 -> {i:02d}:05] {s['tekst']}" for i, s in enumerate(segmenty)),
        encoding="utf-8",
    )
    (kat / "transkrypcja.json").write_text(
        json.dumps({"dlugosc": dlugosc, "segmenty": segmenty}, ensure_ascii=False), encoding="utf-8"
    )
    (kat / "stan.json").write_text(
        json.dumps(
            {
                "status": "done",
                "postep": 100,
                "komunikat": f"Gotowe: {len(segmenty)} segmentów.",
                "rozpoczeto": datetime.now(timezone.utc).isoformat(),
                "zakonczono": datetime.now(timezone.utc).isoformat(),
                "dlugosc": dlugosc,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


# --------------------------------------------------------------------------- #
# Zgłaszanie nagrań
# --------------------------------------------------------------------------- #
def test_wyslanie_nagrania_tworzy_zadanie(client, app_module):
    register(client)
    odpowiedz = wyslij(client)

    assert odpowiedz.status_code == 201, odpowiedz.text
    dane = odpowiedz.json()
    assert dane["status"] == "queued"
    assert dane["title"] == "Wykład 3"
    assert dane["language"] == "pl"
    assert dane["size_bytes"] > 0
    assert dane["has_audio"] is True

    kat = katalog(app_module, dane["id"])
    assert (kat / "zadanie.json").exists()
    zadanie = json.loads((kat / "zadanie.json").read_text(encoding="utf-8"))
    assert zadanie["jezyk"] == "pl"
    assert (kat / zadanie["plik"]).exists()


def test_tytul_domyslny_z_nazwy_pliku(client):
    register(client)
    odpowiedz = client.post(
        "/api/transkrypcje",
        files={"file": ("Wykład 7 — patofizjologia.m4a", io.BytesIO(b"dane" * 32), "audio/mp4")},
        data={"title": "", "language": "pl"},
    )
    assert odpowiedz.status_code == 201
    assert odpowiedz.json()["title"] == "Wykład 7 — patofizjologia"


def test_nieobslugiwany_format_jest_odrzucany(client):
    register(client)
    odpowiedz = client.post(
        "/api/transkrypcje",
        files={"file": ("notatki.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
        data={"title": "Notatki", "language": "pl"},
    )
    assert odpowiedz.status_code == 415
    assert "Dozwolone rozszerzenia" in odpowiedz.json()["detail"]


def test_pusty_plik_jest_odrzucany(client, app_module):
    register(client)
    odpowiedz = wyslij(client, tresc=b"")

    assert odpowiedz.status_code == 400
    from app.config import settings

    assert list(settings.transcripts_dir.iterdir()) == []


def test_zbyt_duze_nagranie_jest_odrzucane(client, app_module, monkeypatch):
    register(client)
    from app.config import settings

    monkeypatch.setattr(settings, "max_audio_bytes", 1024)
    odpowiedz = wyslij(client, tresc=b"x" * 5000)

    assert odpowiedz.status_code == 413
    assert list(settings.transcripts_dir.iterdir()) == []


def test_transkrypcje_sa_prywatne(client, app_module):
    register(client, "autor", "HasloAutora123")
    identyfikator = wyslij(client).json()["id"]
    client.post("/api/auth/logout")

    register(client, "obcy", "HasloObcego1234")
    assert client.get(f"/api/transkrypcje/{identyfikator}").status_code == 404
    assert client.get("/api/transkrypcje").json() == []
    assert client.delete(f"/api/transkrypcje/{identyfikator}").status_code == 404


# --------------------------------------------------------------------------- #
# Synchronizacja z procesem liczącym
# --------------------------------------------------------------------------- #
def test_postep_z_pliku_trafia_do_odpowiedzi(client, app_module):
    register(client)
    identyfikator = wyslij(client).json()["id"]

    (katalog(app_module, identyfikator) / "stan.json").write_text(
        json.dumps({"status": "running", "postep": 42, "komunikat": "Przetworzono 05:00 z 12:00."}),
        encoding="utf-8",
    )

    dane = client.get(f"/api/transkrypcje/{identyfikator}").json()
    assert dane["status"] == "running"
    assert dane["progress"] == 42
    assert "05:00" in dane["message"]


def test_gotowy_wynik_jest_wczytywany(client, app_module):
    register(client)
    identyfikator = wyslij(client).json()["id"]
    udaj_wynik(app_module, identyfikator)

    dane = client.get(f"/api/transkrypcje/{identyfikator}").json()
    assert dane["status"] == "done"
    assert dane["progress"] == 100
    assert dane["segments_count"] == 2
    assert dane["duration_seconds"] == pytest.approx(92.5)
    assert dane["word_count"] > 0
    assert "układzie krążenia" in dane["text"]
    assert dane["segments"][0]["tekst"].startswith("Dzień dobry")


def test_blad_procesu_jest_raportowany(client, app_module):
    register(client)
    identyfikator = wyslij(client).json()["id"]

    (katalog(app_module, identyfikator) / "stan.json").write_text(
        json.dumps({"status": "error", "komunikat": "Nie powiodło się.", "blad": "CUDA out of memory"}),
        encoding="utf-8",
    )

    dane = client.get(f"/api/transkrypcje/{identyfikator}").json()
    assert dane["status"] == "error"
    assert dane["error_message"] == "CUDA out of memory"


def test_zakonczenie_bez_pliku_wyniku_konczy_sie_bledem(client, app_module):
    """Proces zgłasza sukces, ale nie zostawia transkrypcji — to błąd, nie pusty wynik."""
    register(client)
    identyfikator = wyslij(client).json()["id"]

    (katalog(app_module, identyfikator) / "stan.json").write_text(
        json.dumps({"status": "done", "postep": 100}), encoding="utf-8"
    )

    dane = client.get(f"/api/transkrypcje/{identyfikator}").json()
    assert dane["status"] == "error"
    assert "nie powstał" in dane["error_message"]


def test_ponowienie_wraca_do_kolejki(client, app_module):
    register(client)
    identyfikator = wyslij(client).json()["id"]
    (katalog(app_module, identyfikator) / "stan.json").write_text(
        json.dumps({"status": "error", "blad": "awaria"}), encoding="utf-8"
    )
    assert client.get(f"/api/transkrypcje/{identyfikator}").json()["status"] == "error"

    odpowiedz = client.post(f"/api/transkrypcje/{identyfikator}/ponow")
    assert odpowiedz.status_code == 200
    assert odpowiedz.json()["status"] == "queued"
    assert odpowiedz.json()["error_message"] is None
    assert not (katalog(app_module, identyfikator) / "stan.json").exists()


def test_stan_procesu_liczacego(client, app_module):
    register(client)
    from app.config import settings

    assert client.get("/api/transkrypcje/worker").json()["dostepny"] is False

    (settings.transcripts_dir / "_worker.json").write_text(
        json.dumps({"sygnal": datetime.now(timezone.utc).isoformat(), "urzadzenie": "cuda", "model": "large-v3"}),
        encoding="utf-8",
    )
    stan = client.get("/api/transkrypcje/worker").json()
    assert stan["dostepny"] is True
    assert stan["urzadzenie"] == "cuda"


def test_przestarzaly_sygnal_oznacza_proces_jako_nieczynny(client, app_module):
    register(client)
    from datetime import timedelta

    from app.config import settings

    stary = (datetime.now(timezone.utc) - timedelta(seconds=600)).isoformat()
    (settings.transcripts_dir / "_worker.json").write_text(
        json.dumps({"sygnal": stary, "urzadzenie": "cuda"}), encoding="utf-8"
    )

    stan = client.get("/api/transkrypcje/worker").json()
    assert stan["dostepny"] is False
    assert "nie działa" in stan["opis"]


# --------------------------------------------------------------------------- #
# Eksport
# --------------------------------------------------------------------------- #
@pytest.fixture()
def gotowa_transkrypcja(client, app_module):
    register(client)
    identyfikator = wyslij(client).json()["id"]
    udaj_wynik(app_module, identyfikator)
    client.get(f"/api/transkrypcje/{identyfikator}")
    return identyfikator


def test_pobranie_txt_ze_znacznikami(client, gotowa_transkrypcja):
    odpowiedz = client.get(f"/api/transkrypcje/{gotowa_transkrypcja}/pobierz?format=txt")

    assert odpowiedz.status_code == 200
    assert odpowiedz.headers["content-type"].startswith("text/plain")
    assert "attachment" in odpowiedz.headers["content-disposition"]
    tresc = odpowiedz.content.decode("utf-8")
    assert "Wykład 3" in tresc
    assert "[00:00 ->" in tresc


def test_pobranie_samego_tekstu_usuwa_znaczniki(client, gotowa_transkrypcja):
    tresc = client.get(f"/api/transkrypcje/{gotowa_transkrypcja}/pobierz?format=tekst").content.decode("utf-8")

    assert "[00:00" not in tresc
    assert "Dzień dobry" in tresc
    assert "Serce składa się" in tresc


def test_pobranie_markdown(client, gotowa_transkrypcja):
    odpowiedz = client.get(f"/api/transkrypcje/{gotowa_transkrypcja}/pobierz?format=md")

    assert odpowiedz.status_code == 200
    assert odpowiedz.headers["content-type"].startswith("text/markdown")
    tresc = odpowiedz.content.decode("utf-8")
    assert tresc.startswith("# Wykład 3")
    assert "**[00:00]**" in tresc


def test_pobranie_pdf(client, gotowa_transkrypcja):
    odpowiedz = client.get(f"/api/transkrypcje/{gotowa_transkrypcja}/pobierz?format=pdf")

    assert odpowiedz.status_code == 200
    assert odpowiedz.headers["content-type"] == "application/pdf"
    assert odpowiedz.content.startswith(b"%PDF")
    assert len(odpowiedz.content) > 1000


def test_pobranie_przed_zakonczeniem_jest_blokowane(client, app_module):
    register(client)
    identyfikator = wyslij(client).json()["id"]

    odpowiedz = client.get(f"/api/transkrypcje/{identyfikator}/pobierz?format=txt")
    assert odpowiedz.status_code == 409
    assert "nie jest jeszcze gotowa" in odpowiedz.json()["detail"]


# --------------------------------------------------------------------------- #
# Operacje na zadaniu
# --------------------------------------------------------------------------- #
def test_zmiana_nazwy(client, gotowa_transkrypcja):
    odpowiedz = client.patch(f"/api/transkrypcje/{gotowa_transkrypcja}", json={"title": "Krążenie — powtórka"})

    assert odpowiedz.status_code == 200
    assert odpowiedz.json()["title"] == "Krążenie — powtórka"


def test_usuniecie_samego_nagrania_zachowuje_tekst(client, gotowa_transkrypcja, app_module):
    odpowiedz = client.delete(f"/api/transkrypcje/{gotowa_transkrypcja}/nagranie")
    assert odpowiedz.status_code == 200

    dane = client.get(f"/api/transkrypcje/{gotowa_transkrypcja}").json()
    assert dane["has_audio"] is False
    assert dane["text"]
    # Ponowienie bez nagrania nie ma sensu i musi zostać zablokowane.
    assert client.post(f"/api/transkrypcje/{gotowa_transkrypcja}/ponow").status_code == 409


def test_usuniecie_transkrypcji_kasuje_katalog(client, gotowa_transkrypcja, app_module):
    kat = katalog(app_module, gotowa_transkrypcja)
    assert kat.exists()

    assert client.delete(f"/api/transkrypcje/{gotowa_transkrypcja}").status_code == 200
    assert not kat.exists()
    assert client.get("/api/transkrypcje").json() == []


def test_usuniecie_konta_kasuje_transkrypcje(client, app_module):
    """Kasowanie konta nie może zostawiać osieroconych rekordów."""
    register(client, "student", "HasloStudenta123")
    wyslij(client)
    client.post("/api/auth/logout")

    from conftest import unlock_admin

    unlock_admin(client)
    cel = next(u for u in client.get("/api/admin/users").json() if u["username"] == "student")
    assert client.delete(f"/api/admin/users/{cel['id']}").status_code == 200

    from app.database import session_scope
    from app.models import Transcription

    with session_scope() as db:
        assert db.query(Transcription).count() == 0


def test_transkrypcje_wymagaja_zalogowania(client):
    assert client.get("/api/transkrypcje").status_code == 401
    assert client.get("/api/transkrypcje/worker").status_code == 401


# --------------------------------------------------------------------------- #
# Rozpoznawanie trybu pracy procesu
# --------------------------------------------------------------------------- #
def _zapisz_sygnal(app_module, **pola):
    from app.config import settings

    dane = {"sygnal": datetime.now(timezone.utc).isoformat(), "model": "large-v3", **pola}
    (settings.transcripts_dir / "_worker.json").write_text(json.dumps(dane), encoding="utf-8")


def test_brak_sygnalu_sugeruje_instalacje_uslugi(client, app_module):
    register(client)
    stan = client.get("/api/transkrypcje/worker").json()

    assert stan["dostepny"] is False
    assert stan["tryb"] == "brak"
    assert "nie została jeszcze zainstalowana" in stan["opis"]


def test_usluga_w_spoczynku(client, app_module):
    register(client)
    _zapisz_sygnal(app_module, urzadzenie="cuda", tryb="usluga")

    stan = client.get("/api/transkrypcje/worker").json()
    assert stan["dostepny"] is True
    assert stan["tryb"] == "usluga"
    assert "czeka na nagrania" in stan["opis"]
    assert "cuda" in stan["opis"]


def test_proces_uruchomiony_recznie_jest_rozpoznawany(client, app_module):
    """Praca z terminala kończy się wraz z sesją — interfejs ma o tym uprzedzić."""
    register(client)
    _zapisz_sygnal(app_module, urzadzenie="cuda", tryb="reczny")

    stan = client.get("/api/transkrypcje/worker").json()
    assert stan["dostepny"] is True
    assert stan["tryb"] == "reczny"
    assert "ręcznie" in stan["opis"]


def test_sygnal_w_trakcie_pracy_pokazuje_zadanie(client, app_module):
    register(client)
    _zapisz_sygnal(app_module, urzadzenie="cuda", tryb="usluga", zadanie="Wykład 3")

    stan = client.get("/api/transkrypcje/worker").json()
    assert stan["dostepny"] is True
    assert stan["zadanie"] == "Wykład 3"
    assert "Wykład 3" in stan["opis"]


def test_milczaca_usluga_jest_odrozniana_od_niezainstalowanej(client, app_module):
    from datetime import timedelta

    register(client)
    _zapisz_sygnal(
        app_module,
        urzadzenie="cuda",
        tryb="usluga",
        sygnal=(datetime.now(timezone.utc) - timedelta(seconds=600)).isoformat(),
    )

    stan = client.get("/api/transkrypcje/worker").json()
    assert stan["dostepny"] is False
    assert stan["tryb"] == "usluga"
    assert "nie odpowiada" in stan["opis"]
