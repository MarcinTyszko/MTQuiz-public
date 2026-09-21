/**
 * Generator promptu dla modeli językowych.
 *
 * Składa gotowe do wklejenia polecenie, które opisuje modelowi strukturę pliku
 * JSON przyjmowanego przez import oraz narzuca rygor merytoryczny. Prompt jest
 * neutralny wobec dziedziny i dostawcy modelu — działa tak samo dla anatomii,
 * prawa, programowania czy nauki języka, w Claude, ChatGPT i Gemini.
 */
(function () {
  "use strict";
  const { copyToClipboard, downloadText, toast } = window.MTQuiz;

  /* ------------------------------------------------------------------ */
  /* Przykłady pokazujące modelowi oczekiwany kształt pliku              */
  /* ------------------------------------------------------------------ */
  const PRZYKLADY = {
    ogolny: {
      podpis: "Przykład z dziedziny technicznej — pokazuje wyłącznie strukturę pliku, nie temat.",
      tresc: [
        "{",
        '  "title": "Protokół HTTP — kody odpowiedzi",',
        '  "description": "Znaczenie najczęstszych kodów statusu i ich wpływ na zachowanie klienta.",',
        '  "subject": "Sieci komputerowe",',
        '  "tags": ["HTTP", "Protokoły sieciowe"],',
        '  "visibility": "private",',
        '  "cards": [',
        "    {",
        '      "front": "Kod odpowiedzi HTTP 301 — znaczenie i skutek",',
        '      "back": "Moved Permanently: zasób został trwale przeniesiony pod adres wskazany w nagłówku Location. Klienty i wyszukiwarki zapamiętują przekierowanie i kolejne żądania kierują od razu pod nowy adres.",',
        '      "hint": "Grupa 3xx obejmuje przekierowania.",',
        '      "note": "Kod 302 oznacza przeniesienie tymczasowe i nie powinien być zapamiętywany."',
        "    }",
        "  ],",
        '  "questions": [',
        "    {",
        '      "prompt": "Serwer odpowiada kodem 301 i nagłówkiem Location wskazującym nowy adres. Jak powinien zachować się poprawnie napisany klient?",',
        '      "explanation": "Kod 301 oznacza przeniesienie trwałe, więc klient powinien zaktualizować zapamiętany adres zasobu, a nie tylko podążyć za przekierowaniem w bieżącym żądaniu.",',
        '      "options": [',
        '        { "text": "Zaktualizować zapamiętany adres zasobu i kierować tam kolejne żądania", "is_correct": true, "feedback": "Na tym polega różnica między przekierowaniem trwałym a tymczasowym." },',
        '        { "text": "Podążyć za przekierowaniem, ale zachować stary adres", "is_correct": false, "feedback": "Tak zachowuje się klient wobec kodu 302." },',
        '        { "text": "Zgłosić błąd i przerwać żądanie", "is_correct": false, "feedback": "Kody 3xx nie są błędami." },',
        '        { "text": "Ponowić żądanie pod tym samym adresem", "is_correct": false, "feedback": "Prowadziłoby to do pętli przekierowań." }',
        "      ]",
        "    }",
        "  ]",
        "}",
      ],
    },

    medycyna: {
      podpis: "Przykład z neuroanatomii.",
      tresc: [
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
      ],
    },

    jezyki: {
      podpis: "Przykład z nauki języka — zwróć uwagę na układ awersu i rewersu.",
      tresc: [
        "{",
        '  "title": "Hiszpański B1 — czasowniki nieregularne",',
        '  "description": "Formy podstawowe i typowe użycie czasowników nieregularnych na poziomie B1.",',
        '  "subject": "Język hiszpański",',
        '  "tags": ["Hiszpański", "Czasowniki", "Poziom B1"],',
        '  "visibility": "private",',
        '  "cards": [',
        "    {",
        '      "front": "tener",',
        '      "back": "mieć\\nwymowa: [teˈneɾ]\\nprzykład: Tengo dos hermanos. — Mam dwóch braci.",',
        '      "hint": "Czasownik nieregularny w pierwszej osobie liczby pojedynczej.",',
        '      "note": "W zwrocie „tener que + bezokolicznik” oznacza powinność: Tengo que estudiar."',
        "    }",
        "  ],",
        '  "questions": [',
        "    {",
        '      "prompt": "Które zdanie poprawnie wyraża powinność w języku hiszpańskim?",',
        '      "explanation": "Konstrukcja „tener que + bezokolicznik” wyraża konieczność. Po „hay que” również stoi bezokolicznik, ale zdanie jest wtedy bezosobowe.",',
        '      "options": [',
        '        { "text": "Tengo que estudiar más.", "is_correct": true, "feedback": "Poprawna konstrukcja osobowa wyrażająca powinność." },',
        '        { "text": "Tengo de estudiar más.", "is_correct": false, "feedback": "Przyimek „de” nie występuje w tej konstrukcji." },',
        '        { "text": "Tengo que estudio más.", "is_correct": false, "feedback": "Po „que” musi stać bezokolicznik, nie forma osobowa." },',
        '        { "text": "Tengo a estudiar más.", "is_correct": false, "feedback": "Przyimek „a” łączy się z innymi czasownikami, na przykład „ir a”." }',
        "      ]",
        "    }",
        "  ]",
        "}",
      ],
    },
  };

  /* ------------------------------------------------------------------ */
  /* Profile dziedzin — wpływają na źródła, rygor i przykład             */
  /* ------------------------------------------------------------------ */
  const PROFILE = {
    ogolny: {
      etykieta: "Uniwersalny",
      przyklad: "ogolny",
      zrodla: [
        "uznane podręczniki akademickie i opracowania przeglądowe z danej dziedziny",
        "oficjalne dokumenty, normy i specyfikacje wydane przez instytucje odpowiedzialne za temat",
        "recenzowane publikacje naukowe",
      ],
      rygor: [],
      wskazowki: [],
    },
    scisle: {
      etykieta: "Nauki ścisłe i przyrodnicze",
      przyklad: "ogolny",
      zrodla: [
        "podręczniki akademickie uznane w danej dyscyplinie",
        "oficjalne tablice wielkości fizycznych i chemicznych oraz układ SI",
        "recenzowane publikacje naukowe i opracowania przeglądowe",
      ],
      rygor: [
        [
          "Podawaj jednostki przy każdej wielkości.",
          "Wartość liczbowa bez jednostki jest bezużyteczna i myląca.",
        ],
        [
          "Nie zaokrąglaj stałych i wyników na własną rękę.",
          "Jeżeli nie znasz dokładnej wartości, opisz zależność jakościowo zamiast podawać liczbę.",
        ],
      ],
      wskazowki: [
        "Przy wzorach opisuj znaczenie każdego symbolu — fiszka musi być zrozumiała bez podręcznika.",
      ],
    },
    medycyna: {
      etykieta: "Medycyna i nauki o zdrowiu",
      przyklad: "medycyna",
      zrodla: [
        "Bochenek A., Reicher M. — Anatomia człowieka; Terminologia Anatomica (nazewnictwo)",
        "Konturek S. — Fizjologia człowieka; Guyton & Hall — Textbook of Medical Physiology",
        "Kostowski W., Herman Z. — Farmakologia. Podstawy farmakoterapii",
        "Szczeklik A. (red.) — Interna Szczeklika, wydanie aktualne",
        "Kumar V., Abbas A., Aster J. — Robbins & Cotran Pathologic Basis of Disease",
        "aktualne wytyczne towarzystw naukowych (ESC, PTK, PTD, WHO) — wyłącznie gdy znasz ich rok wydania",
      ],
      rygor: [
        [
          "Nie podawaj dawek ani wartości referencyjnych, jeżeli nie masz pewności.",
          "Dotyczy to również przedziałów norm laboratoryjnych i schematów dawkowania.",
        ],
        [
          "Nie formułuj zaleceń terapeutycznych poza treścią źródła.",
          "Materiał ma uczyć do egzaminu, a nie zastępować wytycznych klinicznych.",
        ],
      ],
      wskazowki: [
        "Priorytet materiału wysokowydajnego: mechanizmy, kryteria rozpoznania, objawy patognomoniczne, cechy różnicujące, powikłania.",
      ],
    },
    prawo: {
      etykieta: "Prawo i administracja",
      przyklad: "ogolny",
      zrodla: [
        "teksty jednolite aktów prawnych w brzmieniu obowiązującym",
        "uznane komentarze i podręczniki akademickie z danej gałęzi prawa",
        "orzecznictwo sądów najwyższych instancji, wyłącznie gdy znasz sygnaturę",
      ],
      rygor: [
        [
          "Zaznacz stan prawny.",
          'W polu "note" wskaż, na jaki dzień lub rok podajesz stan prawny.',
          "Jeżeli nie masz pewności co do aktualnego brzmienia przepisu, pomiń zagadnienie.",
        ],
        [
          "Nie cytuj numerów artykułów z pamięci.",
          "Numer przepisu podawaj tylko wtedy, gdy masz co do niego pewność; inaczej opisz instytucję prawną bez numeru.",
        ],
      ],
      wskazowki: [
        "Rozróżniaj definicję ustawową od poglądu doktryny — jeżeli podajesz pogląd, zaznacz to wprost.",
      ],
    },
    it: {
      etykieta: "Technologia i IT",
      przyklad: "ogolny",
      zrodla: [
        "oficjalna dokumentacja projektu, języka lub narzędzia",
        "specyfikacje i normy (RFC, W3C, ISO, POSIX)",
        "uznane podręczniki i opracowania techniczne",
      ],
      rygor: [
        [
          "Przypisz fakt do wersji.",
          'Jeżeli zachowanie zależy od wersji narzędzia, podaj ją w polu "note".',
          "Zagadnienia zmieniające się między wersjami, co do których nie masz pewności — pomiń.",
        ],
        [
          "Nie wymyślaj nazw funkcji, flag ani parametrów.",
          "Nieistniejąca opcja w dokumentacji to błąd, który kosztuje godziny debugowania.",
        ],
      ],
      wskazowki: [
        "Fragmenty kodu w treści fiszki wstawiaj krótkie i kompletne — muszą dać się uruchomić lub odczytać bez kontekstu.",
      ],
    },
    jezyki: {
      etykieta: "Języki obce",
      przyklad: "jezyki",
      zrodla: [
        "słowniki jednojęzyczne i dwujęzyczne renomowanych wydawnictw",
        "podręczniki i repetytoria przypisane do poziomu (na przykład skali CEFR)",
        "korpusy językowe i materiały wydawane przez instytucje danego języka",
      ],
      rygor: [
        [
          "Zdania przykładowe muszą być poprawne i naturalne.",
          "Nie twórz zdań, co do których nie masz pewności gramatycznej ani stylistycznej.",
        ],
        [
          "Oznacz rejestr i zasięg.",
          "Jeżeli wyrażenie jest potoczne, przestarzałe albo regionalne, napisz o tym w notatce.",
        ],
      ],
      wskazowki: [
        'Awers zawiera wyłącznie termin w języku obcym. Rewers: znaczenie po polsku, w razie potrzeby wymowa, oraz jedno krótkie zdanie przykładowe z tłumaczeniem.',
        "Nie umieszczaj tłumaczenia na awersie — zniweczyłoby to sens nauki fiszkami.",
      ],
    },
    humanistyka: {
      etykieta: "Humanistyka i nauki społeczne",
      przyklad: "ogolny",
      zrodla: [
        "podręczniki akademickie i syntezy uznane w danej dyscyplinie",
        "opracowania źródłowe i edycje krytyczne tekstów",
        "recenzowane publikacje naukowe",
      ],
      rygor: [
        [
          "Oddzielaj fakt od interpretacji.",
          "Jeżeli podajesz stanowisko badacza lub szkoły, zaznacz to wprost zamiast przedstawiać je jako fakt.",
        ],
        [
          "Daty i nazwiska podawaj tylko przy pewności.",
          "Przy sporach o datowanie napisz o rozbieżności zamiast wybierać jedną wersję.",
        ],
      ],
      wskazowki: [
        "Przy zjawiskach i nurtach wskazuj cechy odróżniające je od sąsiednich — to one są sprawdzane na egzaminie.",
      ],
    },
  };

  /* ------------------------------------------------------------------ */
  /* Poziomy odbiorcy — niezależne od dziedziny                          */
  /* ------------------------------------------------------------------ */
  const POZIOMY = {
    wprowadzenie: {
      etykieta: "Wprowadzenie — pierwszy kontakt z tematem",
      opis:
        "osoba poznająca temat od podstaw; nacisk na definicje, podstawowe pojęcia i proste " +
        "zależności, bez zakładania wcześniejszej wiedzy",
    },
    studia: {
      etykieta: "Poziom akademicki — studia lub kurs kierunkowy",
      opis:
        "osoba ucząca się przedmiotu kierunkowego; nacisk na mechanizmy, klasyfikacje, " +
        "zależności przyczynowo-skutkowe i umiejętność porównywania pojęć",
    },
    egzamin: {
      etykieta: "Przygotowanie do egzaminu lub certyfikacji",
      opis:
        "osoba przygotowująca się do egzaminu; materiał wysokowydajny, pytania w stylu " +
        "egzaminacyjnym, nacisk na treści faktycznie sprawdzane i typowe pułapki",
    },
    ekspercki: {
      etykieta: "Poziom ekspercki — praktyka zawodowa",
      opis:
        "praktyk pogłębiający wiedzę; nacisk na przypadki graniczne, wyjątki od reguły, " +
        "aktualne standardy i niuanse rozstrzygające w praktyce",
    },
    slownictwo: {
      etykieta: "Terminologia i słownictwo",
      opis:
        "nauka nazewnictwa i słownictwa fachowego; awers zawiera termin, rewers jego " +
        "odpowiedniki, znaczenie i krótkie objaśnienie",
    },
  };

  /* ------------------------------------------------------------------ */
  /* Układ językowy fiszek                                               */
  /* ------------------------------------------------------------------ */
  const JEZYKI = {
    pl: {
      etykieta: "Tylko polski",
      instrukcja:
        "Treść fiszek i pytań w całości po polsku. Terminy obcojęzyczne podawaj w nawiasie " +
        "tylko wtedy, gdy są powszechnie używane w tej dziedzinie albo występują w materiale źródłowym.",
    },
    pl_ang: {
      etykieta: "Polski + angielski odpowiednik",
      instrukcja:
        'Rewers każdej fiszki zawiera odpowiednik angielski w osobnym wierszu, w postaci ' +
        '"angielski: <termin>". Musi to być termin używany w fachowym piśmiennictwie, ' +
        "nie tłumaczenie dosłowne. Pozostała treść po polsku.",
    },
    pl_lac_ang: {
      etykieta: "Polski + łacina + angielski",
      instrukcja:
        "Awers fiszki zawiera termin łaciński w formie przyjętej w tej dziedzinie " +
        "(na przykład Terminologia Anatomica w anatomii albo nazwa systematyczna w biologii). " +
        'Rewers ma dokładnie dwa wiersze:\n    polski: <nazwa polska>\n    angielski: <nazwa angielska>\n' +
        "Nazwa łacińska musi być poprawna gramatycznie, a angielska — używana w piśmiennictwie fachowym.",
    },
    obcy_pl: {
      etykieta: "Dwujęzyczna — termin obcy na awersie",
      instrukcja:
        "Awers zawiera wyłącznie termin lub zwrot w języku, którego dotyczy materiał — bez tłumaczenia. " +
        "Rewers zawiera znaczenie po polsku, a gdy ma to znaczenie dydaktyczne, także zapis wymowy " +
        "oraz jedno krótkie zdanie przykładowe wraz z tłumaczeniem, każde w osobnym wierszu.",
    },
  };

  /* ------------------------------------------------------------------ */
  /* Szablony startowe z różnych dziedzin                                */
  /* ------------------------------------------------------------------ */
  const SZABLONY = {
    anatomia: {
      etykieta: "Anatomia — nazewnictwo",
      profil: "medycyna",
      dziedzina: "Anatomia prawidłowa człowieka",
      temat: "Kości kończyny górnej wraz z punktami orientacyjnymi badania fizykalnego",
      poziom: "slownictwo",
      jezyki: "pl_lac_ang",
      fiszki: 30,
      pytania: 8,
    },
    farmakologia: {
      etykieta: "Farmakologia — grupa leków",
      profil: "medycyna",
      dziedzina: "Farmakologia kliniczna",
      temat: "Leki hipotensyjne: inhibitory konwertazy angiotensyny, sartany, beta-blokery i diuretyki tiazydowe",
      poziom: "egzamin",
      jezyki: "pl",
      fiszki: 35,
      pytania: 12,
    },
    prawo: {
      etykieta: "Prawo — instytucje kodeksowe",
      profil: "prawo",
      dziedzina: "Prawo cywilne — część ogólna",
      temat: "Czynności prawne: forma, wady oświadczenia woli i skutki ich wystąpienia",
      poziom: "studia",
      jezyki: "pl",
      fiszki: 30,
      pytania: 12,
    },
    it: {
      etykieta: "IT — narzędzie i jego model pojęciowy",
      profil: "it",
      dziedzina: "Konteneryzacja i orkiestracja",
      temat: "Kubernetes: obiekty Pod, Deployment, Service i ConfigMap oraz zależności między nimi",
      poziom: "studia",
      jezyki: "pl_ang",
      fiszki: 30,
      pytania: 10,
    },
    jezyk: {
      etykieta: "Język obcy — słownictwo",
      profil: "jezyki",
      dziedzina: "Język hiszpański, poziom B1",
      temat: "Czasowniki nieregularne w czasie teraźniejszym wraz z typowymi konstrukcjami",
      poziom: "slownictwo",
      jezyki: "obcy_pl",
      fiszki: 40,
      pytania: 10,
    },
    historia: {
      etykieta: "Historia — okres i procesy",
      profil: "humanistyka",
      dziedzina: "Historia Polski XX wieku",
      temat: "II Rzeczpospolita: ustrój, przewrót majowy i polityka zagraniczna",
      poziom: "egzamin",
      jezyki: "pl",
      fiszki: 30,
      pytania: 12,
    },
  };

  /* ------------------------------------------------------------------ */
  /* Komponent                                                           */
  /* ------------------------------------------------------------------ */
  function promptGenerator() {
    return {
      // Konfiguracja
      profil: "ogolny",
      dziedzina: "",
      temat: "",
      zrodlo: "wlasne",
      wlasneZrodla: "",
      poziom: "studia",
      jezyki: "pl",
      fiszki: 30,
      pytania: 12,
      wymagajZrodel: true,
      wielokrotnyWybor: true,
      dodatkowe: "",
      // Interfejs
      zakladka: "claude",
      podglad: true,

      get profile() {
        return Object.entries(PROFILE).map(([klucz, wartosc]) => ({ klucz, ...wartosc }));
      },
      get poziomy() {
        return Object.entries(POZIOMY).map(([klucz, wartosc]) => ({ klucz, ...wartosc }));
      },
      get jezykiOpcje() {
        return Object.entries(JEZYKI).map(([klucz, wartosc]) => ({ klucz, ...wartosc }));
      },
      get szablony() {
        return Object.entries(SZABLONY).map(([klucz, wartosc]) => ({ klucz, ...wartosc }));
      },
      get aktywnyProfil() {
        return PROFILE[this.profil] || PROFILE.ogolny;
      },

      zastosujSzablon(klucz) {
        const szablon = SZABLONY[klucz];
        if (!szablon) return;
        this.profil = szablon.profil;
        this.dziedzina = szablon.dziedzina;
        this.temat = szablon.temat;
        this.poziom = szablon.poziom;
        this.jezyki = szablon.jezyki;
        this.fiszki = szablon.fiszki;
        this.pytania = szablon.pytania;
        this.zrodlo = "wiedza";
        toast(`Wczytano szablon: ${szablon.etykieta}`, "success", 2200);
      },

      get dziedzinaDoPromptu() {
        return this.dziedzina.trim() || "<WPISZ DZIEDZINĘ LUB PRZEDMIOT>";
      },
      get tematDoPromptu() {
        return this.temat.trim() || "<WPISZ TEMAT LUB ZAKRES MATERIAŁU>";
      },
      get liczbaFiszek() {
        return Math.max(1, Math.min(300, Number(this.fiszki) || 1));
      },
      get liczbaPytan() {
        return Math.max(0, Math.min(150, Number(this.pytania) || 0));
      },
      get brakujeDanych() {
        return !this.dziedzina.trim() || !this.temat.trim();
      },

      /** Sekcja opisująca dopuszczalne źródła wiedzy. */
      get sekcjaZrodel() {
        if (this.zrodlo === "wlasne") {
          const wiersze = [
            "## ŹRÓDŁO WIEDZY — materiały dołączone przez użytkownika",
            "",
            "Opieraj się WYŁĄCZNIE na treści dołączonych materiałów (plik PDF, skan, notatki, wykład).",
            "Nie uzupełniaj luk wiedzą własną, nawet jeśli jesteś jej pewien — ten materiał służy",
            "do nauki przed konkretnym zaliczeniem i musi odpowiadać temu, czego wymaga prowadzący.",
            "",
            "Jeżeli w materiale czegoś brakuje albo fragment jest nieczytelny, pomiń to zagadnienie.",
            "Nie dopisuj komentarza o pominięciu — po prostu nie twórz takiej fiszki.",
          ];
          if (this.wlasneZrodla.trim()) {
            wiersze.push(
              "",
              "Dodatkowe wskazania użytkownika co do źródeł:",
              ...this.wlasneZrodla.trim().split("\n").map((linia) => `- ${linia.trim()}`),
            );
          }
          return wiersze.join("\n");
        }

        const zrodla = this.wlasneZrodla.trim()
          ? this.wlasneZrodla.trim().split("\n").map((linia) => linia.trim())
          : this.aktywnyProfil.zrodla;

        return [
          "## ŹRÓDŁO WIEDZY — sprawdzone opracowania z danej dziedziny",
          "",
          `Dziedzina: ${this.dziedzinaDoPromptu}`,
          "",
          "Opieraj się wyłącznie na treściach zgodnych z uznanymi, weryfikowalnymi źródłami.",
          "Punkt odniesienia:",
          "",
          ...zrodla.map((pozycja) => `- ${pozycja}`),
          "",
          "Zasada nadrzędna: umieszczaj wyłącznie informacje, co do których masz wysoką pewność,",
          "że są zgodne z powyższymi źródłami i powszechnie uznane w tej dziedzinie. Treści sporne,",
          "niszowe, szybko się zmieniające lub zależne od lokalnego kontekstu — pomiń.",
          "",
          "Jeżeli źródła podają rozbieżne ustalenia, napisz o tym wprost w polu \"note\" albo pomiń",
          "zagadnienie. Nigdy nie wybieraj jednej wersji w milczeniu.",
        ].join("\n");
      },

      get sekcjaRygoru() {
        const zasady = [
          [
            "Nie wymyślaj.",
            "Nie podawaj liczb, dat, wartości, parametrów, nazw własnych, oznaczeń ani numerów,",
            "jeżeli nie masz co do nich pewności. Brak informacji jest lepszy niż informacja nieprawdziwa.",
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
            "Plan zajęć, spis literatury, podziękowania i dane kontaktowe nie są materiałem do nauki.",
          ],
          ...this.aktywnyProfil.rygor,
        ];

        if (this.wymagajZrodel) {
          zasady.push([
            "Oznacz umocowanie każdej fiszki.",
            'W polu "note" dopisz krótko, skąd pochodzi treść — na przykład „wykład 3, slajd 12”',
            "dla materiałów własnych albo nazwę opracowania, na którym opierasz fakt.",
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
          "Na podstawie tego materiału ktoś będzie się uczył do egzaminu i podejmował decyzje.",
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
          '- "note": kontekst, pułapka egzaminacyjna albo powiązanie z inną partią materiału.',
          "- Priorytet materiału wysokowydajnego: mechanizmy, kryteria, cechy różnicujące,",
          "  klasyfikacje, wyjątki od reguły i następstwa.",
          "",
          "### Pytania testowe",
          '- "prompt": konkretna sytuacja albo precyzyjne pytanie o fakt. Dokładnie jeden problem.',
          "- Dokładnie 4 warianty odpowiedzi.",
          this.wielokrotnyWybor
            ? "- Domyślnie jedna odpowiedź poprawna. Jeżeli zagadnienie wymaga kilku, napisz w treści\n  „Zaznacz wszystkie prawidłowe” i ustaw is_correct: true przy każdym poprawnym wariancie."
            : "- Zawsze dokładnie jedna odpowiedź poprawna. Nie twórz pytań wielokrotnego wyboru.",
          "- Dystraktory muszą być prawdopodobne i pochodzić z tej samej kategorii pojęciowej",
          "  co odpowiedź poprawna. Żadnych wariantów oczywiście absurdalnych.",
          "- Warianty podobnej długości i konstrukcji. Nie stosuj „wszystkie powyższe”",
          "  ani „żadne z powyższych”.",
          '- "explanation": tłumaczy mechanizm stojący za poprawną odpowiedzią, nie powtarza jej treści.',
          '- "feedback" przy wariancie błędnym: wskazuje, na czym polega pomyłka.',
          '- Nie umieszczaj liter „A)”, „B)” w polu "text" — numeracja powstaje automatycznie.',
          "",
          "### Język i układ",
          `- ${jezyk.instrukcja}`,
        ];

        const wskazowki = this.aktywnyProfil.wskazowki;
        if (wskazowki.length) {
          wiersze.push("", `### Specyfika dziedziny (${this.aktywnyProfil.etykieta})`, ...wskazowki.map((w) => `- ${w}`));
        }
        if (this.dodatkowe.trim()) {
          wiersze.push(
            "",
            "### Dodatkowe wymagania użytkownika",
            ...this.dodatkowe.trim().split("\n").map((linia) => `- ${linia.trim()}`),
          );
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
          "| `title` | tekst, 1–200 znaków | tak | tytuł zestawu widoczny na liście |",
          "| `description` | tekst, do 5000 znaków | nie | czego dotyczy materiał i skąd pochodzi |",
          "| `subject` | tekst, do 120 znaków | nie | jeden przedmiot wiodący |",
          "| `tags` | lista tekstów, do 20 pozycji | nie | 2–5 tagów tematycznych ułatwiających wyszukiwanie |",
          '| `visibility` | "private" albo "public" | nie | ustaw "private" |',
          "| `cards` | lista fiszek | tak* | patrz niżej |",
          "| `questions` | lista pytań | tak* | patrz niżej |",
          "",
          "\\* przynajmniej jedna z list musi być niepusta.",
          "",
          "### Element listy `cards` (fiszka)",
          "",
          "| pole | typ | wymagane | znaczenie |",
          "|---|---|---|---|",
          "| `front` | tekst, 1–8000 znaków | tak | awers: pojęcie lub pytanie |",
          "| `back` | tekst, 1–20000 znaków | tak | rewers: pełna odpowiedź |",
          "| `hint` | tekst, do 4000 znaków | nie | wskazówka odsłaniana na życzenie |",
          "| `note` | tekst, do 8000 znaków | nie | notatka dodatkowa, kontekst, pułapka |",
          "",
          "### Element listy `questions` (pytanie)",
          "",
          "| pole | typ | wymagane | znaczenie |",
          "|---|---|---|---|",
          "| `prompt` | tekst, 1–8000 znaków | tak | treść pytania |",
          "| `explanation` | tekst, do 20000 znaków | nie | uzasadnienie poprawnej odpowiedzi |",
          "| `options` | lista 2–10 wariantów | tak | warianty odpowiedzi |",
          "",
          "### Element listy `options` (wariant odpowiedzi)",
          "",
          "| pole | typ | wymagane | znaczenie |",
          "|---|---|---|---|",
          '| `text` | tekst, 1–4000 znaków | tak | treść wariantu, BEZ prefiksu "A) " |',
          "| `is_correct` | prawda/fałsz | tak | czy wariant jest poprawny |",
          "| `feedback` | tekst, do 4000 znaków | nie | komentarz do tego konkretnego wariantu |",
          "",
          "### Reguły, których naruszenie powoduje odrzucenie elementu",
          "",
          "- fiszka bez `front` albo bez `back` zostaje pominięta przy imporcie,",
          "- pytanie musi mieć co najmniej 2 warianty i co najmniej jeden z `is_correct: true`,",
          "- pola `multiple` NIE podajesz — aplikacja wylicza je sama na podstawie liczby",
          "  wariantów oznaczonych jako poprawne,",
          "- nie dodawaj pól spoza powyższych tabel,",
          "- znak nowego wiersza wewnątrz tekstu zapisuj jako `\\n`.",
        ].join("\n");
      },

      get sekcjaPrzykladu() {
        const przyklad = PRZYKLADY[this.aktywnyProfil.przyklad] || PRZYKLADY.ogolny;
        return [
          "## PRZYKŁAD POPRAWNEJ ODPOWIEDZI (skrócony)",
          "",
          przyklad.podpis,
          "",
          "```json",
          ...przyklad.tresc,
          "```",
        ].join("\n");
      },

      get sekcjaFormatu() {
        return [
          "## FORMAT ODPOWIEDZI",
          "",
          "- Odpowiedz WYŁĄCZNIE obiektem JSON. Bez zdania wstępu, bez podsumowania, bez komentarzy.",
          "- Pierwszy znak odpowiedzi to `{`, ostatni to `}`.",
          "- Kodowanie UTF-8, znaki diakrytyczne zapisane wprost (nie `\\u0105`).",
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
          "Jesteś doświadczonym dydaktykiem i redaktorem materiałów do nauki.",
          `Specjalizujesz się w dziedzinie: ${this.dziedzinaDoPromptu}.`,
          "Twoim zadaniem jest przygotowanie pakietu fiszek i pytań testowych w formacie JSON,",
          "który zostanie zaimportowany do aplikacji MTQuiz.",
          "",
          "# ZADANIE",
          "",
          `Dziedzina: ${this.dziedzinaDoPromptu}`,
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
        const nazwa = (this.temat.trim() || this.dziedzina.trim() || "prompt-mtquiz")
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
