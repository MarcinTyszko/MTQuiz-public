/** Tryb nauki fiszkami: obrót karty, nawigacja, gesty dotykowe, statystyki sesji. */
(function () {
  "use strict";
  const { api, toast, shuffle, formatDuration, readJsonScript, bindSwipe, createSessionTracker } = window.MTQuiz;

  function flashcardRunner() {
    return {
      set: { id: 0, title: "", cards: [] },
      queue: [],
      index: 0,
      flipped: false,
      hintVisible: false,
      shuffled: false,
      onlyStarred: false,
      known: [],
      review: [],
      // Fiszki przerobione w tej sesji (odwrócone albo ocenione) — każda daje jeden punkt.
      reviewed: [],
      tracker: null,
      finished: false,
      startedAt: Date.now(),
      elapsed: 0,
      timer: null,
      sessionSaved: false,

      init() {
        const data = readJsonScript("dane-zestawu");
        if (!data) {
          toast("Nie udało się wczytać zestawu.", "error");
          return;
        }
        this.set = data;
        this.queue = data.cards.slice();
        this.tracker = this.newTracker();
        // Postęp zapisuje się po każdej fiszce; przy zamykaniu karty dosyłamy ostatni stan.
        window.addEventListener("pagehide", () => this.tracker.flushOnExit());
        document.addEventListener("visibilitychange", () => {
          if (document.visibilityState === "hidden") this.tracker.flushOnExit();
        });
        this.startTimer();
        this.bindKeyboard();
        this.$nextTick(() => this.bindGestures());
      },

      get current() {
        return this.queue[this.index] || null;
      },

      get starredCount() {
        return this.set.cards.filter((card) => card.starred).length;
      },

      get progress() {
        if (!this.queue.length) return 0;
        return Math.round(((this.index + (this.finished ? 1 : 0)) / this.queue.length) * 100);
      },

      get elapsedLabel() {
        return formatDuration(this.elapsed);
      },

      startTimer() {
        this.timer = window.setInterval(() => {
          if (!this.finished) this.elapsed = Math.round((Date.now() - this.startedAt) / 1000);
        }, 1000);
      },

      bindGestures() {
        bindSwipe(this.$refs.scene, {
          onLeft: () => this.next(),
          onRight: () => this.previous(),
        });
      },

      bindKeyboard() {
        document.addEventListener("keydown", (event) => {
          if (this.finished) return;
          const tag = (event.target.tagName || "").toLowerCase();
          if (tag === "input" || tag === "textarea" || tag === "select") return;

          switch (event.key) {
            case " ":
            case "Spacebar":
              event.preventDefault();
              this.flip();
              break;
            case "ArrowRight":
              event.preventDefault();
              this.next();
              break;
            case "ArrowLeft":
              event.preventDefault();
              this.previous();
              break;
            case "s":
            case "S":
              this.toggleStar();
              break;
            case "1":
              this.mark("review");
              break;
            case "2":
              this.mark("known");
              break;
            default:
              break;
          }
        });
      },

      flip() {
        this.flipped = !this.flipped;
        if (this.flipped) this.countReviewed();
      },

      newTracker() {
        this.sessionSaved = false;
        return createSessionTracker({
          setId: this.set.id,
          mode: "flashcards",
          onSaved: () => {
            this.sessionSaved = true;
          },
        });
      },

      /**
       * Zalicza bieżącą fiszkę jako przerobioną (raz na sesję) i zapisuje postęp.
       * Samo przewinięcie bez odwrócenia ani oceny nie jest nauką i nie daje punktu.
       */
      countReviewed() {
        const card = this.current;
        if (card && !this.reviewed.includes(card.id)) this.reviewed.push(card.id);
        this.syncProgress();
      },

      syncProgress() {
        if (!this.reviewed.length) return;
        this.tracker.update({
          score: this.known.length,
          total: this.reviewed.length,
          duration: (Date.now() - this.startedAt) / 1000,
        });
      },

      resetCardState() {
        this.flipped = false;
        this.hintVisible = false;
      },

      next() {
        if (this.index >= this.queue.length - 1) {
          this.finish();
          return;
        }
        this.index += 1;
        this.resetCardState();
      },

      previous() {
        if (this.index === 0) return;
        this.index -= 1;
        this.resetCardState();
      },

      /** Oznacza bieżącą fiszkę jako opanowaną lub do powtórki i przechodzi dalej. */
      mark(bucket) {
        const card = this.current;
        if (!card) return;
        this.known = this.known.filter((id) => id !== card.id);
        this.review = this.review.filter((id) => id !== card.id);
        if (bucket === "known") this.known.push(card.id);
        else this.review.push(card.id);
        this.countReviewed();
        this.next();
      },

      async toggleStar() {
        const card = this.current;
        if (!card) return;
        const next = !card.starred;
        card.starred = next;
        const source = this.set.cards.find((item) => item.id === card.id);
        if (source) source.starred = next;
        try {
          await api.post(`/api/cards/${card.id}/star`, {});
        } catch (error) {
          card.starred = !next;
          if (source) source.starred = !next;
          toast(error.message || "Nie udało się zapisać oznaczenia.", "error");
        }
      },

      toggleShuffle() {
        this.shuffled = !this.shuffled;
        this.rebuild();
      },

      /** Przebudowuje kolejkę po zmianie filtrów lub kolejności. */
      rebuild() {
        const source = this.onlyStarred ? this.set.cards.filter((card) => card.starred) : this.set.cards.slice();
        if (!source.length) {
          this.onlyStarred = false;
          toast("Brak fiszek oznaczonych jako trudne.", "warning");
          return;
        }
        this.queue = this.shuffled ? shuffle(source) : source;
        this.index = 0;
        this.finished = false;
        this.resetCardState();
      },

      restart(onlyReview) {
        if (onlyReview) {
          const ids = new Set(this.review);
          const source = this.set.cards.filter((card) => ids.has(card.id));
          this.queue = this.shuffled ? shuffle(source) : source;
        } else {
          this.rebuildQueueFromSet();
        }
        this.index = 0;
        this.known = [];
        this.review = [];
        this.reviewed = [];
        this.finished = false;
        // Każde powtórzenie to osobna sesja nauki.
        this.tracker = this.newTracker();
        this.startedAt = Date.now();
        this.elapsed = 0;
        this.resetCardState();
      },

      rebuildQueueFromSet() {
        const source = this.onlyStarred ? this.set.cards.filter((card) => card.starred) : this.set.cards.slice();
        this.queue = this.shuffled ? shuffle(source) : source;
      },

      finish() {
        this.finished = true;
        this.elapsed = Math.round((Date.now() - this.startedAt) / 1000);
        this.syncProgress();
      },
    };
  }

  window.flashcardRunner = flashcardRunner;
})();
