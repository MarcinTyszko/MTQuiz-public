/** Silnik quizu: tryb nauki i egzaminu, limit czasu, punktacja i omówienie. */
(function () {
  "use strict";
  const { api, toast, shuffle, formatDuration, readJsonScript, confirmDialog } = window.MTQuiz;

  function quizRunner() {
    return {
      set: { id: 0, title: "", questions: [] },
      stage: "setup",
      config: { count: 0, mode: "instant", shuffleQuestions: true, shuffleOptions: true, timed: false, minutes: 15 },
      questions: [],
      answers: {},
      index: 0,
      selection: [],
      revealed: false,
      lastCorrect: false,
      startedAt: 0,
      elapsed: 0,
      remaining: 0,
      timer: null,
      sessionSaved: false,

      init() {
        const data = readJsonScript("dane-zestawu");
        if (!data) {
          toast("Nie udało się wczytać zestawu.", "error");
          return;
        }
        this.set = data;
        // Wartość ustawiamy po wyrenderowaniu listy opcji, inaczej przeglądarka
        // cofnęłaby wybór do pierwszej pozycji (opcje powstają dopiero z szablonu).
        this.$nextTick(() => {
          this.config.count = data.questions.length;
        });
      },

      get countOptions() {
        const total = this.set.questions.length;
        const options = [5, 10, 20, 30, 50].filter((value) => value < total);
        options.push(total);
        return options;
      },

      get currentQuestion() {
        return this.questions[this.index] || null;
      },

      get canAdvance() {
        if (this.revealed) return true;
        return this.selection.length > 0;
      },

      get advanceLabel() {
        if (this.config.mode === "instant" && !this.revealed) return "Sprawdź";
        return this.index === this.questions.length - 1 ? "Zakończ quiz" : "Następne pytanie";
      },

      get score() {
        return this.breakdown.filter((entry) => entry.correct).length;
      },

      get percentage() {
        if (!this.questions.length) return 0;
        return Math.round((this.score / this.questions.length) * 100);
      },

      get elapsedLabel() {
        return formatDuration(this.elapsed);
      },

      get remainingLabel() {
        return formatDuration(Math.max(0, this.remaining));
      },

      /** Zestawienie pytanie → wybrane warianty → poprawność. */
      get breakdown() {
        return this.questions.map((question) => {
          const selected = this.answers[question.id] || [];
          return { question, selected, correct: this.isCorrect(question, selected) };
        });
      },

      get wrongQuestions() {
        return this.breakdown.filter((entry) => !entry.correct).map((entry) => entry.question);
      },

      isCorrect(question, selected) {
        const correctIds = question.options.filter((option) => option.is_correct).map((option) => option.id);
        if (!selected.length || selected.length !== correctIds.length) return false;
        return correctIds.every((id) => selected.includes(id));
      },

      buildQuestions(source) {
        const pool = this.config.shuffleQuestions ? shuffle(source) : source.slice();
        const limited = pool.slice(0, Math.max(1, Math.min(this.config.count || pool.length, pool.length)));
        return limited.map((question) => ({
          ...question,
          options: this.config.shuffleOptions ? shuffle(question.options) : question.options.slice(),
        }));
      },

      start() {
        this.questions = this.buildQuestions(this.set.questions);
        this.answers = {};
        this.index = 0;
        this.selection = [];
        this.revealed = false;
        this.sessionSaved = false;
        this.startedAt = Date.now();
        this.elapsed = 0;
        this.remaining = this.config.minutes * 60;
        this.stage = "run";
        this.startTimer();
      },

      startTimer() {
        window.clearInterval(this.timer);
        this.timer = window.setInterval(() => {
          if (this.stage !== "run") return;
          this.elapsed = Math.round((Date.now() - this.startedAt) / 1000);
          if (this.config.timed) {
            this.remaining = this.config.minutes * 60 - this.elapsed;
            if (this.remaining <= 0) {
              toast("Czas minął — quiz został zakończony.", "warning");
              this.finish();
            }
          }
        }, 1000);
      },

      choose(option) {
        if (this.revealed) return;
        const question = this.currentQuestion;
        if (!question) return;

        if (question.multiple) {
          this.selection = this.selection.includes(option.id)
            ? this.selection.filter((id) => id !== option.id)
            : [...this.selection, option.id];
        } else {
          this.selection = [option.id];
        }
      },

      optionClass(option) {
        const chosen = this.selection.includes(option.id);
        if (!this.revealed) {
          return chosen
            ? "border-brand-500 bg-brand-50 dark:border-brand-500 dark:bg-brand-950/50"
            : "border-ink-200 hover:border-brand-300 hover:bg-ink-50 dark:border-ink-700 dark:hover:border-brand-700 dark:hover:bg-ink-800/60";
        }
        if (option.is_correct) return "border-emerald-400 bg-emerald-50 dark:border-emerald-700 dark:bg-emerald-950/50";
        if (chosen) return "border-rose-400 bg-rose-50 dark:border-rose-700 dark:bg-rose-950/50";
        return "border-ink-200 opacity-70 dark:border-ink-700";
      },

      badgeClass(option) {
        const chosen = this.selection.includes(option.id);
        if (!this.revealed) {
          return chosen
            ? "border-brand-500 bg-brand-600 text-white"
            : "border-ink-300 text-ink-500 dark:border-ink-600 dark:text-ink-400";
        }
        if (option.is_correct) return "border-emerald-500 bg-emerald-500 text-white";
        if (chosen) return "border-rose-500 bg-rose-500 text-white";
        return "border-ink-300 text-ink-400 dark:border-ink-600";
      },

      resultOptionClass(entry, option) {
        if (option.is_correct) return "bg-emerald-50 text-emerald-900 dark:bg-emerald-950/50 dark:text-emerald-100";
        if (entry.selected.includes(option.id)) return "bg-rose-50 text-rose-900 dark:bg-rose-950/50 dark:text-rose-100";
        return "text-ink-600 dark:text-ink-300";
      },

      advance() {
        const question = this.currentQuestion;
        if (!question) return;

        if (this.config.mode === "instant" && !this.revealed) {
          this.answers[question.id] = this.selection.slice();
          this.lastCorrect = this.isCorrect(question, this.selection);
          this.revealed = true;
          return;
        }

        this.answers[question.id] = this.selection.slice();
        if (this.index === this.questions.length - 1) {
          this.finish();
          return;
        }
        this.index += 1;
        this.selection = this.answers[this.currentQuestion.id] || [];
        this.revealed = false;
      },

      async abort() {
        const confirmed = await confirmDialog({
          title: "Przerwać quiz?",
          message: "Wynik tej sesji nie zostanie zapisany.",
          confirmLabel: "Przerwij",
          danger: true,
        });
        if (!confirmed) return;
        window.clearInterval(this.timer);
        window.location.href = `/zestawy/${this.set.id}`;
      },

      finish() {
        window.clearInterval(this.timer);
        this.elapsed = Math.round((Date.now() - this.startedAt) / 1000);
        this.stage = "result";
        this.saveSession();
        window.scrollTo({ top: 0, behavior: "smooth" });
      },

      retry(onlyWrong) {
        const source = onlyWrong ? this.wrongQuestions.map((question) => this.findOriginal(question)) : this.set.questions;
        this.config.count = onlyWrong ? source.length : this.config.count;
        this.questions = this.buildQuestions(source);
        this.answers = {};
        this.index = 0;
        this.selection = [];
        this.revealed = false;
        this.sessionSaved = false;
        this.startedAt = Date.now();
        this.elapsed = 0;
        this.remaining = this.config.minutes * 60;
        this.stage = "run";
        this.startTimer();
      },

      findOriginal(question) {
        return this.set.questions.find((item) => item.id === question.id) || question;
      },

      async saveSession() {
        if (this.sessionSaved) return;
        this.sessionSaved = true;
        try {
          await api.post("/api/study/sessions", {
            set_id: this.set.id,
            mode: "quiz",
            score: this.score,
            total: this.questions.length,
            duration_seconds: Math.min(this.elapsed, 86400),
          });
        } catch (error) {
          toast("Nie zapisano statystyk tej sesji.", "warning", 2500);
        }
      },
    };
  }

  window.quizRunner = quizRunner;
})();
