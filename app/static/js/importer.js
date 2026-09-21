/** Import pakietów JSON: walidacja, podgląd i przekazanie danych do edytora. */
(function () {
  "use strict";
  const { api, toast } = window.MTQuiz;

  const IMPORT_KEY = "mtquiz-import-draft";

  const SYSTEM_PROMPT = `Jesteś asystentem przygotowującym materiały do nauki dla studenta medycyny.
Na podstawie dostarczonych materiałów źródłowych (PDF, notatki, skrypt) utwórz pakiet nauki
w formacie JSON zgodnym ze schematem "mtquiz/study-set".

ZASADY BEZWZGLĘDNE
1. Korzystaj wyłącznie z treści obecnych w materiale źródłowym. Nie dodawaj faktów spoza niego.
2. Jeżeli materiał nie pozwala sformułować pewnej odpowiedzi, pomiń zagadnienie zamiast zgadywać.
3. Nie wymyślaj dawek, wartości laboratoryjnych, nazw handlowych ani odsyłaczy do piśmiennictwa.
4. Odpowiedz wyłącznie obiektem JSON — bez komentarza przed i po, bez bloków markdown.

JAK BUDOWAĆ TREŚĆ
- Fiszki: jedno zagadnienie na fiszkę, awers zwięzły, rewers kompletny (1-3 zdania).
  Priorytet dla treści wysokowydajnych: mechanizmy, różnicowanie, objawy patognomoniczne, wyjątki.
- Pytania: styl egzaminu państwowego, 4 warianty, dystraktory prawdopodobne i wzajemnie wykluczające się.
  Pole "explanation" ma tłumaczyć, dlaczego odpowiedź jest poprawna, a "feedback" przy wariancie —
  dlaczego dany dystraktor jest błędny.
- Zachowaj polską terminologię anatomiczną i kliniczną zgodną z materiałem źródłowym.

SCHEMAT WYJŚCIOWY
{
  "title": string, "description": string, "subject": string, "tags": string[],
  "visibility": "private",
  "cards": [{ "front": string, "back": string, "hint": string?, "note": string? }],
  "questions": [{
    "prompt": string, "explanation": string,
    "options": [{ "text": string, "is_correct": boolean, "feedback": string? }]
  }]
}

Każde pytanie musi mieć dokładnie jedną poprawną odpowiedź, chyba że polecenie mówi inaczej —
wtedy oznacz wszystkie poprawne warianty wartością true.`;

  function jsonImporter() {
    return {
      source: "file",
      rawText: "",
      file: null,
      fileName: "",
      dragging: false,
      busy: false,
      preview: null,

      issues(severity) {
        if (!this.preview) return [];
        return this.preview.issues.filter((issue) => issue.severity === severity);
      },

      onFile(event) {
        const [file] = event.target.files || [];
        if (file) this.acceptFile(file);
      },

      onDrop(event) {
        this.dragging = false;
        const [file] = event.dataTransfer.files || [];
        if (file) this.acceptFile(file);
      },

      acceptFile(file) {
        this.file = file;
        this.fileName = `${file.name} (${Math.max(1, Math.round(file.size / 1024))} KB)`;
        this.preview = null;
        this.validate();
      },

      async validate() {
        this.busy = true;
        this.preview = null;
        try {
          if (this.source === "file" && this.file) {
            const form = new FormData();
            form.append("file", this.file);
            this.preview = await api.upload("/api/import/upload", form);
          } else {
            const text = this.rawText.trim();
            if (!text) {
              toast("Wklej treść JSON albo wybierz plik.", "warning");
              return;
            }
            this.preview = await api.post("/api/import/validate", { data: text });
          }

          if (this.preview.ok) {
            const warnings = this.issues("warning").length;
            toast(
              warnings
                ? `Pakiet poprawny, ale ${warnings} ${window.MTQuiz.plural(warnings, "element wymaga", "elementy wymagają", "elementów wymaga")} uwagi.`
                : "Pakiet jest poprawny.",
              warnings ? "warning" : "success"
            );
          } else {
            toast("Pakiet zawiera błędy krytyczne — zobacz szczegóły poniżej.", "error");
          }
        } catch (error) {
          toast(error.message || "Nie udało się przetworzyć pliku.", "error");
        } finally {
          this.busy = false;
        }
      },

      openInEditor() {
        if (!this.preview || !this.preview.payload) return;
        try {
          sessionStorage.setItem(IMPORT_KEY, JSON.stringify(this.preview.payload));
        } catch (error) {
          toast("Przeglądarka zablokowała pamięć sesji — zapisz pakiet bezpośrednio.", "error");
          return;
        }
        window.location.href = "/zestawy/nowy";
      },

      async commit() {
        if (!this.preview || !this.preview.payload) return;
        this.busy = true;
        try {
          const saved = await api.post("/api/import/commit", { data: this.preview.payload });
          toast("Zestaw został zapisany.", "success");
          window.location.href = `/zestawy/${saved.id}`;
        } catch (error) {
          toast(error.message || "Nie udało się zapisać zestawu.", "error");
        } finally {
          this.busy = false;
        }
      },

      async copyPrompt() {
        try {
          await navigator.clipboard.writeText(SYSTEM_PROMPT);
          toast("Prompt skopiowany do schowka.", "success");
        } catch (error) {
          // Awaryjnie: zaznaczenie treści w polu tekstowym.
          const area = document.createElement("textarea");
          area.value = SYSTEM_PROMPT;
          area.style.position = "fixed";
          area.style.opacity = "0";
          document.body.appendChild(area);
          area.select();
          try {
            document.execCommand("copy");
            toast("Prompt skopiowany do schowka.", "success");
          } catch (fallbackError) {
            toast("Nie udało się skopiować — zaznacz prompt ręcznie w pliku AI_SCHEMA.md.", "error");
          }
          area.remove();
        }
      },

      reset() {
        this.rawText = "";
        this.file = null;
        this.fileName = "";
        this.preview = null;
      },
    };
  }

  window.jsonImporter = jsonImporter;
})();
