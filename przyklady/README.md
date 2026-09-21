# Materiały testowe

Gotowe pakiety nauki w formacie `medfiszki/study-set`, służące do sprawdzenia
wszystkich funkcji aplikacji bez czekania na własne materiały. Tematyka: **nazewnictwo
anatomiczne w trzech językach** — łacińskim (Terminologia Anatomica), polskim i angielskim.

Każda fiszka ma tę samą budowę:

| Element | Zawartość |
|---|---|
| Awers | nazwa łacińska, np. `Os frontale` |
| Rewers | `polski: kość czołowa` / `angielski: frontal bone` |
| Wskazówka | okolica ciała lub układ, np. „Czaszka — mózgoczaszka” |
| Notatka | fakt czynnościowy lub kliniczny |

## Zawartość katalogu

| Plik | Zestaw | Fiszki | Pytania |
|---|---|---:|---:|
| `01-kosci-lacina-polski-angielski.json` | Kości szkieletu — od czaszki po stopę | 38 | 6 |
| `02-miesnie-lacina-polski-angielski.json` | Mięśnie szkieletowe z unerwieniem i funkcją | 32 | 5 |
| `03-narzady-wewnetrzne-lacina-polski-angielski.json` | Narządy wewnętrzne w podziale na układy | 35 | 6 |
| `04-mianownictwo-kierunki-i-plaszczyzny.json` | Kierunki, płaszczyzny, ruchy i okolice brzucha | 38 | 5 |
| `05-surowa-odpowiedz-modelu.txt` | **Test odporności parsera** — celowo zniekształcony format | 6 | 3 |

Razem **143 fiszki** i **22 pytania** w pakietach poprawnych.

## Jak zaimportować

1. Zaloguj się i przejdź do **Import AI**.
2. Zakładka **Plik .json** → przeciągnij wybrany plik albo kliknij, aby go wskazać.
3. Sprawdź raport walidacji i wybierz **Zapisz od razu** lub **Otwórz w edytorze i popraw**.

Import z wiersza poleceń (po zalogowaniu i zapisaniu ciasteczka sesji):

```bash
curl -s -b ciasteczka.txt -X POST http://localhost:8090/api/import/commit \
     -H 'Content-Type: application/json' \
     -d "{\"data\": $(cat przyklady/01-kosci-lacina-polski-angielski.json)}"
```

## Plik `05-surowa-odpowiedz-modelu.txt`

To nie jest poprawny JSON — celowo. Odwzorowuje surową odpowiedź modelu językowego
i sprawdza, czy silnik importu poradzi sobie z typowymi odstępstwami:

- zdanie wstępu i zakończenia poza obiektem JSON,
- otoczka ```` ```json ```` ,
- przecinki wiszące przed `]`,
- polskie nazwy pól (`tytul`, `fiszki`, `przod`, `tyl`, `pytanie`, `odpowiedzi`, `poprawna`),
- angielskie synonimy w jednej fiszce (`term`, `definition`),
- fiszka zapisana jako tablica `["Collum", "…"]`,
- fiszka zapisana jednym napisem z separatorem `—`,
- prefiksy `"A) "` w treści wariantów,
- wskazanie poprawnej odpowiedzi literą, indeksem **liczonym od 1** oraz listą liter,
- warianty podane jako obiekt `{"A": "…", "B": "…"}`.

Dodatkowo zawiera **cztery elementy niepoprawne**, które import musi pominąć,
raportując powód: fiszkę bez rewersu, fiszkę bez awersu i pytanie bez wariantów odpowiedzi.

Oczekiwany wynik walidacji: **6 fiszek, 3 pytania, 2 fiszki i 1 pytanie pominięte,
5 ostrzeżeń, 0 błędów krytycznych**.
