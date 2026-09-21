# Współpraca przy projekcie

Dziękuję za zainteresowanie. Poniżej krótki przewodnik, jak zgłaszać zmiany.

## Zasady ogólne

- **Językiem projektu jest polski** — dotyczy to tekstów interfejsu, komunikatów
  błędów, komentarzy w kodzie, docstringów, nazw testów i dokumentacji.
  Wyjątkiem są identyfikatory techniczne formatu wymiany JSON (`front`, `back`,
  `is_correct`, `visibility`), które muszą pozostać stabilne.
- Ścieżki widoków HTML są polskie (`/pulpit`, `/baza-publiczna`, `/zestawy/{id}/fiszki`),
  ścieżki API angielskie (`/api/sets`, `/api/study/sessions`).
- Nie zostawiaj komentarzy `TODO` ani niedokończonych funkcji na gałęzi `main`.

## Środowisko

```bash
cd frontend && npm ci && npm run build && cd ..
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
QUIZAPP_DATA_DIR=./data .venv/bin/uvicorn app.main:app --reload --port 8000
```

## Testy

Każda zmiana zachowania wymaga testu. Zestaw musi przechodzić w całości:

```bash
.venv/bin/python -m pytest
```

Testy pracują na własnej bazie tymczasowej — nie dotykają katalogu `./data`.
Przy zmianach w parserze importu uzupełnij `tests/test_importer.py`, a przy
zmianach materiałów w `przyklady/` — `tests/test_przyklady.py`.

## Zmiany w formacie wymiany JSON

Plik `AI_SCHEMA.md` jest kontraktem dla modeli językowych. Jeżeli zmieniasz format:

1. zaktualizuj tabele pól i schemat formalny w `AI_SCHEMA.md`,
2. zaktualizuj prompt systemowy w tym pliku oraz jego kopię w `app/static/js/importer.js`,
3. sprawdź, czy przechodzi `tests/test_importer.py::test_przyklad_ze_specyfikacji_ai_schema_jest_importowalny`,
4. zadbaj o wsteczną zgodność — parser ma tolerować stary format.

## Zgłaszanie zmian

1. Utwórz gałąź: `git checkout -b nazwa-zmiany`.
2. Zadbaj, aby `pytest` przechodził, a `docker compose build` kończył się powodzeniem.
3. Opisz w treści pull requesta, co się zmienia i dlaczego.

Komunikaty commitów piszemy po polsku, w trybie oznajmującym, np.
`Dodaje filtr trudnych fiszek w trybie nauki`.
