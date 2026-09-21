<h1 align="center">MTQuiz</h1>

<p align="center">
  Samohostowana platforma do nauki — fiszki i quizy z dowolnego przedmiotu.
</p>

<p align="center">
  <a href="https://github.com/MarcinTyszko/MTQuiz/actions/workflows/ci.yml">
    <img alt="Status CI" src="https://github.com/MarcinTyszko/MTQuiz/actions/workflows/ci.yml/badge.svg">
  </a>
  <img alt="Python 3.12" src="https://img.shields.io/badge/python-3.12-3776AB?logo=python&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white">
  <img alt="Docker" src="https://img.shields.io/badge/Docker-compose-2496ED?logo=docker&logoColor=white">
  <img alt="Licencja MIT" src="https://img.shields.io/badge/licencja-MIT-green">
  <img alt="Testy" src="https://img.shields.io/badge/testy-125%20pytest-brightgreen">
</p>

---

Alternatywa dla Quizleta, którą uruchamiasz na własnym serwerze. Tworzysz zestawy fiszek
i pytań testowych — ręcznie w edytorze albo generując je modelem językowym z własnych
notatek i plików PDF. Nadaje się tak samo do anatomii, prawa cywilnego, Kubernetesa,
historii i nauki języka obcego. Dane nie opuszczają Twojej maszyny.

```
FastAPI + SQLAlchemy 2 + SQLite   ·   Jinja2 + Tailwind CSS + Alpine.js   ·   Docker
```

**Uruchomienie w trzech poleceniach:**

```bash
cp .env.example .env
sed -i "s|^QUIZAPP_UID=.*|QUIZAPP_UID=$(id -u)|; s|^QUIZAPP_GID=.*|QUIZAPP_GID=$(id -g)|" .env
docker compose up -d --build
```

Interfejs: **http://localhost:8080** · pierwsze logowanie: `admin` / `admin` (hasło trzeba
od razu zmienić) · gotowe materiały do testów: [`przyklady/`](przyklady/).

---

## Spis treści

1. [Możliwości](#możliwości)
2. [Szybki start](#szybki-start)
3. [Pierwsze logowanie](#pierwsze-logowanie)
4. [Konfiguracja](#konfiguracja)
5. [Import materiału z Claude CLI](#import-materiału-z-claude-cli)
6. [Kopie zapasowe — instrukcja operacyjna](#kopie-zapasowe--instrukcja-operacyjna)
7. [Praca nad kodem](#praca-nad-kodem)
8. [Struktura projektu](#struktura-projektu)
9. [API](#api)
10. [Rozwiązywanie problemów](#rozwiązywanie-problemów)

---

## Możliwości

**Nauka**
- **Tryb fiszek** — obrót karty w 3D (klik, spacja lub dotknięcie), nawigacja klawiaturą
  i gestami przesunięcia, losowanie kolejności, oznaczanie trudnych kart, filtr
  „tylko trudne”, podsumowanie sesji z czasem nauki.
- **Tryb quizu** — wybór liczby pytań, tryb *Nauka* (odpowiedź sprawdzana natychmiast,
  z wyjaśnieniem) albo *Egzamin* (wynik na końcu), opcjonalny limit czasu, losowanie
  pytań i wariantów, wynik procentowy, szczegółowe omówienie i powtórka samych błędów.
- Pytania jednokrotnego i wielokrotnego wyboru, komentarz do każdego wariantu odpowiedzi.

**Zestawy („teczki nauki”)**
- Tytuł, opis, przedmiot, tagi, widoczność prywatna lub publiczna.
- Rozbudowany edytor GUI: dodawanie, duplikowanie, zmiana kolejności i usuwanie
  fiszek oraz pytań, walidacja przed zapisem, ostrzeżenie przed utratą zmian.
- Eksport i import pojedynczego zestawu w formacie JSON.

**Generator promptu AI**
- Kreator w zakładce **Prompt AI**: ustawiasz dziedzinę, temat, poziom odbiorcy, liczbę fiszek
  i pytań, układ językowy oraz rygor źródeł, a aplikacja składa gotowe do wklejenia polecenie.
- **Niezależny od dziedziny.** Siedem profili — uniwersalny, nauki ścisłe, medycyna, prawo,
  technologia i IT, języki obce, humanistyka — dobiera listę wiarygodnych źródeł, dodatkowe
  zasady rygoru oraz przykład w prompcie. Listę źródeł możesz nadpisać własną.
- Prompt sam opisuje modelowi strukturę pliku JSON — nie trzeba dołączać dokumentacji.
- Neutralny wobec dostawcy: **Claude CLI, Claude w przeglądarce, ChatGPT, Gemini** oraz modele
  lokalne, z osobną instrukcją obsługi dla każdego z nich.
- Rozbudowany blok zasad ograniczających konfabulację: zakaz podawania niepewnych liczb, dat
  i oznaczeń, wymóg pomijania zagadnień niepewnych, opcjonalne wskazanie źródła w każdej fiszce.
  Profile dokładają zasady branżowe — stan prawny, wersję oprogramowania, jednostki wielkości,
  rejestr językowy czy oddzielenie faktu od interpretacji.

**Silnik importu AI**
- Wgranie pliku `.json` (przeciągnij i upuść) albo wklejenie treści.
- Parser odporny na typowe odstępstwa modeli językowych: bloki ```` ```json ````,
  przecinki wiszące, polskie i angielskie nazwy pól, wskazanie poprawnej odpowiedzi
  literą, indeksem lub treścią.
- Ekran walidacji z listą pominiętych elementów i powodem pominięcia.
- Przejście do edytora w celu poprawienia treści przed zapisem.

**Baza publiczna**
- Wyszukiwanie po tytule, opisie i przedmiocie, filtrowanie po tagach.
- Sortowanie: najnowsze, najpopularniejsze, alfabetycznie, ostatnio zmieniane.
- Dodawanie do ulubionych (przypięcie do pulpitu) oraz kopiowanie zestawu
  do własnej biblioteki z zachowaniem odnośnika do oryginału.

**Konta i administracja**
- Uwierzytelnianie sesyjne (JWT w ciasteczku `HttpOnly`), hasła hashowane Argon2id.
- Role `user` i `admin`; zmiana hasła unieważnia wszystkie wcześniejsze sesje.
- Panel administratora: statystyki instancji, zarządzanie kontami (blokada, rola,
  reset hasła, usunięcie), moderacja bazy publicznej, dziennik zdarzeń.
- Kopie zapasowe: pobranie archiwum ZIP jednym kliknięciem oraz przywrócenie bazy
  z automatyczną kopią bezpieczeństwa stanu sprzed operacji.

**Interfejs**
- Motyw jasny i ciemny z zapamiętaniem wyboru (`localStorage`) i domyślnym
  ustawieniem systemowym.
- Pełna responsywność: przyklejone paski akcji i powiększone obszary dotyku na
  telefonie, układ wielokolumnowy na tablecie i komputerze.
- Obsługa klawiatury i czytników ekranu, poszanowanie `prefers-reduced-motion`.

---

## Szybki start

**Wymagania:** Docker 24+ z wtyczką Compose. Nic więcej — Python i Node.js są
potrzebne wyłącznie do pracy nad kodem.

```bash
git clone <adres-repozytorium> mtquiz
cd mtquiz

# 1. Konfiguracja
cp .env.example .env
sed -i "s|^QUIZAPP_SECRET_KEY=.*|QUIZAPP_SECRET_KEY=$(openssl rand -base64 48)|" .env
sed -i "s|^QUIZAPP_UID=.*|QUIZAPP_UID=$(id -u)|; s|^QUIZAPP_GID=.*|QUIZAPP_GID=$(id -g)|" .env

# 2. Uruchomienie
docker compose up -d --build

# 3. Sprawdzenie stanu
docker compose ps
curl http://localhost:8080/healthz
```

Aplikacja działa pod adresem **http://localhost:8080**.

> `QUIZAPP_UID` i `QUIZAPP_GID` decydują o tożsamości procesu w kontenerze. Ustawienie
> ich na właściciela katalogu `./data` sprawia, że proces nie działa z uprawnieniami
> administratora, a pliki kopii zapasowych czytasz na hoście bez `sudo`.

| Element | Wartość |
|---|---|
| Port na hoście | `8080`, zmienny przez `QUIZAPP_PORT` (kontener nasłuchuje na `8000`) |
| Katalog danych | `./data` → `/data` w kontenerze |
| Plik bazy | `./data/quizapp.db` |
| Kopie zapasowe | `./data/backups/` |
| Klucz podpisu sesji | `./data/.secret_key` (generowany, gdy nie ustawiono zmiennej) |
| Dokumentacja API | http://localhost:8080/api/docs |
| Sonda zdrowia | http://localhost:8080/healthz |

Zatrzymanie i aktualizacja:

```bash
docker compose down                 # zatrzymanie (dane w ./data pozostają)
git pull && docker compose up -d --build   # aktualizacja do nowej wersji
docker compose logs -f mtquiz    # podgląd logów
```

---

## Pierwsze logowanie

Przy pierwszym starcie na pustej bazie aplikacja tworzy konto administratora
i dodaje jeden przykładowy zestaw publiczny (*Neuroanatomia — nerwy czaszkowe I–XII*),
który stanowi wzorzec formatu importu.

| | |
|---|---|
| Login | `admin` |
| Hasło | `admin` |

Po zalogowaniu aplikacja **wymusi ustawienie własnego hasła** — do tego czasu
wszystkie funkcje pozostają zablokowane, a przejście na dowolną stronę przekierowuje
na formularz zmiany hasła. Nowe hasło musi mieć co najmniej 8 znaków i różnić się
od dotychczasowego. Zmiana hasła unieważnia wszystkie wydane wcześniej tokeny sesji.

Kolejne konta powstają przez formularz rejestracji. Aby zamknąć instancję na
rejestrację z zewnątrz, ustaw `QUIZAPP_ALLOW_REGISTRATION=false` i utwórz konta
z poziomu panelu administratora.

Przykładowy zestaw możesz usunąć jak każdy inny (strona zestawu → *Usuń*).
Aby nie tworzył się na nowych instancjach, ustaw `QUIZAPP_SEED_EXAMPLE_SET=false`.

---

## Konfiguracja

Wszystkie ustawienia przekazywane są zmiennymi środowiskowymi z przedrostkiem
`QUIZAPP_` (plik `.env` obok `docker-compose.yml`).

| Zmienna | Domyślnie | Opis |
|---|---|---|
| `QUIZAPP_PORT` | `8080` | Port na hoście (tylko `docker-compose.yml`). |
| `QUIZAPP_UID` / `QUIZAPP_GID` | `1000` | Tożsamość procesu w kontenerze; ustaw na właściciela katalogu `./data` (`id -u`, `id -g`). |
| `QUIZAPP_SECRET_KEY` | *(generowany)* | Klucz podpisu tokenów sesji. Bez niego generowany jest trwały klucz w `./data/.secret_key`. Ustaw własny, jeśli chcesz zachować sesje po odtworzeniu wolumenu. |
| `QUIZAPP_DATA_DIR` | `/data` | Katalog danych trwałych. |
| `QUIZAPP_COOKIE_SECURE` | `false` | Ustaw `true` przy pracy za odwrotnym proxy z HTTPS. |
| `QUIZAPP_COOKIE_SAMESITE` | `lax` | Polityka `SameSite` ciasteczka sesji. |
| `QUIZAPP_SESSION_TTL_MINUTES` | `20160` | Czas życia sesji (domyślnie 14 dni). |
| `QUIZAPP_ALLOW_REGISTRATION` | `true` | Samodzielna rejestracja kont. |
| `QUIZAPP_SEED_EXAMPLE_SET` | `true` | Dodanie zestawu pokazowego na czystej bazie. |
| `QUIZAPP_BOOTSTRAP_ADMIN_USERNAME` | `admin` | Nazwa konta startowego. |
| `QUIZAPP_BOOTSTRAP_ADMIN_PASSWORD` | `admin` | Hasło startowe (i tak wymaga zmiany przy pierwszym logowaniu). |
| `QUIZAPP_MAX_UPLOAD_BYTES` | `26214400` | Limit rozmiaru importowanego pliku JSON (25 MB). |
| `QUIZAPP_MAX_RESTORE_BYTES` | `536870912` | Limit rozmiaru przywracanej kopii (512 MB). |
| `QUIZAPP_APP_NAME` | `MTQuiz` | Nazwa instancji w interfejsie. |

### Praca za odwrotnym proxy

Kontener ufa nagłówkom `X-Forwarded-*`. Przykładowa konfiguracja Nginx:

```nginx
server {
    server_name fiszki.example.com;

    location / {
        proxy_pass         http://127.0.0.1:8080;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        client_max_body_size 550M;   # wymagane do przywracania kopii zapasowych
    }
}
```

Przy HTTPS ustaw dodatkowo `QUIZAPP_COOKIE_SECURE=true`.

---

## Import materiału z Claude CLI

Najszybsza droga prowadzi przez zakładkę **Prompt AI** (`/generator-promptu`): wybierasz profil
dziedziny, ustawiasz parametry materiału, kopiujesz wygenerowane polecenie i wklejasz je do
dowolnego modelu. Generator nie jest przypisany do jednej dyscypliny — działa tak samo dla
anatomii, prawa cywilnego, Kubernetesa, historii i nauki języka obcego.
Pełna specyfikacja formatu znajduje się w pliku **[`AI_SCHEMA.md`](AI_SCHEMA.md)**.

Skrócony przebieg z wiersza poleceń:

```bash
# 1. Wygenerowanie pakietu z notatek
claude -p "$(cat AI_SCHEMA.md)

Przetwórz plik ./materialy/wyklad-03.pdf. Zwróć wyłącznie JSON." \
  > pakiet.json

# 2. Szybka kontrola składni
python3 -m json.tool pakiet.json > /dev/null && echo "JSON poprawny"
```

3. W aplikacji: **Import AI → Plik .json → Sprawdź pakiet**.
4. Przejrzyj raport walidacji (liczba fiszek i pytań, elementy pominięte wraz z powodem).
5. **Otwórz w edytorze i popraw** — nanieś zmiany, po czym zapisz zestaw.

Parser toleruje najczęstsze odstępstwa modeli (bloki markdown, polskie nazwy pól,
wskazanie odpowiedzi literą lub indeksem) i zamiast przerywać import, pomija
uszkodzone elementy z czytelnym komunikatem. Szczegółowa lista wariantów:
sekcja 4 pliku `AI_SCHEMA.md`.

Prompt systemowy można też skopiować bezpośrednio z interfejsu — przycisk
**„Skopiuj prompt systemowy”** na stronie *Import AI*.

### Materiały testowe

Katalog [`przyklady/`](przyklady/) zawiera gotowe pakiety pozwalające sprawdzić aplikację
bez czekania na własne materiały — **nazewnictwo anatomiczne po łacinie, polsku i angielsku**
(kości, mięśnie, narządy wewnętrzne, mianownictwo kierunków i płaszczyzn; łącznie 143 fiszki
i 22 pytania). Znajdziesz tam również plik `05-surowa-odpowiedz-modelu.txt` celowo zapisany
w zniekształconym formacie — sprawdza odporność parsera i sposób raportowania pominiętych
elementów. Szczegóły: [`przyklady/README.md`](przyklady/README.md).

---

## Kopie zapasowe — instrukcja operacyjna

### Kopia z poziomu interfejsu

**Panel → Kopie zapasowe → Pobierz kopię zapasową**

Aplikacja tworzy spójną migawkę bazy (API `sqlite3.backup`, bezpieczne nawet podczas
zapisu) i pakuje ją w archiwum ZIP zawierające:

```
mtquiz-backup-RRRRMMDD-GGMMSS.zip
├── quizapp.db      # kompletna baza danych
└── manifest.json   # data utworzenia, rozmiar, liczności tabel
```

Archiwum trafia jednocześnie do przeglądarki i do katalogu `./data/backups/`
(przechowywanych jest 10 najnowszych).

### Kopia z poziomu powłoki

```bash
# Migawka bez zatrzymywania aplikacji
docker compose exec mtquiz \
  python -c "from app.backup import create_backup_archive; print(create_backup_archive()[0])"

# Skopiowanie archiwów na maszynę kopii zapasowych
rsync -av ./data/backups/ kopie@nas:/wolumen/mtquiz/
```

Do zadania w `cron` (codziennie o 3:00):

```cron
0 3 * * * cd /opt/mtquiz && docker compose exec -T mtquiz \
  python -c "from app.backup import create_backup_archive; create_backup_archive()" >> /var/log/mtquiz-backup.log 2>&1
```

Najprostszy wariant przy zatrzymanej aplikacji to zwykłe skopiowanie katalogu:

```bash
docker compose stop mtquiz
tar czf mtquiz-$(date +%F).tar.gz ./data
docker compose start mtquiz
```

### Przywracanie

**Panel → Kopie zapasowe → Przywróć bazę**

1. Wskaż archiwum `.zip` utworzone przez aplikację albo surowy plik `.db`.
2. Potwierdź operację, wpisując `PRZYWROC` w oknie potwierdzenia.
3. Aplikacja weryfikuje plik przed nadpisaniem: nagłówek SQLite, `PRAGMA integrity_check`,
   obecność wymaganych tabel oraz istnienie co najmniej jednego konta administratora.
4. Stan sprzed operacji zapisywany jest automatycznie jako
   `./data/backups/mtquiz-przed-przywroceniem-*.db`.
5. Po przywróceniu zaloguj się ponownie — tokeny sesji pochodzą z przywróconej bazy.

Przywracanie z powłoki (przy zatrzymanej aplikacji):

```bash
docker compose stop mtquiz
unzip -o mtquiz-backup-20260921-030000.zip quizapp.db -d ./data
rm -f ./data/quizapp.db-wal ./data/quizapp.db-shm
docker compose start mtquiz
```

> **Uwaga:** przywrócenie zastępuje wszystkie dane — konta, zestawy i historię nauki.
> Operacji nie da się cofnąć inaczej niż przez odtworzenie automatycznej kopii
> bezpieczeństwa z katalogu `./data/backups/`.

---

## Narzędzia administracyjne (wiersz poleceń)

Moduł `app.cli` pozwala odzyskać dostęp i wykonać kopię bez wchodzenia do interfejsu.

```bash
# lista kont wraz ze stanem
docker compose exec mtquiz python -m app.cli konta

# przywrócenie konta admin do hasła startowego "admin"
# (aplikacja poprosi o ustawienie własnego hasła przy pierwszym logowaniu)
docker compose exec mtquiz python -m app.cli reset-admina

# własne hasło zamiast startowego
docker compose exec mtquiz python -m app.cli reset-admina --haslo TwojeNoweHaslo123

# odzyskanie innego konta i nadanie mu uprawnień administratora
docker compose exec mtquiz python -m app.cli reset-admina --login marcin

# nowe konto administratora z losowym hasłem
docker compose exec mtquiz python -m app.cli utworz-admina zapasowy

# kopia zapasowa do ./data/backups
docker compose exec mtquiz python -m app.cli kopia-zapasowa
```

Przy pracy lokalnej zamiast `docker compose exec mtquiz` użyj `.venv/bin/python`.

## Praca nad kodem

### Środowisko lokalne

```bash
# Zasoby statyczne (Tailwind CSS + Alpine.js)
cd frontend && npm install && npm run build && cd ..

# Środowisko Pythona
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt

# Uruchomienie z przeładowywaniem
QUIZAPP_DATA_DIR=./data .venv/bin/uvicorn app.main:app --reload --port 8000
```

Podczas pracy nad stylami uruchom w osobnym terminalu obserwatora Tailwinda:

```bash
cd frontend && npm run watch:css
```

### Testy

```bash
.venv/bin/python -m pytest              # cały zestaw
.venv/bin/python -m pytest -v tests/test_importer.py   # sam parser importu
```

Zestaw obejmuje uwierzytelnianie i role, wymuszoną zmianę hasła, operacje na
zestawach i kontrolę widoczności, odporność parsera JSON na odstępstwa formatu,
sesje nauki i statystyki, moderację, a także pełny cykl kopia zapasowa → przywrócenie.
Każdy test pracuje na własnej, tymczasowej bazie.

---

## Struktura projektu

```
.
├── app/
│   ├── main.py             # aplikacja FastAPI, obsługa błędów, montowanie routerów
│   ├── config.py           # ustawienia ze zmiennych środowiskowych
│   ├── database.py         # silnik SQLAlchemy, sesje, ponowne otwarcie po przywróceniu
│   ├── models.py           # modele ORM
│   ├── schemas.py          # walidacja wejścia i serializacja (Pydantic)
│   ├── security.py         # Argon2id, tokeny sesji JWT
│   ├── deps.py             # zależności FastAPI, kontrola ról, ciasteczko sesji
│   ├── services.py         # logika biznesowa zestawów, tagi, statystyki
│   ├── importer.py         # uniwersalny parser pakietów JSON
│   ├── backup.py           # kopie zapasowe i przywracanie bazy
│   ├── bootstrap.py        # konto startowe i zestaw pokazowy
│   ├── cli.py              # narzędzia administracyjne wiersza poleceń
│   ├── templating.py       # Jinja2: filtry, wersjonowanie zasobów
│   ├── routers/            # auth, sets, study, admin, pages
│   ├── templates/          # widoki HTML
│   ├── static/             # CSS, JS, zasoby zewnętrzne
│   └── data/               # przykładowy pakiet JSON
├── frontend/               # źródła Tailwind CSS i skrypt kopiujący zależności
├── tests/                  # testy pytest
├── data/                   # wolumen danych (baza, kopie zapasowe) — poza repozytorium
├── Dockerfile              # obraz wieloetapowy, użytkownik bez uprawnień root
├── docker-compose.yml
├── AI_SCHEMA.md            # specyfikacja formatu JSON i prompt dla Claude CLI
└── README.md
```

---

## API

Interaktywna dokumentacja: `/api/docs`. Uwierzytelnianie odbywa się ciasteczkiem
sesji albo nagłówkiem `Authorization: Bearer <token>`.

| Metoda | Ścieżka | Opis |
|---|---|---|
| `POST` | `/api/auth/register` | Rejestracja konta |
| `POST` | `/api/auth/login` | Logowanie |
| `POST` | `/api/auth/logout` | Wylogowanie |
| `GET` | `/api/auth/me` | Dane bieżącego konta |
| `POST` | `/api/auth/change-password` | Zmiana hasła |
| `GET` | `/api/sets` | Biblioteka użytkownika |
| `POST` | `/api/sets` | Utworzenie zestawu |
| `GET` `PUT` `DELETE` | `/api/sets/{id}` | Odczyt, aktualizacja, usunięcie |
| `POST` | `/api/sets/{id}/fork` | Kopia do własnej biblioteki |
| `POST` `DELETE` | `/api/sets/{id}/favorite` | Ulubione |
| `GET` | `/api/sets/{id}/export` | Eksport JSON |
| `POST` | `/api/cards/{id}/star` | Oznaczenie trudnej fiszki |
| `GET` | `/api/public/sets` | Baza publiczna (`q`, `tag`, `sort`, `limit`, `offset`) |
| `GET` | `/api/public/tags` | Najczęstsze tagi |
| `POST` | `/api/import/validate` | Walidacja pakietu z tekstu |
| `POST` | `/api/import/upload` | Walidacja przesłanego pliku |
| `POST` | `/api/import/commit` | Walidacja i zapis zestawu |
| `POST` `GET` | `/api/study/sessions` | Zapis i historia sesji nauki |
| `GET` | `/api/study/stats` | Statystyki pulpitu |
| `GET` | `/api/admin/stats` | Statystyki instancji |
| `GET` `PATCH` `DELETE` | `/api/admin/users[/{id}]` | Zarządzanie kontami |
| `POST` | `/api/admin/users/{id}/reset-password` | Reset hasła |
| `GET` `PATCH` `DELETE` | `/api/admin/sets[/{id}]` | Moderacja zestawów |
| `POST` | `/api/admin/backup` | Pobranie kopii zapasowej |
| `POST` | `/api/admin/restore?confirm=PRZYWROC` | Przywrócenie bazy |
| `GET` | `/api/admin/audit` | Dziennik zdarzeń |

---

## Rozwiązywanie problemów

**Nie mogę się zalogować na konto `admin`.**
Konto startowe powstaje tylko wtedy, gdy w bazie nie ma żadnego administratora, a jego hasło
mogło zostać wcześniej zmienione. Przywróć hasło startowe jednym poleceniem:

```bash
docker compose exec mtquiz python -m app.cli reset-admina
```

Następnie zaloguj się jako `admin` / `admin` — aplikacja od razu poprosi o ustawienie własnego
hasła. Listę wszystkich kont pokaże `python -m app.cli konta`.

**Kontener zatrzymuje się z komunikatem „Brak prawa zapisu do katalogu danych”.**
Proces w kontenerze ma inne UID niż właściciel katalogu `./data`. Ustaw w pliku `.env`:

```bash
printf "QUIZAPP_UID=%s\nQUIZAPP_GID=%s\n" "$(id -u)" "$(id -g)" >> .env
docker compose up -d
```

Alternatywnie nadaj katalogowi właściciela zgodnego z konfiguracją:
`sudo chown -R 1000:1000 ./data`.

**Port 8080 jest już zajęty.**
Ustaw inny port w pliku `.env`, np. `QUIZAPP_PORT=8099`, i uruchom `docker compose up -d`.

**Interfejs wygląda na pozbawiony stylów.**
Arkusz `app/static/css/app.css` powstaje na etapie budowania obrazu. Przy pracy
lokalnej uruchom `cd frontend && npm install && npm run build`.

**Import kończy się komunikatem „Niepoprawna składnia JSON”.**
Sprawdź plik poleceniem `python3 -m json.tool pakiet.json`. Najczęstsze przyczyny to
ucięta odpowiedź modelu (przerwany plik) oraz kodowanie inne niż UTF-8. Bloki
```` ```json ```` i przecinki wiszące są usuwane automatycznie.

**Przywracanie kopii zwraca błąd 413.**
Odwrotne proxy ogranicza rozmiar żądania — zwiększ `client_max_body_size`
(Nginx) lub odpowiednik w innym serwerze.

**Baza wydaje się zablokowana przy dużym obciążeniu.**
SQLite pracuje w trybie WAL z limitem oczekiwania 10 s. Upewnij się, że katalog
`./data` znajduje się na lokalnym systemie plików — udziały sieciowe (NFS, SMB)
nie gwarantują poprawnego blokowania plików.

**Sesje wygasają po każdym odtworzeniu kontenera.**
Ustaw stałą wartość `QUIZAPP_SECRET_KEY` w pliku `.env`, zamiast polegać na kluczu
generowanym w katalogu danych.

---

## Współpraca

Wskazówki dla osób zgłaszających zmiany: [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Licencja

Projekt udostępniony na licencji [MIT](LICENSE) — Copyright (c) 2026 Marcin Tyszko.
