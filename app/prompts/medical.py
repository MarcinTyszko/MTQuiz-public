"""Tryby generatora promptu dla studentów kierunku lekarskiego.

Trzy tryby, każdy wyłącznie z pytaniami zamkniętymi ABCD:

* ``lek`` — pytania w standardzie Lekarskiego Egzaminu Końcowego i kolokwiów
  klinicznych: winiety kliniczne, jedna odpowiedź najlepsza, rzetelne
  uzasadnienie;
* ``anatomia`` — topografia, unaczynienie, unerwienie, rzuty narządów
  i relacje anatomiczne z korelacją kliniczną;
* ``synteza`` — kompresja wklejonego fragmentu podręcznika do treści
  wysokowydajnych wraz z mnemotechnikami.

Strojenie promptów: zmieniaj krotki wierszy poniżej. Testy w
``tests/test_prompt_modes.py`` pilnują, by przykłady przechodziły import bez
uwag i trzymały się formatu ABCD.
"""
from __future__ import annotations

from ..permissions import Permission
from .base import CLOSED_QUESTION_RULES, PromptMode, SourceTextSpec

_BADGE = "Student medycyny"
_GROUP = "Tryby medyczne"

# Rygor wspólny dla wszystkich trybów medycznych.
_MEDICAL_RIGOR: tuple[tuple[str, ...], ...] = (
    (
        "Dawki, normy laboratoryjne i punkty odcięcia — tylko przy pewności.",
        "Podawaj je z jednostkami. Jeżeli wartość różni się między wytycznymi lub laboratoriami,",
        "opisz zależność jakościowo albo pomiń zagadnienie.",
    ),
    (
        "Materiał uczy do egzaminu, nie zastępuje wytycznych.",
        "Nie formułuj zaleceń terapeutycznych wykraczających poza źródło.",
    ),
)


# --------------------------------------------------------------------------- #
# LEK i egzaminy kliniczne
# --------------------------------------------------------------------------- #
LEK = PromptMode(
    key="lek",
    label="LEK i egzaminy kliniczne",
    summary="Pytania w standardzie LEK, kolokwiów i seminariów: winiety kliniczne, jedna odpowiedź najlepsza.",
    badge=_BADGE,
    group=_GROUP,
    permission=Permission.MEDICAL_PROMPTS,
    role=(
        "Jesteś lekarzem-dydaktykiem i autorem pytań egzaminacyjnych z wieloletnim doświadczeniem",
        "w przygotowywaniu testów na poziomie Lekarskiego Egzaminu Końcowego (LEK) oraz kolokwiów",
        "i seminariów klinicznych na kierunku lekarskim. Piszesz pytania, które sprawdzają",
        "rozumowanie kliniczne — rozpoznanie, różnicowanie i postępowanie — a nie pamięciowe",
        "odtwarzanie definicji. Każde pytanie przechodzi u Ciebie recenzję merytoryczną,",
        "zanim trafi do zestawu.",
    ),
    instructions=(
        "## WYMAGANIA TRYBU — LEK i egzaminy kliniczne",
        "",
        *CLOSED_QUESTION_RULES,
        "",
        "### Konstrukcja pytania (standard „single best answer”)",
        "- Co najmniej 60% pytań buduj jako winietę kliniczną: wiek i płeć, główna dolegliwość",
        "  i czas jej trwania, istotne odchylenia w badaniu przedmiotowym, wyniki badań",
        "  dodatkowych z jednostkami — wyłącznie dane potrzebne do rozwiązania i typowe",
        "  „szumy” obecne w prawdziwym wywiadzie.",
        "- Pozostałe pytania: mechanizm, patofizjologia, farmakologia, kryteria rozpoznania,",
        "  postępowanie — sformułowane jednoznacznie.",
        "- Treść kończy się jasnym poleceniem, np. „Najbardziej prawdopodobnym rozpoznaniem jest:”,",
        "  „Lekiem z wyboru jest:”, „Kolejnym krokiem postępowania powinno być:”,",
        "  „Które badanie należy wykonać w pierwszej kolejności?”.",
        "- Test zakrytych odpowiedzi: dobrze przygotowany student powinien znać odpowiedź,",
        "  zanim przeczyta warianty.",
        "- Unikaj negacji („Które NIE…”, „z wyjątkiem”). Jeżeli jest nieodzowna, zapisz ją",
        "  wielkimi literami.",
        "- Nie zostawiaj wskazówek: słowo-klucz z treści nie może się powtarzać wyłącznie",
        "  w poprawnym wariancie.",
        "",
        "### Warianty odpowiedzi",
        "- Wszystkie cztery z tej samej kategorii: same rozpoznania, same leki, same badania",
        "  albo same kroki postępowania.",
        "- Dystraktory odzwierciedlają typowe błędy rozumowania: jednostkę z rozpoznania",
        "  różnicowego, lek z tej samej grupy o innym wskazaniu, właściwe badanie w złej kolejności.",
        "- Podobna długość i szczegółowość — poprawna odpowiedź nie może wyróżniać się precyzją.",
        "",
        "### Uzasadnienie",
        '- "explanation" (3–6 zdań): kluczowe przesłanki z treści → mechanizm lub kryterium → wniosek.',
        '  Zakończ zdaniem zaczynającym się od „Zapamiętaj:” — jedna perła egzaminacyjna.',
        '- "feedback" przy każdym dystraktorze: kiedy ten wariant byłby prawidłowy albo dlaczego',
        "  w tej sytuacji odpada.",
        "",
        "### Dobór i trudność",
        "- Treści faktycznie sprawdzane: jednostki częste i groźne, stany nagłe, leki pierwszego",
        "  wyboru, przeciwwskazania, interakcje, powikłania, kryteria rozpoznania.",
        "- Rozkład trudności: około 20% łatwych (fakt kluczowy), 60% średnich (zastosowanie",
        "  w przypadku), 20% trudnych (różnicowanie bliskich jednostek, rozumowanie dwuetapowe).",
        "- Jeżeli postępowanie zmieniało się w ostatnich latach, a nie masz pewności co do",
        '  obowiązujących zaleceń — pomiń pytanie. Przy pytaniach o wytyczne podaj w polu "note"',
        "  przy fiszce albo w uzasadnieniu nazwę towarzystwa i rok wydania.",
        "",
        "### Fiszki (jeżeli zamówiono)",
        "- Uzupełniają pytania: awers pyta o perłę kliniczną („Lek z wyboru w…”, „Objaw",
        "  patognomoniczny…”), rewers podaje odpowiedź z jednozdaniowym uzasadnieniem.",
    ),
    sources=(
        "Szczeklik A. (red.) — Interna Szczeklika, wydanie aktualne",
        "Noszczyk W. (red.) — Chirurgia",
        "Bręborowicz G.H. (red.) — Położnictwo i ginekologia",
        "Kawalec W., Grenda R. (red.) — Pediatria",
        "Jarema M. (red.) — Psychiatria. Podręcznik dla studentów medycyny",
        "Kostowski W., Herman Z. — Farmakologia. Podstawy farmakoterapii",
        "Charakterystyki Produktów Leczniczych (ChPL) — wskazania, przeciwwskazania, działania niepożądane",
        "wytyczne towarzystw naukowych (np. ESC, PTK, PTD, ERC) — wyłącznie gdy znasz ich rok wydania",
    ),
    rigor=(
        (
            "Jedna odpowiedź jednoznacznie najlepsza.",
            "Jeżeli dwa warianty mogłyby zostać uznane za poprawne w zależności od wytycznych",
            "albo interpretacji, przeredaguj pytanie lub je pomiń.",
        ),
        *_MEDICAL_RIGOR,
    ),
    example_caption="Przykład pytania w standardzie LEK (winieta kliniczna) i fiszki uzupełniającej.",
    example={
        "title": "Endokrynologia — nadczynność tarczycy",
        "description": "Rozpoznanie i różnicowanie przyczyn nadczynności tarczycy w pytaniach w stylu LEK.",
        "subject": "Choroby wewnętrzne",
        "tags": ["LEK", "Endokrynologia", "Tarczyca"],
        "visibility": "private",
        "cards": [
            {
                "front": "Choroba Gravesa-Basedowa — badanie potwierdzające autoimmunologiczne podłoże",
                "back": "Oznaczenie przeciwciał przeciwko receptorowi TSH (TRAb). Ich obecność potwierdza, "
                "że nadczynność wynika z pobudzania receptora przez autoprzeciwciała.",
                "hint": "Przeciwciała działające jak hormon przysadki.",
                "note": "Orbitopatia tarczycowa nie występuje w wolu guzkowym toksycznym.",
            }
        ],
        "questions": [
            {
                "prompt": "Kobieta, 26 lat, od 3 miesięcy zgłasza kołatanie serca, drżenie rąk, nietolerancję "
                "ciepła i spadek masy ciała o 6 kg. W badaniu: tętno 112/min, wytrzeszcz obustronny, "
                "rozlane powiększenie tarczycy ze szmerem naczyniowym. TSH obniżone, FT4 podwyższone. "
                "Najbardziej prawdopodobnym rozpoznaniem jest:",
                "explanation": "Nadczynność tarczycy z orbitopatią i rozlanym wolem naczyniowym u młodej kobiety "
                "jest obrazem typowym dla choroby Gravesa-Basedowa — autoimmunologicznej choroby, w której "
                "przeciwciała pobudzają receptor TSH. Orbitopatia jest dla niej charakterystyczna i nie "
                "występuje w wolu guzkowym toksycznym ani w podostrym zapaleniu tarczycy. "
                "Zapamiętaj: nadczynność + orbitopatia = choroba "
                "Gravesa-Basedowa; potwierdzeniem jest oznaczenie TRAb.",
                "options": [
                    {
                        "text": "Wole guzkowe toksyczne",
                        "is_correct": False,
                        "feedback": "Dotyczy zwykle osób starszych, daje guzki w badaniu i nie powoduje orbitopatii.",
                    },
                    {
                        "text": "Podostre zapalenie tarczycy",
                        "is_correct": False,
                        "feedback": "Przebiega z bolesnością tarczycy, gorączką i wysokim OB, bez wytrzeszczu.",
                    },
                    {
                        "text": "Choroba Gravesa-Basedowa",
                        "is_correct": True,
                        "feedback": "Orbitopatia i wole naczyniowe przesądzają o rozpoznaniu.",
                    },
                    {
                        "text": "Faza nadczynności w chorobie Hashimoto",
                        "is_correct": False,
                        "feedback": "Bywa przejściowa i łagodna; orbitopatia nie należy do jej typowego obrazu.",
                    },
                ],
            }
        ],
    },
    defaults={
        "dziedzina": "Choroby wewnętrzne",
        "poziom": "egzamin",
        "jezyki": "pl",
        "fiszki": 10,
        "pytania": 30,
        "zrodlo": "wiedza",
        "wymagajZrodel": True,
    },
)


# --------------------------------------------------------------------------- #
# Anatomia topograficzna i kliniczna
# --------------------------------------------------------------------------- #
ANATOMIA = PromptMode(
    key="anatomia",
    label="Anatomia",
    summary="Topografia, unaczynienie, unerwienie, rzuty narządów i relacje anatomiczne z korelacją kliniczną.",
    badge=_BADGE,
    group=_GROUP,
    permission=Permission.MEDICAL_PROMPTS,
    role=(
        "Jesteś anatomem i dydaktykiem prowadzącym zajęcia z anatomii prawidłowej człowieka",
        "na kierunku lekarskim. Uczysz anatomii topograficznej i klinicznej: student ma rozumieć",
        "położenie, sąsiedztwo, unaczynienie i unerwienie struktur oraz skutki ich uszkodzenia,",
        "a nie tylko znać ich nazwy.",
    ),
    instructions=(
        "## WYMAGANIA TRYBU — Anatomia topograficzna i kliniczna",
        "",
        "### Osie wiedzy — zestaw ma pokryć każdą z nich",
        "1. Położenie i rzut: rzut na powierzchnię ciała i szkielet (poziomy kręgów, żebra,",
        "   linie orientacyjne), punkty orientacyjne badania fizykalnego.",
        "2. Topografia i relacje: sąsiedztwo we wszystkich kierunkach, ściany i zawartość",
        "   przestrzeni (kanały, doły, trójkąty, otwory) oraz to, co przez nie przechodzi.",
        "3. Unaczynienie: źródło tętnic, uchodzenie żył, drenaż chłonny.",
        "4. Unerwienie: ruchowe (z poziomem segmentowym, gdy ma znaczenie), czuciowe, autonomiczne.",
        "5. Znaczenie kliniczne: skutki uszkodzenia, typowe miejsca urazów, dostępy",
        "   operacyjne, miejsca wkłuć i badania.",
        "Jedna fiszka nadal oznacza jeden fakt — osie rozkładaj na kolejne fiszki.",
        "",
        "### Nazewnictwo",
        "- Nazwy zgodne z Terminologia Anatomica; przy nazwie polskiej podawaj łacińską w nawiasie,",
        "  chyba że wybrano układ z łaciną na awersie.",
        "- Określenia kierunków i płaszczyzn zawsze w odniesieniu do pozycji anatomicznej.",
        "",
        "### Fiszki",
        "- Awers pyta precyzyjnie, np. „Zawartość kanału pachwinowego u mężczyzny”,",
        "  „Unerwienie ruchowe mięśnia naramiennego”, „Rzut koniuszka serca na ścianę klatki piersiowej”.",
        "- Rewers: odpowiedź kompletna dla danej osi; listy w porządku topograficznym",
        "  (od przodu do tyłu, od góry do dołu, od boku do środka) z nazwanym kierunkiem.",
        '- "hint" (widoczny przed odwróceniem): punkt orientacyjny albo sam klucz mnemotechniki,',
        '  bez zdradzania odpowiedzi. "note": rozkodowana mnemotechnika i korelacja kliniczna.',
        "",
        *CLOSED_QUESTION_RULES,
        "",
        "### Typy pytań anatomicznych",
        "- relacja topograficzna („Która struktura leży bezpośrednio do tyłu od…”),",
        "- unaczynienie lub unerwienie konkretnej struktury,",
        "- rzut i punkt orientacyjny,",
        "- kliniczne: objaw uszkodzenia → struktura („opadanie ręki po złamaniu trzonu kości ramiennej”),",
        "- zawartość przestrzeni anatomicznej.",
        "- Dystraktory: struktury sąsiednie, gałęzie tego samego pnia, nerwy tego samego splotu.",
        "- Warianty anatomiczne tylko wtedy, gdy mają znaczenie kliniczne i są powszechnie",
        "  omawiane — wtedy zaznacz, że to wariant.",
    ),
    sources=(
        "Bochenek A., Reicher M. — Anatomia człowieka",
        "Sobotta — Atlas anatomii człowieka",
        "Netter F.H. — Atlas anatomii człowieka",
        "Moore K.L., Dalley A.F., Agur A.M.R. — Clinically Oriented Anatomy",
        "Drake R.L., Vogl A.W., Mitchell A.W.M. — Gray's Anatomy for Students",
        "Terminologia Anatomica — nazewnictwo łacińskie",
    ),
    rigor=(
        (
            "Nie zgaduj poziomów i rzutów.",
            "Poziom kręgu, żebra czy przestrzeni międzyżebrowej podawaj tylko wtedy, gdy jest",
            "powszechnie przyjęty w podręcznikach; przy rozbieżnościach podaj zakres albo pomiń.",
        ),
        *_MEDICAL_RIGOR,
    ),
    example_caption="Przykład z anatomii kończyny górnej — relacja topograficzna i korelacja kliniczna.",
    example={
        "title": "Kończyna górna — nerwy i naczynia w topografii",
        "description": "Przebieg nerwów i naczyń kończyny górnej oraz skutki ich uszkodzenia.",
        "subject": "Anatomia",
        "tags": ["Anatomia", "Kończyna górna", "Topografia"],
        "visibility": "private",
        "cards": [
            {
                "front": "Zawartość dołu łokciowego w kierunku od boku do środka",
                "back": "Ścięgno mięśnia dwugłowego ramienia, tętnica ramienna, nerw pośrodkowy.",
                "hint": "Angielski skrót TAN, czytany od strony bocznej.",
                "note": "Mnemotechnika: TAN — Tendon, Artery, Nerve. Nerw promieniowy leży głębiej, "
                "pod mięśniem ramienno-promieniowym, przy bocznym brzegu dołu.",
            }
        ],
        "questions": [
            {
                "prompt": "Po złamaniu trzonu kości ramiennej w jego środkowej części pacjent nie może wyprostować "
                "nadgarstka ani palców, a czucie jest zaburzone na grzbiecie ręki między I a II kością "
                "śródręcza. Który nerw został uszkodzony?",
                "explanation": "Nerw promieniowy biegnie w bruździe nerwu promieniowego na tylnej powierzchni "
                "trzonu kości ramiennej, dlatego jest narażony przy złamaniach tej części kości. Unerwia "
                "prostowniki nadgarstka i palców, a jego gałąź powierzchowna — skórę grzbietu ręki po "
                "stronie promieniowej. Zapamiętaj: złamanie trzonu kości ramiennej → opadanie ręki → "
                "nerw promieniowy.",
                "options": [
                    {
                        "text": "Nerw pachowy",
                        "is_correct": False,
                        "feedback": "Uszkadzany przy złamaniu szyjki chirurgicznej; osłabia odwodzenie ramienia.",
                    },
                    {
                        "text": "Nerw łokciowy",
                        "is_correct": False,
                        "feedback": "Narażony za nadkłykciem przyśrodkowym; daje rękę szponiastą.",
                    },
                    {
                        "text": "Nerw pośrodkowy",
                        "is_correct": False,
                        "feedback": "Uszkodzenie osłabia zginanie i przeciwstawianie kciuka, nie prostowanie ręki.",
                    },
                    {
                        "text": "Nerw promieniowy",
                        "is_correct": True,
                        "feedback": "Biegnie w bruździe na trzonie kości ramiennej i unerwia prostowniki.",
                    },
                ],
            }
        ],
    },
    defaults={
        "dziedzina": "Anatomia prawidłowa człowieka",
        "poziom": "studia",
        "jezyki": "pl",
        "fiszki": 30,
        "pytania": 15,
        "zrodlo": "wiedza",
        "wymagajZrodel": True,
    },
)


# --------------------------------------------------------------------------- #
# Skrypt i synteza — kompresja wiedzy z mnemotechnikami
# --------------------------------------------------------------------------- #
SYNTEZA = PromptMode(
    key="synteza",
    label="Skrypt i synteza",
    summary="Wklejony fragment podręcznika → esencja high-yield z mnemotechnikami, fiszki i pytania ABCD.",
    badge=_BADGE,
    group=_GROUP,
    permission=Permission.MEDICAL_PROMPTS,
    role=(
        "Jesteś redaktorem materiałów do nauki dla studentów medycyny, specjalistą od kompresji",
        "wiedzy i technik pamięciowych. Z obszernego tekstu wydobywasz to, co egzaminacyjnie",
        "najważniejsze (high-yield), i zamieniasz to w fiszki oraz pytania ABCD, które da się",
        "szybko powtórzyć — z mnemotechnikami tam, gdzie pamięć potrzebuje zaczepienia.",
    ),
    instructions=(
        "## WYMAGANIA TRYBU — Skrypt i synteza (high-yield + mnemotechniki)",
        "",
        "### Etap 1 — selekcja (wykonaj w myślach, nie opisuj jej w odpowiedzi)",
        "- Przeczytaj cały fragment i wybierz treści high-yield: definicje kluczowe, mechanizmy,",
        "  klasyfikacje, kryteria, wartości graniczne podane w tekście, cechy różnicujące,",
        "  wyjątki, powikłania.",
        "- Odrzuć wstępy historyczne, powtórzenia, dygresje i przykłady bez nowej informacji.",
        "- Kompresuj, nie przepisuj: z około 300–500 słów tekstu powstają zwykle 2–4 fiszki.",
        "  Zamówiona liczba fiszek jest górną granicą — przy krótkim fragmencie oddaj mniej.",
        "",
        "### Etap 2 — fiszki syntetyczne",
        "- Awers pyta o jeden konkretny fakt lub zależność.",
        "- Rewers podaje esencję w 1–3 zdaniach, prościej niż podręcznik, bez utraty precyzji.",
        "- Listę zamykaj w jednej fiszce tylko wtedy, gdy ma najwyżej 5 elementów; dłuższe dziel.",
        "",
        "### Etap 3 — mnemotechniki",
        '- Dla list, sekwencji, klasyfikacji i trudnych nazw umieść w polu "note" pełną',
        "  mnemotechnikę wraz z rozkodowaniem, zaczynając od „Mnemotechnika:”. Notatka pojawia się",
        "  na rewersie razem z odpowiedzią, więc wspiera zapamiętywanie.",
        '- W polu "hint" (widocznym przed odwróceniem fiszki) możesz podać sam klucz',
        "  mnemotechniki bez rozkodowania, np. „Pomyśl o roku 1972.” — wskazówka nie może",
        "  zdradzać odpowiedzi.",
        "- Dopuszczalne rodzaje: akronim lub akrostych (po polsku albo powszechnie znany",
        "  angielski — wtedy to zaznacz), skojarzenie obrazowe, rym, krótka historyjka łącząca",
        "  elementy, rozbiór nazwy na znane cząstki (etymologia).",
        "- Mnemotechnika odtwarza elementy w tej samej kolejności co rewers. Sprawdź każdą literę",
        "  akronimu — błędna mnemotechnika utrwala błąd.",
        "- Stosuj ją tam, gdzie treść tego wymaga (zwykle co druga–trzecia fiszka). Jeżeli dobra",
        "  mnemotechnika nie istnieje, podaj zwykłą wskazówkę naprowadzającą zamiast wymuszonej.",
        "",
        *CLOSED_QUESTION_RULES,
        "",
        "### Etap 4 — pytania sprawdzające syntezę",
        "- Sprawdzaj zrozumienie i powiązania („Który mechanizm wyjaśnia…”, „Która cecha",
        "  odróżnia X od Y?”), a nie dosłowne zdania z tekstu.",
        '- "explanation" parafrazuje odpowiedni fragment materiału i wyjaśnia, dlaczego',
        "  dystraktory są błędne.",
        "",
        "### Streszczenie w opisie zestawu",
        '- Pole "description" to ściąga: 3–5 zdań streszczenia high-yield całego fragmentu,',
        "  do przeczytania przed rozpoczęciem nauki.",
    ),
    sources=(
        "wyłącznie fragment podręcznika lub skryptu wklejony poniżej promptu",
    ),
    rigor=(
        (
            "Synteza nie dodaje faktów.",
            "Upraszczasz język, ale każda informacja musi wynikać z wklejonego fragmentu.",
            "Mnemotechnika to narzędzie pamięciowe, nie nowy fakt.",
        ),
        *_MEDICAL_RIGOR,
    ),
    example_caption="Przykład syntezy fragmentu o krzepnięciu — mnemotechnika w polu hint i ściąga w opisie.",
    example={
        "title": "Hemostaza — czynniki zależne od witaminy K",
        "description": "Witamina K jest kofaktorem gamma-karboksylacji czynników II, VII, IX i X oraz białek "
        "C i S. Antagoniści witaminy K hamują ten proces, a najwcześniej spada aktywność czynnika VII, "
        "który ma najkrótszy okres półtrwania — dlatego INR rośnie jako pierwszy.",
        "subject": "Fizjologia",
        "tags": ["Hemostaza", "Witamina K", "Synteza"],
        "visibility": "private",
        "cards": [
            {
                "front": "Czynniki krzepnięcia zależne od witaminy K",
                "back": "Czynniki X, IX, VII i II (protrombina) oraz białka antykoagulacyjne C i S.",
                "hint": "Pomyśl o roku 1972.",
                "note": "Mnemotechnika: rok „1972” → czynniki 10, 9, 7 i 2. Białka C i S również zależą "
                "od witaminy K, ale działają przeciwkrzepliwie.",
            }
        ],
        "questions": [
            {
                "prompt": "Antagoniści witaminy K hamują gamma-karboksylację białek układu krzepnięcia. "
                "Który z wymienionych czynników krzepnięcia wymaga tej modyfikacji?",
                "explanation": "Karboksylaza zależna od witaminy K przekształca reszty kwasu glutaminowego "
                "czynników II, VII, IX i X, umożliwiając im wiązanie jonów wapnia na powierzchni "
                "fosfolipidów. Czynnik VIII, czynnik XII i fibrynogen nie podlegają tej modyfikacji, "
                "więc ich synteza nie zależy od witaminy K.",
                "options": [
                    {
                        "text": "Czynnik VIII",
                        "is_correct": False,
                        "feedback": "Nie wymaga karboksylacji; jego niedobór to hemofilia A.",
                    },
                    {
                        "text": "Czynnik VII",
                        "is_correct": True,
                        "feedback": "Należy do czynników II, VII, IX i X zależnych od witaminy K.",
                    },
                    {
                        "text": "Czynnik XII",
                        "is_correct": False,
                        "feedback": "Nie zależy od witaminy K.",
                    },
                    {
                        "text": "Fibrynogen",
                        "is_correct": False,
                        "feedback": "Fibrynogen (czynnik I) nie podlega karboksylacji zależnej od witaminy K.",
                    },
                ],
            }
        ],
    },
    defaults={
        "dziedzina": "",
        "poziom": "egzamin",
        "jezyki": "pl",
        "fiszki": 25,
        "pytania": 10,
        "zrodlo": "wlasne",
        "wymagajZrodel": False,
    },
    source_text=SourceTextSpec(
        label="Fragment podręcznika lub skryptu",
        placeholder="Wklej tutaj fragment rozdziału (tekst, nie zdjęcie) — z niego powstaną fiszki, "
        "mnemotechniki i pytania.",
        heading="## MATERIAŁ ŹRÓDŁOWY — fragment podręcznika",
        intro="Poniżej znajduje się fragment podręcznika wklejony przez użytkownika. To jedyne źródło, "
        "z którego wolno Ci korzystać.",
        min_chars=200,
    ),
)


MEDICAL_MODES: tuple[PromptMode, ...] = (LEK, ANATOMIA, SYNTEZA)
