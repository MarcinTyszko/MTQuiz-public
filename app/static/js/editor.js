/** Edytor zestawów: metadane, fiszki, pytania quizowe i zapis do API. */
(function () {
  "use strict";
  const { api, toast } = window.MTQuiz;

  const IMPORT_KEY = "mtquiz-import-draft";
  let keyCounter = 0;
  const nextKey = () => `k${(keyCounter += 1)}`;

  function blankCard() {
    return { _key: nextKey(), id: null, front: "", back: "", hint: "", note: "" };
  }

  function blankOption(text = "") {
    return { _key: nextKey(), id: null, text, is_correct: false, feedback: "" };
  }

  function blankQuestion() {
    return {
      _key: nextKey(),
      id: null,
      prompt: "",
      explanation: "",
      options: [blankOption(), blankOption(), blankOption(), blankOption()],
    };
  }

  function hydrateCard(card) {
    return {
      _key: nextKey(),
      id: card.id ?? null,
      front: card.front || "",
      back: card.back || "",
      hint: card.hint || "",
      note: card.note || "",
    };
  }

  function hydrateQuestion(question) {
    const options = (question.options || []).map((option) => ({
      _key: nextKey(),
      id: option.id ?? null,
      text: option.text || "",
      is_correct: Boolean(option.is_correct),
      feedback: option.feedback || "",
    }));
    while (options.length < 2) options.push(blankOption());
    return {
      _key: nextKey(),
      id: question.id ?? null,
      prompt: question.prompt || "",
      explanation: question.explanation || "",
      options,
    };
  }

  function setEditor(initial) {
    return {
      mode: initial.mode || "create",
      setId: initial.data ? initial.data.id : null,
      meta: { title: "", description: "", subject: "", visibility: "private", tags: [] },
      cards: [],
      questions: [],
      tab: "cards",
      tagDraft: "",
      collapsed: false,
      busy: false,
      errors: [],
      importBanner: false,
      dirty: false,

      init() {
        if (initial.data) {
          this.applyPayload(initial.data);
        } else {
          const draft = this.readImportDraft();
          if (draft) {
            this.applyPayload(draft);
            this.importBanner = true;
          } else {
            this.cards = [blankCard(), blankCard()];
          }
        }

        // Ostrzeżenie przed utratą niezapisanych zmian.
        this.$watch("meta", () => (this.dirty = true), { deep: true });
        this.$watch("cards", () => (this.dirty = true), { deep: true });
        this.$watch("questions", () => (this.dirty = true), { deep: true });
        window.addEventListener("beforeunload", (event) => {
          if (!this.dirty || this.busy) return;
          event.preventDefault();
          event.returnValue = "";
        });
      },

      readImportDraft() {
        try {
          const raw = sessionStorage.getItem(IMPORT_KEY);
          if (!raw) return null;
          sessionStorage.removeItem(IMPORT_KEY);
          return JSON.parse(raw);
        } catch (error) {
          return null;
        }
      },

      applyPayload(payload) {
        this.meta = {
          title: payload.title || "",
          description: payload.description || "",
          subject: payload.subject || "",
          visibility: payload.visibility || "private",
          tags: Array.isArray(payload.tags) ? payload.tags.slice(0, 20) : [],
        };
        this.cards = (payload.cards || []).map(hydrateCard);
        this.questions = (payload.questions || []).map(hydrateQuestion);
        if (!this.cards.length && this.questions.length) this.tab = "questions";
        this.$nextTick(() => (this.dirty = false));
      },

      addCard() {
        this.cards.push(blankCard());
        this.tab = "cards";
        this.$nextTick(() => this.focusLast("textarea"));
      },

      duplicateCard(index) {
        const source = this.cards[index];
        this.cards.splice(index + 1, 0, { ...source, _key: nextKey(), id: null });
      },

      addQuestion() {
        this.questions.push(blankQuestion());
        this.tab = "questions";
        this.$nextTick(() => this.focusLast("textarea"));
      },

      addOption(question) {
        if (question.options.length < 10) question.options.push(blankOption());
      },

      move(collection, index, delta) {
        const target = index + delta;
        if (target < 0 || target >= collection.length) return;
        const [item] = collection.splice(index, 1);
        collection.splice(target, 0, item);
      },

      focusLast(selector) {
        const nodes = this.$el.querySelectorAll(selector);
        if (nodes.length) nodes[nodes.length - 1].focus();
      },

      addTag() {
        const value = this.tagDraft.trim().replace(/,+$/, "");
        if (!value) return;
        const exists = this.meta.tags.some((tag) => tag.toLowerCase() === value.toLowerCase());
        if (!exists && this.meta.tags.length < 20) this.meta.tags.push(value.slice(0, 64));
        this.tagDraft = "";
      },

      removeTag(tag) {
        this.meta.tags = this.meta.tags.filter((item) => item !== tag);
      },

      /** Zbiera treść formularza w strukturę akceptowaną przez API. */
      buildPayload() {
        return {
          title: this.meta.title.trim(),
          description: this.meta.description.trim(),
          subject: this.meta.subject.trim(),
          visibility: this.meta.visibility,
          tags: this.meta.tags,
          cards: this.cards
            .filter((card) => card.front.trim() && card.back.trim())
            .map((card) => ({
              id: card.id,
              front: card.front.trim(),
              back: card.back.trim(),
              hint: card.hint.trim() || null,
              note: card.note.trim() || null,
            })),
          questions: this.questions.map((question) => ({
            id: question.id,
            prompt: question.prompt.trim(),
            explanation: question.explanation.trim() || null,
            options: question.options
              .filter((option) => option.text.trim())
              .map((option) => ({
                id: option.id,
                text: option.text.trim(),
                is_correct: Boolean(option.is_correct),
                feedback: option.feedback.trim() || null,
              })),
          })),
        };
      },

      validate(payload) {
        const errors = [];
        if (!payload.title) errors.push("Tytuł zestawu jest wymagany.");

        this.cards.forEach((card, index) => {
          const hasFront = Boolean(card.front.trim());
          const hasBack = Boolean(card.back.trim());
          if (hasFront !== hasBack) {
            errors.push(`Fiszka ${index + 1}: uzupełnij zarówno awers, jak i rewers.`);
          }
        });

        payload.questions.forEach((question, index) => {
          if (!question.prompt) errors.push(`Pytanie ${index + 1}: brak treści polecenia.`);
          if (question.options.length < 2) errors.push(`Pytanie ${index + 1}: wymagane są co najmniej dwa warianty.`);
          if (!question.options.some((option) => option.is_correct)) {
            errors.push(`Pytanie ${index + 1}: zaznacz co najmniej jedną poprawną odpowiedź.`);
          }
        });

        if (!payload.cards.length && !payload.questions.length) {
          errors.push("Zestaw musi zawierać przynajmniej jedną fiszkę lub jedno pytanie.");
        }
        return errors;
      },

      async save() {
        const payload = this.buildPayload();
        this.errors = this.validate(payload);
        if (this.errors.length) {
          window.scrollTo({ top: 0, behavior: "smooth" });
          toast("Formularz zawiera błędy — sprawdź listę na górze strony.", "error");
          return;
        }

        this.busy = true;
        try {
          const saved =
            this.mode === "edit"
              ? await api.put(`/api/sets/${this.setId}`, payload)
              : await api.post("/api/sets", payload);
          this.dirty = false;
          toast("Zestaw został zapisany.", "success");
          window.location.href = `/zestawy/${saved.id}`;
        } catch (error) {
          this.errors = [error.message || "Nie udało się zapisać zestawu."];
          window.scrollTo({ top: 0, behavior: "smooth" });
          toast(error.message || "Nie udało się zapisać zestawu.", "error");
        } finally {
          this.busy = false;
        }
      },
    };
  }

  window.setEditor = setEditor;
  window.MTQUIZ_IMPORT_KEY = IMPORT_KEY;
})();
