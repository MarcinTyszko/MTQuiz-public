# AI_SCHEMA.md — specyfikacja pakietu nauki dla MTQuiz

Dokument opisuje format wymiany danych `mtquiz/study-set` oraz zawiera gotowy
prompt systemowy do sesji z modelem językowym, w których przygotowujesz pakiety nauki
na podstawie własnych skryptów, notatek i materiałów PDF.

> **Szybsza droga:** zakładka **Prompt AI** w aplikacji (`/generator-promptu`) składa
> rozbudowane polecenie dopasowane do dziedziny, tematu, poziomu odbiorcy, liczby fiszek
> i układu językowego, wraz z instrukcją obsługi dla Claude CLI, ChatGPT, Gemini i modeli
> lokalnych. Format jest niezależny od dyscypliny — poniższe przykłady pochodzą z medycyny,
> ale te same pola opisują fiszki z prawa, programowania czy nauki języka.
> Ten plik przydaje się, gdy chcesz zrozumieć format do końca albo budować własne narzędzia.

Cały plik jest przeznaczony do przekazania modelowi. Typowe użycie:

```bash
claude -p "$(cat AI_SCHEMA.md)

Przetwórz materiał: ./materialy/neuroanatomia-wyklad-03.pdf" > pakiet.json
```

Następnie zaimportuj `pakiet.json` w aplikacji: **Import AI → Plik .json → Sprawdź pakiet**.

---

## 1. Model danych

Pakiet to pojedynczy obiekt JSON opisujący jeden **zestaw nauki** („teczkę”).
Zestaw zawiera dwa niezależne moduły: listę **fiszek** i listę **pytań quizowych**.
Co najmniej jeden z nich musi być niepusty.

### 1.1. Obiekt główny — `StudySet`

| Pole | Typ | Wymagane | Ograniczenia | Opis |
|---|---|---|---|---|
| `schema` | `string` | nie | `"mtquiz/study-set"` | Znacznik formatu; ignorowany przy imporcie, zalecany dla czytelności. |
| `version` | `integer` | nie | `1` | Wersja formatu. |
| `title` | `string` | **tak** | 1–200 znaków | Tytuł zestawu. Brak tytułu → import nada „Zaimportowany zestaw” i zgłosi ostrzeżenie. |
| `description` | `string` | nie | ≤ 5000 znaków | Zakres materiału, źródło, uwagi dla uczącego się. |
| `subject` | `string` | nie | ≤ 120 znaków | Przedmiot wiodący, np. `Anatomia`, `Farmakologia`. |
| `tags` | `string[]` | nie | ≤ 20 pozycji, każda ≤ 64 znaki | Tagi tematyczne. Duplikaty (bez względu na wielkość liter) są scalane. |
| `visibility` | `"private" \| "public"` | nie | domyślnie `"private"` | Widoczność po imporcie. |
| `cards` | `Flashcard[]` | warunkowo | ≤ 5000 pozycji | Fiszki. |
| `questions` | `Question[]` | warunkowo | ≤ 5000 pozycji | Pytania wielokrotnego wyboru. |

> **Reguła:** `cards` i `questions` nie mogą być jednocześnie puste.

### 1.2. `Flashcard`

| Pole | Typ | Wymagane | Ograniczenia | Opis |
|---|---|---|---|---|
| `front` | `string` | **tak** | 1–8000 znaków | Awers: pojęcie, pytanie lub polecenie. |
| `back` | `string` | **tak** | 1–20000 znaków | Rewers: pełna odpowiedź wraz z kontekstem klinicznym. |
| `hint` | `string` | nie | ≤ 4000 znaków | Wskazówka odsłaniana na życzenie podczas nauki. |
| `note` | `string` | nie | ≤ 8000 znaków | Notatka dodatkowa: pułapka egzaminacyjna, mnemotechnika, odsyłacz do materiału. |

Fiszka bez `front` lub bez `back` jest **pomijana** — import przechodzi dalej i zgłasza ostrzeżenie.

### 1.3. `Question`

| Pole | Typ | Wymagane | Ograniczenia | Opis |
|---|---|---|---|---|
| `prompt` | `string` | **tak** | 1–8000 znaków | Treść pytania (trzon zadania). |
| `explanation` | `string` | nie | ≤ 20000 znaków | Uzasadnienie poprawnej odpowiedzi, pokazywane po jej udzieleniu. |
| `options` | `AnswerOption[]` | **tak** | 2–10 pozycji | Warianty odpowiedzi. |

Pole `multiple` (wybór wielokrotny) **nie jest podawane ręcznie** — aplikacja wylicza je
automatycznie: pytanie jest wielokrotnego wyboru, gdy więcej niż jeden wariant ma
`is_correct: true`.

### 1.4. `AnswerOption`

| Pole | Typ | Wymagane | Ograniczenia | Opis |
|---|---|---|---|---|
| `text` | `string` | **tak** | 1–4000 znaków | Treść wariantu, **bez** prefiksu „A) ”. |
| `is_correct` | `boolean` | **tak** | — | Czy wariant jest poprawny. |
| `feedback` | `string` | nie | ≤ 4000 znaków | Komentarz do tego konkretnego wariantu — dlaczego jest poprawny lub na czym polega pułapka. |

Pytanie, w którym żaden wariant nie ma `is_correct: true`, jest **pomijane** wraz z ostrzeżeniem.

---

## 2. Schemat formalny (JSON Schema, draft 2020-12)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://mtquiz.local/schemas/study-set.json",
  "title": "mtquiz/study-set",
  "type": "object",
  "required": ["title"],
  "properties": {
    "schema":      { "const": "mtquiz/study-set" },
    "version":     { "type": "integer", "minimum": 1 },
    "title":       { "type": "string", "minLength": 1, "maxLength": 200 },
    "description": { "type": "string", "maxLength": 5000 },
    "subject":     { "type": "string", "maxLength": 120 },
    "visibility":  { "enum": ["private", "public"] },
    "tags": {
      "type": "array",
      "maxItems": 20,
      "items": { "type": "string", "minLength": 1, "maxLength": 64 }
    },
    "cards": {
      "type": "array",
      "maxItems": 5000,
      "items": {
        "type": "object",
        "required": ["front", "back"],
        "properties": {
          "front": { "type": "string", "minLength": 1, "maxLength": 8000 },
          "back":  { "type": "string", "minLength": 1, "maxLength": 20000 },
          "hint":  { "type": "string", "maxLength": 4000 },
          "note":  { "type": "string", "maxLength": 8000 }
        },
        "additionalProperties": false
      }
    },
    "questions": {
      "type": "array",
      "maxItems": 5000,
      "items": {
        "type": "object",
        "required": ["prompt", "options"],
        "properties": {
          "prompt":      { "type": "string", "minLength": 1, "maxLength": 8000 },
          "explanation": { "type": "string", "maxLength": 20000 },
          "options": {
            "type": "array",
            "minItems": 2,
            "maxItems": 10,
            "items": {
              "type": "object",
              "required": ["text", "is_correct"],
              "properties": {
                "text":       { "type": "string", "minLength": 1, "maxLength": 4000 },
                "is_correct": { "type": "boolean" },
                "feedback":   { "type": "string", "maxLength": 4000 }
              },
              "additionalProperties": false
            }
          }
        },
        "additionalProperties": false
      }
    }
  },
  "anyOf": [
    { "required": ["cards"],     "properties": { "cards":     { "minItems": 1 } } },
    { "required": ["questions"], "properties": { "questions": { "minItems": 1 } } }
  ]
}
```

---

## 3. Prompt systemowy (uniwersalny)

Poniższy blok działa w dowolnym modelu językowym — Claude, ChatGPT, Gemini, a także
w modelach uruchamianych lokalnie. Nie zawiera niczego specyficznego dla jednego dostawcy.
W aplikacji rozbudowaną, parametryzowaną wersję wygenerujesz w zakładce **Prompt AI**.

```text
Jesteś asystentem przygotowującym materiały do nauki dla studenta kierunku medycznego.
Na podstawie dostarczonych materiałów źródłowych (PDF, skrypt, notatki z wykładu)
utwórz pakiet nauki w formacie JSON zgodnym ze schematem "mtquiz/study-set".

=== ZASADY BEZWZGLĘDNE (ochrona przed konfabulacją) ===
1. Korzystaj WYŁĄCZNIE z treści obecnych w materiale źródłowym. Nie uzupełniaj luk
   wiedzą własną, nawet jeśli jesteś jej pewien.
2. Jeżeli materiał nie pozwala sformułować jednoznacznej odpowiedzi, pomiń
   zagadnienie. Lepszy jest krótszy pakiet niż pakiet z błędem merytorycznym.
3. Nie wymyślaj: dawek leków, wartości referencyjnych badań, odsetków, nazw
   handlowych, nazwisk, dat, numerów wytycznych ani odsyłaczy do piśmiennictwa.
   Przenoś je wyłącznie dosłownie z materiału.
4. Nie łącz faktów z różnych fragmentów w nowy wniosek, którego materiał nie
   formułuje wprost.
5. Zachowaj terminologię i nazewnictwo (polskie oraz łacińskie) dokładnie takie,
   jakie występuje w materiale źródłowym.
6. Odpowiedz WYŁĄCZNIE obiektem JSON. Bez zdania wstępu, bez podsumowania,
   bez bloków ```json, bez komentarzy w treści.

=== JAK BUDOWAĆ FISZKI ===
- Jedna fiszka = jedno zagadnienie. Nie łącz dwóch pojęć w jednej karcie.
- "front": zwięzłe i jednoznaczne (do ~15 słów). Unikaj pytań typu
  „Co wiesz o…?”. Pytaj o konkret: mechanizm, kryterium, wartość, różnicę.
- "back": pełna, samodzielna odpowiedź w 1–3 zdaniach. Musi dać się zrozumieć
  bez zaglądania do awersu.
- Priorytet materiału wysokowydajnego: mechanizmy działania, kryteria
  rozpoznania, objawy patognomoniczne, cechy różnicujące, wyjątki od reguły,
  klasyfikacje, powikłania.
- Pomijaj treści organizacyjne (plan wykładu, literatura, podziękowania).
- "hint": krótka podpowiedź naprowadzająca (kategoria, pierwsza litera,
  mnemotechnika) — nigdy nie zawiera pełnej odpowiedzi.
- "note": pułapka egzaminacyjna, kontekst kliniczny lub powiązanie z inną partią
  materiału.

=== JAK BUDOWAĆ PYTANIA QUIZOWE ===
- Styl egzaminu państwowego (LEK / LDEK): krótka winieta kliniczna albo precyzyjne
  pytanie o fakt, zawsze dokładnie jeden problem do rozstrzygnięcia.
- Dokładnie 4 warianty odpowiedzi, chyba że materiał wymusza inną liczbę.
- Dokładnie jedna odpowiedź poprawna. Jeżeli pytanie z natury wymaga kilku,
  napisz to w treści ("Zaznacz wszystkie prawidłowe") i ustaw is_correct: true
  dla każdego poprawnego wariantu.
- Dystraktory muszą być prawdopodobne i pochodzić z tej samej kategorii
  pojęciowej co odpowiedź poprawna (np. same nerwy, same leki, same enzymy).
  Nie twórz wariantów oczywiście absurdalnych.
- Warianty podobnej długości i konstrukcji gramatycznej. Nie stosuj
  „wszystkie powyższe” ani „żadne z powyższych”.
- "explanation": wyjaśnia, dlaczego poprawna odpowiedź jest poprawna — odwołuje
  się do mechanizmu, nie tylko powtarza treść wariantu.
- "feedback" przy wariancie błędnym: wskazuje, na czym polega pomyłka.
- Nie umieszczaj liter "A)", "B)" w polu "text" — numeracja powstaje automatycznie.

=== PROPORCJE I OBJĘTOŚĆ ===
- Domyślnie: 15–40 fiszek i 8–15 pytań na typowy wykład (20–40 slajdów).
- Przy obszerniejszym materiale rozbij go na kilka pakietów tematycznych,
  każdy z własnym tytułem — nie twórz jednego zestawu na 300 fiszek.
- "tags": 2–5 tagów opisujących temat (np. "Neuroanatomia", "Nerwy czaszkowe").
- "subject": jeden przedmiot wiodący.
- "visibility": zawsze "private", chyba że polecenie mówi inaczej.

=== FORMAT WYJŚCIOWY ===
{
  "schema": "mtquiz/study-set",
  "version": 1,
  "title": string,
  "description": string,
  "subject": string,
  "tags": string[],
  "visibility": "private",
  "cards": [
    { "front": string, "back": string, "hint": string?, "note": string? }
  ],
  "questions": [
    {
      "prompt": string,
      "explanation": string,
      "options": [
        { "text": string, "is_correct": boolean, "feedback": string? }
      ]
    }
  ]
}

=== KONTROLA PRZED ODDANIEM ODPOWIEDZI ===
Zanim odpowiesz, sprawdź po kolei:
[ ] JSON jest składniowo poprawny i nie zawiera przecinków wiszących.
[ ] Każda fiszka ma niepuste "front" i "back".
[ ] Każde pytanie ma co najmniej 2 warianty i co najmniej jeden is_correct: true.
[ ] Żaden fakt nie pochodzi spoza materiału źródłowego.
[ ] Odpowiedź zaczyna się znakiem "{" i kończy znakiem "}".
```

---

## 4. Warianty tolerowane przez parser

Parser aplikacji jest celowo odporny na odstępstwa, które modele językowe popełniają
najczęściej. Poniższe zapisy zostaną poprawnie zinterpretowane (z ostrzeżeniem),
ale **format kanoniczny z sekcji 1 jest zawsze preferowany**.

| Odstępstwo | Zachowanie parsera |
|---|---|
| Odpowiedź otoczona blokiem ` ```json … ``` ` | Otoczka jest usuwana. |
| Tekst komentarza przed lub po obiekcie JSON | Wyłuskiwany jest pierwszy kompletny obiekt/tablica. |
| Przecinek wiszący przed `}` lub `]` | Usuwany automatycznie. |
| Polskie nazwy pól: `tytul`, `opis`, `przedmiot`, `tagi`, `fiszki`, `pytania`, `przod`, `tyl`, `pytanie`, `odpowiedzi`, `poprawna`, `wyjasnienie` | Mapowane na pola kanoniczne. |
| Angielskie synonimy: `name`, `term`, `definition`, `answers`, `choices`, `correct_answer`, `rationale` | Mapowane na pola kanoniczne. |
| `options` jako lista napisów + osobne pole `correct` | Wskazanie nanoszone na odpowiedni wariant. |
| `correct` jako litera (`"B"`, `"b"`, `"B)"`) | Zamieniane na indeks wariantu. |
| `correct` jako liczba | Traktowane jako indeks liczony od 0; wartość poza zakresem jest interpretowana jako numeracja od 1 (z ostrzeżeniem). |
| `correct` jako dosłowna treść odpowiedzi | Dopasowywane po treści wariantu. |
| `correct` jako lista wskazań | Pytanie staje się wielokrotnego wyboru. |
| `options` jako obiekt `{"A": "…", "B": "…"}` | Zamieniane na listę w kolejności liter. |
| Prefiks `"A) "` w treści wariantu | Usuwany. |
| Koperta `{"set": {…}}`, `{"data": {…}}`, `{"zestaw": {…}}` | Rozpakowywana. |
| Tablica na najwyższym poziomie | Traktowana jako lista fiszek (elementy z polem `options` trafiają do pytań). |
| Fiszka jako napis `"Pojęcie — definicja"` | Dzielona na awers i rewers. |

**Błędy krytyczne** (import zostaje zatrzymany, dane nie są zapisywane):
niepoprawna składnia JSON, kodowanie inne niż UTF-8, brak jakiejkolwiek poprawnej
fiszki i jakiegokolwiek poprawnego pytania.

---

## 5. Przykład poprawnego pakietu

Skrócona wersja zestawu pokazowego dołączonego do aplikacji
(pełny plik: `app/data/przyklad_nerwy_czaszkowe.json`).

```json
{
  "schema": "mtquiz/study-set",
  "version": 1,
  "title": "Neuroanatomia — nerwy czaszkowe I–XII",
  "description": "Przebieg, otwory podstawy czaszki, funkcje oraz objawy uszkodzenia dwunastu nerwów czaszkowych.",
  "subject": "Anatomia",
  "tags": ["Neuroanatomia", "Nerwy czaszkowe", "Anatomia głowy"],
  "visibility": "private",
  "cards": [
    {
      "front": "Nerw czaszkowy IV — unerwiany mięsień i cecha wyjątkowa",
      "back": "Nerw bloczkowy (n. trochlearis). Unerwia wyłącznie mięsień skośny górny. Jako jedyny nerw czaszkowy opuszcza pień mózgu po stronie grzbietowej i krzyżuje się przed wyjściem, więc unerwia mięsień po stronie przeciwnej.",
      "hint": "Najdłuższy śródczaszkowy przebieg i najcieńszy nerw czaszkowy.",
      "note": "Uszkodzenie utrudnia schodzenie po schodach — dwojenie nasila się przy patrzeniu w dół i przyśrodkowo."
    },
    {
      "front": "Nerw czaszkowy VII — funkcje i otwór wyjścia z czaszki",
      "back": "Nerw twarzowy (n. facialis). Ruchowo unerwia mięśnie mimiczne i mięsień strzemiączkowy, czuciowo smak z 2/3 przednich języka, przywspółczulnie gruczoł łzowy oraz ślinianki podżuchwową i podjęzykową. Wchodzi przewodem słuchowym wewnętrznym, opuszcza czaszkę otworem rylcowo-sutkowym.",
      "hint": "Zwoje: skrzydłowo-podniebienny i podżuchwowy."
    },
    {
      "front": "Które nerwy czaszkowe niosą włókna przywspółczulne?",
      "back": "Nerwy III, VII, IX i X. Zwoje przełączeniowe: rzęskowy (III), skrzydłowo-podniebienny i podżuchwowy (VII), uszny (IX) oraz zwoje śródścienne narządów (X).",
      "note": "Wszystkie zwoje przywspółczulne głowy korzystają z gałęzi nerwu trójdzielnego jako drogi dojścia do narządów docelowych."
    }
  ],
  "questions": [
    {
      "prompt": "Pacjent zgłasza dwojenie nasilające się podczas schodzenia po schodach i odruchowo przechyla głowę w stronę przeciwną do uszkodzenia. Który nerw czaszkowy jest uszkodzony?",
      "explanation": "Mięsień skośny górny, unerwiony przez nerw bloczkowy, obniża gałkę oczną w przywiedzeniu i dokonuje intorsji. Kompensacyjny przechył głowy w stronę przeciwną (dodatni test Bielschowskiego) jest klasycznym objawem.",
      "options": [
        { "text": "Nerw okoruchowy (III)", "is_correct": false, "feedback": "Porażenie III daje opadnięcie powieki i ustawienie gałki w dół i na zewnątrz." },
        { "text": "Nerw bloczkowy (IV)", "is_correct": true, "feedback": "Mięsień skośny górny obniża gałkę w addukcji oraz dokonuje intorsji." },
        { "text": "Nerw odwodzący (VI)", "is_correct": false, "feedback": "Uszkodzenie VI powoduje dwojenie poziome i zeza zbieżnego." },
        { "text": "Nerw wzrokowy (II)", "is_correct": false, "feedback": "Nerw II nie unerwia mięśni gałkoruchowych." }
      ]
    },
    {
      "prompt": "Które nerwy czaszkowe opuszczają jamę czaszki przez otwór szyjny?",
      "explanation": "Zespół otworu szyjnego (zespół Verneta) obejmuje porażenie nerwów IX, X i XI: zaburzenia połykania, chrypkę oraz osłabienie unoszenia barku.",
      "options": [
        { "text": "IX, X, XI", "is_correct": true, "feedback": "Razem z opuszką żyły szyjnej wewnętrznej i zatoką skalistą dolną." },
        { "text": "VII i VIII", "is_correct": false, "feedback": "Te nerwy wchodzą do przewodu słuchowego wewnętrznego." },
        { "text": "III, IV, VI", "is_correct": false, "feedback": "Przechodzą przez szczelinę oczodołową górną." },
        { "text": "X, XI, XII", "is_correct": false, "feedback": "Nerw XII opuszcza czaszkę własnym kanałem nerwu podjęzykowego." }
      ]
    }
  ]
}
```

---

## 6. Gotowe polecenia dla Claude CLI

Poniższe przykłady dotyczą Claude CLI. Odpowiedniki dla pozostałych modeli
(ChatGPT, Gemini, modele lokalne) znajdziesz w zakładce **Prompt AI** w aplikacji.

**Jeden plik PDF → jeden pakiet**

```bash
claude -p "$(cat AI_SCHEMA.md)

Przetwórz plik ./materialy/farmakologia-05.pdf. Zwróć wyłącznie JSON." \
  > pakiety/farmakologia-05.json
```

**Podział obszernego skryptu na pakiety tematyczne**

```bash
claude -p "$(cat AI_SCHEMA.md)

Przeanalizuj ./materialy/patofizjologia-skrypt.pdf i wypisz listę rozdziałów
wraz z zakresem stron. Nie generuj jeszcze JSON-a."

# następnie, dla każdego rozdziału:
claude -p "$(cat AI_SCHEMA.md)

Przetwórz wyłącznie rozdział 'Wstrząs' (strony 44-61) z pliku
./materialy/patofizjologia-skrypt.pdf. Zwróć wyłącznie JSON." \
  > pakiety/patofizjologia-wstrzas.json
```

**Uzupełnienie istniejącego zestawu o pytania quizowe**

Wyeksportuj zestaw z aplikacji (przycisk *Eksport JSON* na stronie zestawu), a następnie:

```bash
claude -p "$(cat AI_SCHEMA.md)

W pliku ./zestaw-7.json znajduje się istniejący zestaw. Zachowaj wszystkie
fiszki bez zmian i dopisz 10 pytań quizowych opartych wyłącznie na treści
tych fiszek. Zwróć kompletny obiekt JSON." \
  > zestaw-7-rozszerzony.json
```

Zaimportowany ponownie plik utworzy **nowy** zestaw — aplikacja nie nadpisuje
istniejących danych podczas importu.

---

## 7. Weryfikacja pakietu przed importem

Szybkie sprawdzenie składni bez uruchamiania aplikacji:

```bash
python3 -m json.tool pakiet.json > /dev/null && echo "JSON poprawny"
```

Pełna walidacja merytoryczna (liczniki, pominięte elementy, ostrzeżenia) odbywa się
w aplikacji: **Import AI → Sprawdź pakiet**. Ekran wyniku pokazuje liczbę rozpoznanych
fiszek i pytań, listę elementów pominiętych wraz z powodem oraz podgląd treści.
Przycisk **„Otwórz w edytorze i popraw”** przenosi pakiet do pełnego edytora, gdzie
możesz poprawić literówki, dodać lub usunąć elementy przed zapisem.
