/** Lista transkrypcji: wysyłka nagrania, śledzenie postępu, operacje na zadaniach. */
(function () {
  "use strict";
  const { api, toast, confirmDialog } = window.MTQuiz;

  const STATUSY = {
    queued: { etykieta: "W kolejce", klasa: "badge-neutral" },
    running: { etykieta: "Przetwarzanie", klasa: "badge-brand" },
    done: { etykieta: "Gotowe", klasa: "badge-success" },
    error: { etykieta: "Błąd", klasa: "badge-danger" },
  };

  const JEZYKI = [
    { kod: "pl", nazwa: "polski" },
    { kod: "en", nazwa: "angielski" },
    { kod: "de", nazwa: "niemiecki" },
    { kod: "es", nazwa: "hiszpański" },
    { kod: "fr", nazwa: "francuski" },
    { kod: "it", nazwa: "włoski" },
    { kod: "uk", nazwa: "ukraiński" },
    { kod: "", nazwa: "wykryj automatycznie" },
  ];

  function listaTranskrypcji() {
    return {
      pozycje: [],
      worker: { dostepny: false, opis: "Sprawdzanie…" },
      jezyki: JEZYKI,
      // Formularz wysyłki
      plik: null,
      nazwaPliku: "",
      tytul: "",
      jezyk: "pl",
      dragging: false,
      wysylanie: false,
      postepWysylki: 0,
      ladowanie: true,
      odswiezanie: null,

      async init() {
        await Promise.all([this.pobierz(), this.sprawdzWorkera()]);
        this.ladowanie = false;
        this.zaplanujOdswiezanie();
        window.setInterval(() => this.sprawdzWorkera(), 30000);
      },

      get trwajace() {
        return this.pozycje.filter((p) => p.status === "queued" || p.status === "running").length;
      },

      /** Odpytuje serwer tylko wtedy, gdy coś jest w toku. */
      zaplanujOdswiezanie() {
        window.clearInterval(this.odswiezanie);
        this.odswiezanie = window.setInterval(() => {
          if (this.trwajace > 0) this.pobierz();
        }, 3000);
      },

      async pobierz() {
        try {
          this.pozycje = await api.get("/api/transkrypcje");
        } catch (error) {
          toast(error.message || "Nie udało się pobrać listy transkrypcji.", "error");
        }
      },

      async sprawdzWorkera() {
        try {
          this.worker = await api.get("/api/transkrypcje/worker");
        } catch (error) {
          this.worker = { dostepny: false, opis: "Nie udało się sprawdzić stanu procesu." };
        }
      },

      status(pozycja) {
        return STATUSY[pozycja.status] || STATUSY.queued;
      },

      czas(sekundy) {
        const total = Math.max(0, Math.round(sekundy || 0));
        const g = Math.floor(total / 3600);
        const m = Math.floor((total % 3600) / 60);
        const s = total % 60;
        const pad = (v) => String(v).padStart(2, "0");
        return g ? `${pad(g)}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
      },

      rozmiar(bajty) {
        const mb = (bajty || 0) / 1024 / 1024;
        return mb >= 1 ? `${mb.toFixed(1)} MB` : `${Math.max(1, Math.round((bajty || 0) / 1024))} KB`;
      },

      data(wartosc) {
        if (!wartosc) return "—";
        try {
          return new Date(wartosc).toLocaleString("pl-PL", { dateStyle: "short", timeStyle: "short" });
        } catch (error) {
          return wartosc;
        }
      },

      onPlik(event) {
        const [plik] = event.target.files || [];
        if (plik) this.przyjmij(plik);
      },

      onDrop(event) {
        this.dragging = false;
        const [plik] = event.dataTransfer.files || [];
        if (plik) this.przyjmij(plik);
      },

      przyjmij(plik) {
        this.plik = plik;
        this.nazwaPliku = `${plik.name} (${this.rozmiar(plik.size)})`;
        if (!this.tytul.trim()) {
          this.tytul = plik.name.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ").trim();
        }
      },

      wyczysc() {
        this.plik = null;
        this.nazwaPliku = "";
        this.tytul = "";
        this.postepWysylki = 0;
      },

      /** Wysyłka przez XMLHttpRequest — tylko ona daje postęp przesyłania dużego pliku. */
      wyslij() {
        if (!this.plik || this.wysylanie) return;

        const dane = new FormData();
        dane.append("file", this.plik);
        dane.append("title", this.tytul.trim());
        dane.append("language", this.jezyk);

        this.wysylanie = true;
        this.postepWysylki = 0;

        const zadanie = new XMLHttpRequest();
        zadanie.open("POST", "/api/transkrypcje");
        zadanie.upload.addEventListener("progress", (event) => {
          if (event.lengthComputable) {
            this.postepWysylki = Math.round((event.loaded / event.total) * 100);
          }
        });
        zadanie.addEventListener("load", () => {
          this.wysylanie = false;
          if (zadanie.status >= 200 && zadanie.status < 300) {
            this.wyczysc();
            toast("Nagranie trafiło do kolejki.", "success");
            this.pobierz();
            if (!this.worker.dostepny) {
              toast("Uruchom proces transkrybujący, inaczej nagranie zostanie w kolejce.", "warning", 7000);
            }
          } else {
            let detal = `Błąd ${zadanie.status}`;
            try {
              detal = JSON.parse(zadanie.responseText).detail || detal;
            } catch (error) {
              /* odpowiedź bez treści JSON */
            }
            toast(detal, "error", 7000);
          }
        });
        zadanie.addEventListener("error", () => {
          this.wysylanie = false;
          toast("Przesyłanie nagrania nie powiodło się.", "error");
        });
        zadanie.send(dane);
      },

      async ponow(pozycja) {
        try {
          const wynik = await api.post(`/api/transkrypcje/${pozycja.id}/ponow`, {});
          Object.assign(pozycja, wynik);
          toast("Zadanie wróciło do kolejki.", "success");
        } catch (error) {
          toast(error.message || "Nie udało się ponowić zadania.", "error");
        }
      },

      async usun(pozycja) {
        const potwierdzone = await confirmDialog({
          title: "Usunąć transkrypcję?",
          message: `„${pozycja.title}” zostanie skasowana razem z nagraniem źródłowym. Operacji nie można cofnąć.`,
          confirmLabel: "Usuń",
          danger: true,
        });
        if (!potwierdzone) return;
        try {
          await api.delete(`/api/transkrypcje/${pozycja.id}`);
          this.pozycje = this.pozycje.filter((p) => p.id !== pozycja.id);
          toast("Transkrypcja została usunięta.", "success");
        } catch (error) {
          toast(error.message || "Nie udało się usunąć transkrypcji.", "error");
        }
      },
    };
  }

  window.listaTranskrypcji = listaTranskrypcji;
})();
