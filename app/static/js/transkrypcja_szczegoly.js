/** Strona wyniku transkrypcji: podgląd, kopiowanie, pobieranie i przekazanie do generatora. */
(function () {
  "use strict";
  const { api, toast, confirmDialog, copyToClipboard, readJsonScript } = window.MTQuiz;

  const KLUCZ_MATERIALU = "mtquiz-material-zrodlowy";

  function szczegolyTranskrypcji() {
    return {
      dane: { id: 0, title: "", status: "queued", progress: 0, segments: [], text: "" },
      widok: "segmenty",
      edycjaTytulu: false,
      nowyTytul: "",
      odswiezanie: null,

      init() {
        const wczytane = readJsonScript("dane-transkrypcji");
        if (!wczytane) {
          toast("Nie udało się wczytać transkrypcji.", "error");
          return;
        }
        this.dane = wczytane;
        this.nowyTytul = wczytane.title;
        if (!this.gotowa) this.sledzPostep();
      },

      get gotowa() {
        return this.dane.status === "done";
      },
      get wTrakcie() {
        return this.dane.status === "queued" || this.dane.status === "running";
      },
      get liczbaSlow() {
        return this.dane.word_count || 0;
      },
      get samTekst() {
        if (this.dane.segments && this.dane.segments.length) {
          return this.dane.segments.map((s) => (s.tekst || s.text || "").trim()).filter(Boolean).join(" ");
        }
        return (this.dane.text || "").replace(/^\[[^\]]+\]\s*/gm, "");
      },

      /** Dopóki trwa przetwarzanie, odświeża stan i przeładowuje stronę po zakończeniu. */
      sledzPostep() {
        window.clearInterval(this.odswiezanie);
        this.odswiezanie = window.setInterval(async () => {
          try {
            const swieze = await api.get(`/api/transkrypcje/${this.dane.id}`);
            const bylWTrakcie = this.wTrakcie;
            this.dane = swieze;
            if (bylWTrakcie && !this.wTrakcie) {
              window.clearInterval(this.odswiezanie);
              if (this.gotowa) {
                toast("Transkrypcja gotowa.", "success");
                window.setTimeout(() => window.location.reload(), 800);
              }
            }
          } catch (error) {
            /* przejściowy błąd sieci — spróbujemy ponownie przy następnym odpytaniu */
          }
        }, 3000);
      },

      czas(sekundy) {
        const total = Math.max(0, Math.round(sekundy || 0));
        const g = Math.floor(total / 3600);
        const m = Math.floor((total % 3600) / 60);
        const s = total % 60;
        const pad = (v) => String(v).padStart(2, "0");
        return g ? `${pad(g)}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
      },

      async kopiujZeZnacznikami() {
        await copyToClipboard(this.dane.text, { successMessage: "Transkrypcja ze znacznikami czasu skopiowana." });
      },

      async kopiujSamTekst() {
        await copyToClipboard(this.samTekst, { successMessage: "Sam tekst transkrypcji skopiowany." });
      },

      pobierz(format) {
        window.location.href = `/api/transkrypcje/${this.dane.id}/pobierz?format=${format}`;
      },

      /** Przekazuje transkrypcję do generatora promptu przez pamięć sesji. */
      doGeneratora() {
        try {
          sessionStorage.setItem(
            KLUCZ_MATERIALU,
            JSON.stringify({ tytul: this.dane.title, tekst: this.samTekst, zrodlo: "transkrypcja" })
          );
        } catch (error) {
          toast("Przeglądarka zablokowała pamięć sesji — skopiuj tekst ręcznie.", "error");
          return;
        }
        window.location.href = "/generator-promptu";
      },

      async zapiszTytul() {
        const tytul = this.nowyTytul.trim();
        if (!tytul || tytul === this.dane.title) {
          this.edycjaTytulu = false;
          this.nowyTytul = this.dane.title;
          return;
        }
        try {
          const wynik = await api.patch(`/api/transkrypcje/${this.dane.id}`, { title: tytul });
          this.dane.title = wynik.title;
          document.title = `${wynik.title} — transkrypcja`;
          this.edycjaTytulu = false;
          toast("Nazwa została zmieniona.", "success", 2000);
        } catch (error) {
          toast(error.message || "Nie udało się zmienić nazwy.", "error");
        }
      },

      async usunNagranie() {
        const potwierdzone = await confirmDialog({
          title: "Usunąć plik nagrania?",
          message:
            "Transkrypcja zostanie zachowana, skasowany będzie tylko plik audio. " +
            "Późniejsze ponowienie transkrypcji nie będzie możliwe bez wysłania pliku od nowa.",
          confirmLabel: "Usuń nagranie",
          danger: true,
        });
        if (!potwierdzone) return;
        try {
          const wynik = await api.delete(`/api/transkrypcje/${this.dane.id}/nagranie`);
          this.dane.has_audio = false;
          toast(wynik.message, "success");
        } catch (error) {
          toast(error.message || "Nie udało się usunąć nagrania.", "error");
        }
      },

      async ponow() {
        try {
          const wynik = await api.post(`/api/transkrypcje/${this.dane.id}/ponow`, {});
          Object.assign(this.dane, wynik);
          toast("Zadanie wróciło do kolejki.", "success");
          this.sledzPostep();
        } catch (error) {
          toast(error.message || "Nie udało się ponowić zadania.", "error");
        }
      },

      async usun() {
        const potwierdzone = await confirmDialog({
          title: "Usunąć transkrypcję?",
          message: `„${this.dane.title}” zostanie skasowana razem z nagraniem. Operacji nie można cofnąć.`,
          confirmLabel: "Usuń",
          danger: true,
        });
        if (!potwierdzone) return;
        try {
          await api.delete(`/api/transkrypcje/${this.dane.id}`);
          window.location.href = "/transkrypcje";
        } catch (error) {
          toast(error.message || "Nie udało się usunąć transkrypcji.", "error");
        }
      },
    };
  }

  window.szczegolyTranskrypcji = szczegolyTranskrypcji;
  window.MTQUIZ_KLUCZ_MATERIALU = KLUCZ_MATERIALU;
})();
