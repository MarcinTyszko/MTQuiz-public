/**
 * Generator promptu dla modeli językowych.
 *
 * Składa gotowe do wklejenia polecenie, które opisuje modelowi strukturę pliku
 * JSON przyjmowanego przez import oraz narzuca rygor merytoryczny. Prompt jest
 * neutralny wobec dostawcy — działa tak samo w Claude CLI, ChatGPT i Gemini.
 */
(function () {
  "use strict";
  const { copyToClipboard, downloadText, toast } = window.MTQuiz;

  const POZIOMY = {
    przedkliniczny: {
      etykieta: "Lata przedkliniczne (anatomia, fizjologia, biochemia)",
      opis:
        "student pierwszych lat studiów medycznych; nacisk na definicje, klasyfikacje, " +
        "budowę i mechanizmy podstawowe, bez rozbudowanego kontekstu klinicznego",
    },
    kliniczny: {
      etykieta: "Lata kliniczne (interna, chirurgia, pediatria)",
      opis:
        "student lat klinicznych; nacisk na rozpoznanie różnicowe, kryteria diagnostyczne, " +
        "postępowanie pierwszego rzutu i typowe powikłania",
    },
    lek: {
      etykieta: "Przygotowanie do LEK / LDEK",
      opis:
        "kandydat do egzaminu państwowego; materiał wysokowydajny, pytania w stylu " +
        "egzaminacyjnym z winietą kliniczną i czterema wariantami odpowiedzi",
    },
    specjalizacja: {
      etykieta: "Specjalizacja i egzaminy podyplomowe",
      opis:
        "lekarz w trakcie specjalizacji; nacisk na aktualne wytyczne, wartości odcięcia, " +
        "schematy leczenia i wyjątki od reguły",
    },
    jezykowy: {
      etykieta: "Nauka terminologii i słownictwa",
      opis:
        "nauka nazewnictwa i słownictwa fachowego; awers zawiera termin, rewers jego " +
        "odpowiedniki i zwięzłe objaśnienie",
    },
  };

  const JEZYKI = {
    pl: {
      etykieta: "Tylko polski",
      instrukcja:
        'Treść fiszek i pytań w całości po polsku. Terminy łacińskie podawaj w nawiasie ' +
        "tylko wtedy, gdy występują w materiale źródłowym.",
    },
    pl_lat: {
      etykieta: "Polski + łacina",
      instrukcja:
        'Awers fiszki zawiera termin łaciński zgodny z Terminologia Anatomica, rewers ' +
        'zaczyna się wierszem "polski: <nazwa polska>". Nazewnictwo łacińskie musi być ' +
        "poprawne gramatycznie (mianownik liczby pojedynczej, chyba że termin występuje tylko w liczbie mnogiej).",
    },
    pl_lat_en: {
      etykieta: "Polski + łacina + angielski",
      instrukcja:
        'Awers fiszki zawiera termin łaciński zgodny z Terminologia Anatomica. Rewers ma ' +
        'dokładnie dwa wiersze:\n    polski: <nazwa polska>\n    angielski: <nazwa angielska>\n' +
        "Nazwa angielska musi być terminem używanym w piśmiennictwie medycznym, nie tłumaczeniem dosłownym.",
    },
    pl_en: {
      etykieta: "Polski + angielski",
      instrukcja:
        'Rewers każdej fiszki zawiera odpowiednik angielski w osobnym wierszu ' +
        'w postaci "angielski: <termin>". Pozostała treść po polsku.',
    },
  };

  const SZABLONY = {
    anatomia: {
      etykieta: "Anatomia — nazewnictwo trójjęzyczne",
      temat: "Nazewnictwo anatomiczne: kości kończyny górnej wraz z punktami orientacyjnymi",
      poziom: "jezykowy",
      jezyki: "pl_lat_en",
      fiszki: 30,
      pytania: 8,
    },
    farmakologia: {
      etykieta: "Farmakologia — grupa leków",
      temat: "Leki hipotensyjne: inhibitory konwertazy angiotensyny, sartany, beta-blokery i diuretyki tiazydowe",
      poziom: "kliniczny",
      jezyki: "pl",
      fiszki: 35,
      pytania: 12,
    },
    interna: {
      etykieta: "Interna — jednostka chorobowa",
      temat: "Ostre zespoły wieńcowe: rozpoznanie, diagnostyka różnicowa i postępowanie wstępne",
      poziom: "lek",
      jezyki: "pl",
      fiszki: 30,
      pytania: 15,
    },
    fizjologia: {
      etykieta: "Fizjologia — układ",
      temat: "Fizjologia nerek: filtracja kłębuszkowa, transport kanalikowy i regulacja hormonalna",
      poziom: "przedkliniczny",
      jezyki: "pl",
      fiszki: 40,
      pytania: 10,
    },
  };

  const ZRODLA_PODRECZNIKOWE = [
    "Bochenek A., Reicher M. — Anatomia człowieka (anatomia prawidłowa)",
    "Terminologia Anatomica / Federative International Programme on Anatomical Terminology (nazewnictwo)",
    "Konturek S. — Fizjologia człowieka; Guyton & Hall — Textbook of Medical Physiology",
    "Kostowski W., Herman Z. — Farmakologia. Podstawy farmakoterapii",
    "Szczeklik A. (red.) — Interna Szczeklika, wydanie aktualne",
    "Kumar V., Abbas A., Aster J. — Robbins & Cotran Pathologic Basis of Disease",
    "Aktualne wytyczne towarzystw naukowych (ESC, PTK, PTD, WHO) — wyłącznie gdy znasz numer i rok wydania",
  ];

  function promptGenerator() {
    return {
      // Konfiguracja
      temat: "",
      zrodlo: "wlasne",
      poziom: "lek",
      jezyki: "pl",
      fiszki: 30,
      pytania: 12,
      wymagajZrodel: true,
      wielokrotnyWybor: true,
      dodatkowe: "",
      // Interfejs
      zakladka: "claude",
      podglad: true,

      get poziomy() {
        return Object.entries(POZIOMY).map(([klucz, wartosc]) => ({ klucz, ...wartosc }));
      },
      get jezykiOpcje() {
        return Object.entries(JEZYKI).map(([klucz, wartosc]) => ({ klucz, ...wartosc }));
      },
      get szablony() {
        return Object.entries(SZABLONY).map(([klucz, wartosc]) => ({ klucz, ...wartosc }));
      },

      zastosujSzablon(klucz) {
        const szablon = SZABLONY[klucz];
        if (!szablon) return;
        this.temat = szablon.temat;
        this.poziom = szablon.poziom;
        this.jezyki = szablon.jezyki;
        this.fiszki = szablon.fiszki;
        this.pytania = szablon.pytania;
        this.zrodlo = "wiedza";
        toast(`Wczytano szablon: ${szablon.etykieta}`, "success", 2200);
      },

      get tematDoPromptu() {
        return this.temat.trim() || "<WPISZ TUTAJ TEMAT LUB ZAKRES MATERIAŁU>";
      },

      get liczbaFiszek() {
        return Math.max(1, Math.min(300, Number(this.fiszki) || 1));
      },

      get liczbaPytan() {
        return Math.max(0, Math.min(150, Number(this.pytania) || 0));
      },

      /** Sekcja opisująca dopuszczalne źródła wiedzy. */
      get sekcjaZrodel() {
        if (this.zrodlo === "wlasne") {
          return [
            "## ŹRÓDŁO WIEDZY — materiały dołączone przez użytkownika",
            "",
            "Opieraj się WYŁĄCZNIE na treści dołączonych materiałów (PDF, skan, notatki, wykład).",
            "Nie uzupełniaj luk wiedzą własną, nawet jeśli jesteś jej pewien — ten materiał służy",
            "do nauki przed konkretnym zaliczeniem i musi odpowiadać temu, czego wymaga prowadzący.",
            "",
            "Jeżeli w materiale czegoś brakuje albo fragment jest nieczytelny, pomiń to zagadnienie.",
            "Nie dopisuj komentarza o pominięciu — po prostu nie twórz takiej fiszki.",
          ].join("\n");
        }

        return [
          "## ŹRÓDŁO WIEDZY — ugruntowana wiedza podręcznikowa",
          "",
          "Opieraj się wyłącznie na treściach zgodnych ze standardowymi podręcznikami akademickimi",
          "i aktualnymi wytycznymi. Punkt odniesienia:",
          "",
          ...ZRODLA_PODRECZNIKOWE.map((pozycja) => `- ${pozycja}`),
          "",
          "Zasada nadrzędna: umieszczaj wyłącznie informacje, co do których masz wysoką pewność,",
          "że są zgodne z powyższymi źródłami i powszechnie uznane. Treści sporne, niszowe,",
          "szybko zmieniające się lub zależne od lokalnych protokołów — pomiń.",
          "",
          "Jeżeli źródła podają rozbieżne wartości (na przykład zakresy referencyjne), napisz o tym",
          'wprost w polu "note" albo pomiń zagadnienie. Nigdy nie wybieraj jednej wartości w milczeniu.',
        ].join("\n");
      },

      get sekcjaRygoru() {
        const zasady = [
          [
            "Nie wymyślaj.",
            "Nie podawaj liczb, dawek, wartości referencyjnych, odsetków, nazw handlowych,",
            "nazwisk, dat ani numerów wytycznych, jeżeli nie masz co do nich pewności.",
            "Brak informacji jest lepszy niż informacja nieprawdziwa.",
          ],
          [
            "Nie łącz faktów w nowe wnioski.",
            "Nie twórz zależności, których źródło nie formułuje wprost.",
          ],
          [
            "Nie twórz przypisów ani bibliografii.",
            "Nie podawaj odnośników do stron, numerów tabel ani adresów internetowych —",
            "nie da się ich zweryfikować w pliku importu.",
          ],
          [
            "Jedna fiszka to jeden fakt.",
            "Nie upychaj kilku zagadnień w jednej karcie.",
          ],
          [
            "Precyzja przed obszernością.",
            "Lepiej oddać dwadzieścia bezbłędnych fiszek niż pięćdziesiąt z trzema błędami.",
          ],
          [
            "Pomijaj treści organizacyjne.",
            "Plan wykładu, spis literatury, podziękowania i dane kontaktowe nie są materiałem do nauki.",
          ],
        ];

        if (this.wymagajZrodel) {
          zasady.push([
            "Oznacz umocowanie każdej fiszki.",
            'W polu "note" dopisz krótko, skąd pochodzi treść — na przykład „wykład 3, slajd 12”',
            "dla materiałów własnych albo „wiedza podręcznikowa: anatomia prawidłowa”.",
          ]);
        }

        const wiersze = [];
        zasady.forEach((zasada, index) => {
          const [naglowek, ...opis] = zasada;
          wiersze.push(`${index + 1}. **${naglowek}**`);
          opis.forEach((linia) => wiersze.push(`   ${linia}`));
        });

        return [
          "## RYGOR MERYTORYCZNY — bezwzględny",
          "",
          "Na podstawie tego materiału ktoś będzie się uczył do egzaminu, a później leczył pacjentów.",
          "Błąd merytoryczny jest gorszy niż brak materiału.",
          "",
          ...wiersze,
        ].join("\n");
      },

      get sekcjaTresci() {
        const poziom = POZIOMY[this.poziom];
        const jezyk = JEZYKI[this.jezyki];
        const wiersze = [
          "## JAK BUDOWAĆ TREŚĆ",
          "",
          `Odbiorca: ${poziom.opis}.`,
          "",
          "### Fiszki",
          '- "front": zwięzłe i jednoznaczne, do około 15 słów. Pytaj o konkret — mechanizm,',
          "  kryterium, różnicę, wyjątek. Unikaj sformułowań typu „Co wiesz o…?”.",
          '- "back": pełna, samodzielna odpowiedź w 1–3 zdaniach, zrozumiała bez zaglądania na awers.',
          '- "hint": krótka podpowiedź naprowadzająca (kategoria, mnemotechnika). NIGDY nie zawiera',
          "  pełnej odpowiedzi — inaczej wskazówka psuje naukę.",
          '- "note": kontekst kliniczny, pułapka egzaminacyjna albo powiązanie z inną partią materiału.',
          "- Priorytet materiału wysokowydajnego: mechanizmy, kryteria rozpoznania, objawy",
          "  patognomoniczne, cechy różnicujące, klasyfikacje, powikłania, wyjątki od reguły.",
          "",
          "### Pytania quizowe",
          '- "prompt": krótka winieta kliniczna albo precyzyjne pytanie o fakt. Dokładnie jeden problem.',
          "- Dokładnie 4 warianty odpowiedzi.",
          this.wielokrotnyWybor
            ? "- Domyślnie jedna odpowiedź poprawna. Jeżeli zagadnienie wymaga kilku, napisz w treści\n  „Zaznacz wszystkie prawidłowe” i ustaw is_correct: true przy każdym poprawnym wariancie."
            : "- Zawsze dokładnie jedna odpowiedź poprawna. Nie twórz pytań wielokrotnego wyboru.",
          "- Dystraktory muszą być prawdopodobne i pochodzić z tej samej kategorii pojęciowej",
          "  co odpowiedź poprawna (same leki, same nerwy, same enzymy). Żadnych wariantów absurdalnych.",
          "- Warianty podobnej długości i konstrukcji. Nie stosuj „wszystkie powyższe”",
          "  ani „żadne z powyższych”.",
          '- "explanation": tłumaczy mechanizm stojący za poprawną odpowiedzią, nie powtarza jej treści.',
          '- "feedback" przy wariancie błędnym: wskazuje, na czym polega pomyłka.',
          '- Nie umieszczaj liter „A)”, „B)” w polu "text" — numeracja powstaje automatycznie.',
          "",
          "### Język",
          `- ${jezyk.instrukcja}`,
        ];
        if (this.dodatkowe.trim()) {
          wiersze.push("", "### Dodatkowe wymagania użytkownika", ...this.dodatkowe.trim().split("\n").map((l) => `- ${l.trim()}`));
        }
        return wiersze.join("\n");
      },

      get sekcjaSchematu() {
        return [
          "## STRUKTURA PLIKU JSON — opis pełny",
          "",
          "Zwracasz JEDEN obiekt JSON. Poniżej znaczenie każdego pola.",
          "",
          "### Obiekt główny (zestaw nauki)",
          "",
          "| pole | typ | wymagane | znaczenie |",
          "|---|---|---|---|",
          '| `title` | tekst, 1–200 znaków | tak | tytuł zestawu widoczny na liście |',
          '| `description` | tekst, do 5000 znaków | nie | czego dotyczy materiał i skąd pochodzi |',
          '| `subject` | tekst, do 120 znaków | nie | jeden przedmiot wiodący, np. "Farmakologia" |',
          '| `tags` | lista tekstów, do 20 pozycji | nie | 2–5 tagów tematycznych ułatwiających wyszukiwanie |',
          '| `visibility` | "private" albo "public" | nie | ustaw "private" |',
          '| `cards` | lista fiszek | tak* | patrz niżej |',
          '| `questions` | lista pytań | tak* | patrz niżej |',
          "",
          "\\* przynajmniej jedna z list musi być niepusta.",
          "",
          "### Element listy `cards` (fiszka)",
          "",
          "| pole | typ | wymagane | znaczenie |",
          "|---|---|---|---|",
          '| `front` | tekst, 1–8000 znaków | tak | awers: pojęcie lub pytanie |',
          '| `back` | tekst, 1–20000 znaków | tak | rewers: pełna odpowiedź |',
          '| `hint` | tekst, do 4000 znaków | nie | wskazówka odsłaniana na życzenie |',
          '| `note` | tekst, do 8000 znaków | nie | notatka dodatkowa, kontekst, pułapka |',
          "",
          "### Element listy `questions` (pytanie)",
          "",
          "| pole | typ | wymagane | znaczenie |",
          "|---|---|---|---|",
          '| `prompt` | tekst, 1–8000 znaków | tak | treść pytania |',
          '| `explanation` | tekst, do 20000 znaków | nie | uzasadnienie poprawnej odpowiedzi |',
          '| `options` | lista 2–10 wariantów | tak | warianty odpowiedzi |',
          "",
          "### Element listy `options` (wariant odpowiedzi)",
          "",
          "| pole | typ | wymagane | znaczenie |",
          "|---|---|---|---|",
          '| `text` | tekst, 1–4000 znaków | tak | treść wariantu, BEZ prefiksu "A) " |',
          '| `is_correct` | prawda/fałsz | tak | czy wariant jest poprawny |',
          '| `feedback` | tekst, do 4000 znaków | nie | komentarz do tego konkretnego wariantu |',
          "",
          "### Reguły, których naruszenie powoduje odrzucenie elementu",
          "",
          "- fiszka bez `front` albo bez `back` zostaje pominięta przy imporcie,",
          "- pytanie musi mieć co najmniej 2 warianty i co najmniej jeden z `is_correct: true`,",
          "- pola `multiple` NIE podajesz — aplikacja wylicza je sama na podstawie liczby",
          "  wariantów oznaczonych jako poprawne,",
          "- nie dodawaj pól spoza powyższych tabel.",
        ].join("\n");
      },

      get sekcjaPrzykladu() {
        return [
          "## PRZYKŁAD POPRAWNEJ ODPOWIEDZI (skrócony)",
          "",
          "```json",
          "{",
          '  "title": "Neuroanatomia — nerwy czaszkowe",',
          '  "description": "Przebieg, funkcje i objawy uszkodzenia nerwów czaszkowych.",',
          '  "subject": "Anatomia",',
          '  "tags": ["Neuroanatomia", "Nerwy czaszkowe"],',
          '  "visibility": "private",',
          '  "cards": [',
          "    {",
          '      "front": "Nerw czaszkowy IV — unerwiany mięsień i cecha wyjątkowa",',
          '      "back": "Nerw bloczkowy. Unerwia wyłącznie mięsień skośny górny. Jako jedyny nerw czaszkowy opuszcza pień mózgu po stronie grzbietowej.",',
          '      "hint": "Najcieńszy nerw czaszkowy.",',
          '      "note": "Uszkodzenie utrudnia schodzenie po schodach."',
          "    }",
          "  ],",
          '  "questions": [',
          "    {",
          '      "prompt": "Pacjent zgłasza dwojenie przy patrzeniu w dół i przechyla głowę w stronę przeciwną do uszkodzenia. Który nerw jest uszkodzony?",',
          '      "explanation": "Mięsień skośny górny obniża gałkę oczną w przywiedzeniu i dokonuje intorsji, stąd kompensacyjny przechył głowy.",',
          '      "options": [',
          '        { "text": "Nerw okoruchowy (III)", "is_correct": false, "feedback": "Daje opadnięcie powieki i ustawienie gałki w dół i na zewnątrz." },',
          '        { "text": "Nerw bloczkowy (IV)", "is_correct": true, "feedback": "Unerwia mięsień skośny górny." },',
          '        { "text": "Nerw odwodzący (VI)", "is_correct": false, "feedback": "Powoduje dwojenie poziome i zeza zbieżnego." },',
          '        { "text": "Nerw wzrokowy (II)", "is_correct": false, "feedback": "Nie unerwia mięśni gałkoruchowych." }',
          "      ]",
          "    }",
          "  ]",
          "}",
          "```",
        ].join("\n");
      },

      get sekcjaFormatu() {
        return [
          "## FORMAT ODPOWIEDZI",
          "",
          "- Odpowiedz WYŁĄCZNIE obiektem JSON. Bez zdania wstępu, bez podsumowania, bez komentarzy.",
          "- Pierwszy znak odpowiedzi to `{`, ostatni to `}`.",
          "- Kodowanie UTF-8, polskie znaki diakrytyczne zapisane wprost (nie `\\u0105`).",
          "- Nie stosuj przecinków wiszących przed `}` ani `]`.",
          "- Jeżeli materiał jest zbyt obszerny, żeby zmieścić go w jednej odpowiedzi, przygotuj",
          "  mniejszy, ale kompletny i poprawny składniowo pakiet, zamiast urywać JSON w połowie.",
          "",
          "## LISTA KONTROLNA — sprawdź przed wysłaniem odpowiedzi",
          "",
          "- [ ] JSON jest składniowo poprawny i domyka wszystkie nawiasy.",
          "- [ ] Każda fiszka ma niepuste `front` i `back`.",
          "- [ ] Każde pytanie ma 4 warianty i co najmniej jeden `is_correct: true`.",
          "- [ ] Żaden wariant odpowiedzi nie zaczyna się od „A) ”, „B) ” i podobnych.",
          "- [ ] Nie ma pola `multiple` ani żadnego pola spoza specyfikacji.",
          "- [ ] Każdy fakt jest zgodny ze wskazanym źródłem wiedzy; nic nie zostało zmyślone.",
          "- [ ] Odpowiedź nie zawiera nic poza obiektem JSON.",
        ].join("\n");
      },

      /** Składa kompletny prompt z wszystkich sekcji. */
      get promptTekst() {
        const poziom = POZIOMY[this.poziom];
        const naglowek = [
          "# ROLA",
          "",
          "Jesteś doświadczonym dydaktykiem nauk medycznych i redaktorem materiałów do nauki.",
          "Twoim zadaniem jest przygotowanie pakietu fiszek i pytań testowych w formacie JSON,",
          "który zostanie zaimportowany do aplikacji MTQuiz.",
          "",
          "# ZADANIE",
          "",
          `Temat / zakres materiału: ${this.tematDoPromptu}`,
          `Poziom odbiorcy: ${poziom.etykieta}`,
          `Liczba fiszek: ${this.liczbaFiszek}`,
          this.liczbaPytan > 0
            ? `Liczba pytań testowych: ${this.liczbaPytan}`
            : "Pytania testowe: nie twórz ich, przygotuj wyłącznie fiszki.",
        ].join("\n");

        return [
          naglowek,
          this.sekcjaZrodel,
          this.sekcjaRygoru,
          this.sekcjaTresci,
          this.sekcjaSchematu,
          this.sekcjaPrzykladu,
          this.sekcjaFormatu,
        ].join("\n\n---\n\n");
      },

      get dlugoscPromptu() {
        return this.promptTekst.length;
      },

      get przyblizoneTokeny() {
        // Przybliżenie: dla tekstu polskiego około 3 znaki na token.
        return Math.round(this.promptTekst.length / 3);
      },

      async kopiuj() {
        await copyToClipboard(this.promptTekst, {
          successMessage: "Prompt skopiowany do schowka — wklej go w oknie modelu.",
        });
      },

      pobierz() {
        const nazwa = (this.temat.trim() || "prompt-mtquiz")
          .toLowerCase()
          .normalize("NFD")
          .replace(/[̀-ͯ]/g, "")
          .replace(/ł/g, "l")
          .replace(/[^a-z0-9]+/g, "-")
          .replace(/^-+|-+$/g, "")
          .slice(0, 60);
        downloadText(`${nazwa || "prompt-mtquiz"}.txt`, this.promptTekst);
        toast("Plik z promptem został pobrany.", "success", 2400);
      },
    };
  }

  window.promptGenerator = promptGenerator;
})();
