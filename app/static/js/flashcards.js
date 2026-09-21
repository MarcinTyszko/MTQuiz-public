/** Tryb nauki fiszkami: obrót karty, nawigacja, gesty dotykowe, statystyki sesji. */
(function () {
  "use strict";
  const { api, toast, shuffle, formatDuration, readJsonScript, bindSwipe } = window.MedFiszki;

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
        this.sessionSaved = false;
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
        this.finished = false;
        this.sessionSaved = false;
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
        this.saveSession();
      },

      async saveSession() {
        if (this.sessionSaved) return;
        this.sessionSaved = true;
        try {
          await api.post("/api/study/sessions", {
            set_id: this.set.id,
            mode: "flashcards",
            score: this.known.length,
            total: this.queue.length,
            duration_seconds: Math.min(this.elapsed, 86400),
          });
        } catch (error) {
          // Zapis statystyk nie może przerwać nauki — informujemy dyskretnie.
          toast("Nie zapisano statystyk tej sesji.", "warning", 2500);
        }
      },
    };
  }

  window.flashcardRunner = flashcardRunner;
})();
