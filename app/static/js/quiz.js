/** Silnik quizu: tryb nauki i egzaminu, limit czasu, punktacja i omówienie. */
(function () {
  "use strict";
  const { toast, shuffle, formatDuration, readJsonScript, confirmDialog, createSessionTracker, isTypingTarget } =
    window.MTQuiz;

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
      tracker: null,
      // Zakończenie przed ostatnim pytaniem: wynik obejmuje tylko rozwiązane pytania.
      endedEarly: false,
      plannedCount: 0,
      remainingQuestions: [],

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
        // Postęp zapisuje się po każdym pytaniu; przy zamykaniu karty dosyłamy ostatni stan.
        const flush = () => this.tracker && this.tracker.flushOnExit();
        window.addEventListener("pagehide", flush);
        document.addEventListener("visibilitychange", () => {
          if (document.visibilityState === "hidden") flush();
        });
        document.addEventListener("keydown", (event) => this.onKeydown(event));
      },

      /** Skróty: 1–9 albo A–J wybiera wariant, Enter sprawdza i przechodzi dalej. */
      onKeydown(event) {
        if (this.stage !== "run" || event.defaultPrevented || event.repeat) return;
        if (event.ctrlKey || event.metaKey || event.altKey) return;
        if (isTypingTarget(event.target) || document.querySelector('[role="dialog"][aria-modal="true"]')) return;
        const question = this.currentQuestion;
        if (!question) return;

        if (event.key === "Enter") {
          // Enter na innym przycisku (np. „Zakończ teraz”) zachowuje swoje działanie.
          const target = event.target;
          if (target && target !== document.body && !target.closest("[data-quiz-option]")) return;
          event.preventDefault();
          if (this.canAdvance) this.advance();
          return;
        }

        const key = event.key.toUpperCase();
        let position = -1;
        if (/^[1-9]$/.test(key)) position = Number(key) - 1;
        else if (/^[A-J]$/.test(key)) position = key.charCodeAt(0) - 65;
        const option = question.options[position];
        if (!option) return;
        event.preventDefault();
        this.choose(option);
      },

      /** Liczba pytań, na które padła odpowiedź w bieżącym podejściu. */
      get answeredCount() {
        return this.questions.filter((question) => this.answers[question.id]).length;
      },

      get answeredCorrect() {
        return this.questions.filter((question) => {
          const selected = this.answers[question.id];
          return selected && this.isCorrect(question, selected);
        }).length;
      },

      newTracker() {
        this.sessionSaved = false;
        return createSessionTracker({
          setId: this.set.id,
          mode: "quiz",
          onSaved: () => {
            this.sessionSaved = true;
          },
        });
      },

      /** Każde rozwiązane pytanie to punkt — zapisywany od razu, nie dopiero na końcu. */
      syncProgress() {
        if (!this.tracker) return;
        this.tracker.update({
          score: this.answeredCorrect,
          total: this.answeredCount,
          duration: (Date.now() - this.startedAt) / 1000,
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
        this.begin(this.set.questions);
      },

      /** Rozpoczyna nowe podejście — każde jest osobną sesją w statystykach. */
      begin(source) {
        this.questions = this.buildQuestions(source);
        this.answers = {};
        this.index = 0;
        this.selection = [];
        this.revealed = false;
        this.endedEarly = false;
        this.plannedCount = 0;
        this.remainingQuestions = [];
        this.tracker = this.newTracker();
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
          this.syncProgress();
          return;
        }

        this.answers[question.id] = this.selection.slice();
        this.syncProgress();
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
          message:
            "Rozwiązane pytania są już zapisane w statystykach. Omówienia błędów nie zobaczysz — " +
            "jeżeli go potrzebujesz, wybierz „Zakończ teraz”.",
          confirmLabel: "Przerwij",
          danger: true,
        });
        if (!confirmed) return;
        window.clearInterval(this.timer);
        if (this.tracker) await this.tracker.flush();
        window.location.href = `/zestawy/${this.set.id}`;
      },

      finish() {
        window.clearInterval(this.timer);
        this.elapsed = Math.round((Date.now() - this.startedAt) / 1000);
        this.stage = "result";
        this.syncProgress();
        window.scrollTo({ top: 0, behavior: "smooth" });
      },

      /**
       * Kończy quiz przed ostatnim pytaniem. Wynik i omówienie obejmują tylko
       * rozwiązane pytania; pozostałe można rozwiązać później jednym przyciskiem.
       */
      async finishEarly() {
        const question = this.currentQuestion;
        // Zaznaczona, choć jeszcze niezatwierdzona odpowiedź też się liczy.
        if (question && this.selection.length && !this.answers[question.id]) {
          this.answers[question.id] = this.selection.slice();
        }
        const answered = this.questions.filter((item) => this.answers[item.id]);
        if (!answered.length) {
          toast("Odpowiedz na co najmniej jedno pytanie, aby zobaczyć wynik.", "info");
          return;
        }
        const left = this.questions.length - answered.length;
        if (left > 0) {
          const confirmed = await confirmDialog({
            title: "Zakończyć quiz teraz?",
            message:
              `Wynik i omówienie obejmą ${answered.length} rozwiązanych pytań. ` +
              `Pozostałe ${left} możesz rozwiązać później przyciskiem na ekranie wyniku.`,
            confirmLabel: "Zakończ i pokaż wyniki",
          });
          if (!confirmed) return;
        }

        this.plannedCount = this.questions.length;
        this.remainingQuestions = this.questions
          .filter((item) => !this.answers[item.id])
          .map((item) => this.findOriginal(item));
        this.endedEarly = left > 0;
        this.questions = answered;
        this.finish();
      },

      retry(onlyWrong) {
        const source = onlyWrong ? this.wrongQuestions.map((question) => this.findOriginal(question)) : this.set.questions;
        this.config.count = onlyWrong ? source.length : this.config.count;
        this.begin(source);
      },

      /** Wraca do pytań pominiętych po wcześniejszym zakończeniu quizu. */
      retryRemaining() {
        const source = this.remainingQuestions.slice();
        if (!source.length) return;
        this.config.count = source.length;
        this.begin(source);
      },

      findOriginal(question) {
        return this.set.questions.find((item) => item.id === question.id) || question;
      },
    };
  }

  window.quizRunner = quizRunner;
})();
