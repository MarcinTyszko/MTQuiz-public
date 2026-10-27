/**
 * Pomodoro: minutnik działający na wszystkich stronach, powiadomienia, dźwięki tła.
 *
 * Aplikacja składa się z osobnych stron, więc minutnik nie może żyć w jednej
 * z nich. Stan to kilka znaczników czasu (koniec fazy, pozostały czas), z których
 * każda strona w dowolnej chwili odtwarza, co się dzieje — także po godzinie
 * nieobecności: fazy, które minęły, zostają rozliczone i zapisane w statystykach.
 *
 * Stan żyje w trzech miejscach, uzgadnianych numerem rewizji:
 * - localStorage — natychmiastowy start strony i synchronizacja kart,
 * - serwer — to samo na komputerze i telefonie oraz plan powiadomień push,
 * - magazyn Alpine.js — reaktywny widok dla pływającego minutnika i strony Pomodoro.
 */
(function () {
  "use strict";
  const { api, toast, readJsonScript, isTypingTarget } = window.MTQuiz;

  /** Przełączniki w „Moje konto” — działają także przy wyłączonym Pomodoro. */
  window.ustawieniaPomodoro = function ustawieniaPomodoro(poczatkowe) {
    return {
      prefs: { ...poczatkowe },
      zapisywanie: false,
      async przelacz(klucz) {
        this.prefs[klucz] = !this.prefs[klucz];
        this.zapisywanie = true;
        try {
          await api.patch("/api/preferences", { [klucz]: this.prefs[klucz] });
          toast("Zapisano.", "success", 2000);
          // Menu i minutnik powstają po stronie serwera — przeładowanie pokazuje efekt od razu.
          window.setTimeout(() => window.location.reload(), 400);
        } catch (error) {
          this.prefs[klucz] = !this.prefs[klucz];
          toast(error.message || "Nie udało się zapisać ustawienia.", "error");
        } finally {
          this.zapisywanie = false;
        }
      },
    };
  };

  const boot = readJsonScript("pomodoro-bootstrap");
  if (!boot || !boot.enabled) return;

  const KLUCZ_STANU = "mtquiz-pomodoro-stan";
  const KLUCZ_KOLEJKI = "mtquiz-pomodoro-kolejka";
  const KLUCZ_ZWINIECIA = "mtquiz-pomodoro-zwiniety";
  const KLUCZ_DZWIEKOW = "mtquiz-dzwieki-tla";
  const TAG_POWIADOMIENIA = "mtquiz-pomodoro";
  const IKONA = "/static/icons/icon-192.png";

  const FAZY = {
    focus: { nazwa: "Skupienie", krotko: "Skupienie" },
    short_break: { nazwa: "Krótka przerwa", krotko: "Przerwa" },
    long_break: { nazwa: "Długa przerwa", krotko: "Długa przerwa" },
  };

  /* ----------------------------------------------------------------------- */
  /* Narzędzia                                                                */
  /* ----------------------------------------------------------------------- */
  function czytaj(klucz, domyslna) {
    try {
      const surowe = localStorage.getItem(klucz);
      return surowe ? JSON.parse(surowe) : domyslna;
    } catch (error) {
      return domyslna;
    }
  }

  function zapisz(klucz, wartosc) {
    try {
      localStorage.setItem(klucz, JSON.stringify(wartosc));
    } catch (error) {
      /* Tryb prywatny — minutnik działa dalej, tylko bez pamięci między kartami. */
    }
  }

  function zegar(sekundy) {
    const calosc = Math.max(0, Math.ceil(sekundy));
    const godziny = Math.floor(calosc / 3600);
    const minuty = Math.floor((calosc % 3600) / 60);
    const sek = String(calosc % 60).padStart(2, "0");
    return godziny ? `${godziny}:${String(minuty).padStart(2, "0")}:${sek}` : `${String(minuty).padStart(2, "0")}:${sek}`;
  }

  /** Czas trwania, zwięźle: „45 s”, „25 min”, „2 h 5 min”. */
  function czasTrwania(sekundy) {
    const calosc = Math.max(0, Math.round(sekundy || 0));
    if (calosc < 60) return `${calosc} s`;
    const minuty = Math.round(calosc / 60);
    if (minuty < 60) return `${minuty} min`;
    const godziny = Math.floor(minuty / 60);
    const reszta = minuty % 60;
    return reszta ? `${godziny} h ${reszta} min` : `${godziny} h`;
  }

  function zbudujPlan(config) {
    const plan = [];
    for (let runda = 1; runda <= config.rounds; runda += 1) {
      plan.push({ type: "focus", seconds: config.focus_minutes * 60 });
      if (runda < config.rounds) plan.push({ type: "short_break", seconds: config.short_break_minutes * 60 });
      else if (config.long_break_minutes > 0) plan.push({ type: "long_break", seconds: config.long_break_minutes * 60 });
    }
    return plan;
  }

  function pustyStan() {
    return { status: "idle", plan: [], index: 0 };
  }

  const jestIOS = /iP(hone|ad|od)/.test(navigator.userAgent) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  const jestZainstalowana = window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;

  /* ----------------------------------------------------------------------- */
  /* Sygnał dźwiękowy końca fazy                                              */
  /* ----------------------------------------------------------------------- */
  let kontekstAudio = null;
  function audio() {
    if (!kontekstAudio) {
      const Konstruktor = window.AudioContext || window.webkitAudioContext;
      if (!Konstruktor) return null;
      kontekstAudio = new Konstruktor();
    }
    if (kontekstAudio.state === "suspended") kontekstAudio.resume().catch(() => {});
    return kontekstAudio;
  }
  // Przeglądarki odblokowują dźwięk dopiero po geście użytkownika na stronie.
  ["pointerdown", "keydown"].forEach((zdarzenie) =>
    document.addEventListener(zdarzenie, () => audio(), { once: true, capture: true }),
  );

  /** Trzy miękkie dźwięki: w górę na koniec przerwy, w dół na koniec skupienia. */
  function zagrajSygnal(rosnaco) {
    const ctx = audio();
    if (!ctx || ctx.state !== "running") return;
    const nuty = rosnaco ? [659.25, 783.99, 1046.5] : [1046.5, 783.99, 659.25];
    nuty.forEach((czestotliwosc, numer) => {
      const start = ctx.currentTime + numer * 0.18;
      const oscylator = ctx.createOscillator();
      const wzmocnienie = ctx.createGain();
      oscylator.type = "sine";
      oscylator.frequency.value = czestotliwosc;
      wzmocnienie.gain.setValueAtTime(0, start);
      wzmocnienie.gain.linearRampToValueAtTime(0.22, start + 0.02);
      wzmocnienie.gain.exponentialRampToValueAtTime(0.0001, start + 0.9);
      oscylator.connect(wzmocnienie).connect(ctx.destination);
      oscylator.start(start);
      oscylator.stop(start + 1);
    });
  }

  /* ----------------------------------------------------------------------- */
  /* Powiadomienia systemowe i push                                           */
  /* ----------------------------------------------------------------------- */
  function kluczSerwera(base64) {
    const dopelnienie = "=".repeat((4 - (base64.length % 4)) % 4);
    const surowe = atob((base64 + dopelnienie).replace(/-/g, "+").replace(/_/g, "/"));
    return Uint8Array.from(surowe, (znak) => znak.charCodeAt(0));
  }

  const powiadomienia = {
    wsparcie: "brak", // push | lokalne | ios-instalacja | https | brak
    zgoda: "default",
    subskrypcja: false,
    pracuje: false,

    async przygotuj() {
      const maNotification = "Notification" in window;
      const maPush = "serviceWorker" in navigator && "PushManager" in window;
      if (!window.isSecureContext) this.wsparcie = "https";
      else if (maNotification && maPush) this.wsparcie = "push";
      else if (jestIOS && !jestZainstalowana) this.wsparcie = "ios-instalacja";
      else if (maNotification) this.wsparcie = "lokalne";
      this.zgoda = maNotification ? Notification.permission : "default";
      if ("serviceWorker" in navigator && window.isSecureContext) {
        try {
          const rejestracja = await navigator.serviceWorker.register("/sw.js", { scope: "/" });
          if (this.wsparcie === "push" && rejestracja.pushManager) {
            const subskrypcja = await rejestracja.pushManager.getSubscription();
            this.subskrypcja = Boolean(subskrypcja);
          }
        } catch (error) {
          /* Brak service workera — zostają powiadomienia z otwartej karty. */
        }
      }
    },

    get aktywne() {
      return this.zgoda === "granted";
    },

    async wlacz() {
      if (!("Notification" in window)) {
        toast(
          jestIOS
            ? "Na iPhonie powiadomienia działają po dodaniu MTQuiz do ekranu początkowego (Udostępnij → Do ekranu początkowego)."
            : "Ta przeglądarka nie obsługuje powiadomień.",
          "warning",
          7000,
        );
        return;
      }
      this.pracuje = true;
      try {
        this.zgoda = await Notification.requestPermission();
        if (this.zgoda !== "granted") {
          toast("Bez zgody przeglądarki minutnik da znać tylko dźwiękiem i komunikatem na stronie.", "warning", 6000);
          return;
        }
        if (this.wsparcie === "push") {
          const rejestracja = await navigator.serviceWorker.ready;
          let subskrypcja = await rejestracja.pushManager.getSubscription();
          if (!subskrypcja) {
            subskrypcja = await rejestracja.pushManager.subscribe({
              userVisibleOnly: true,
              applicationServerKey: kluczSerwera(boot.vapidKey),
            });
          }
          await api.post("/api/push/subscriptions", subskrypcja.toJSON());
          this.subskrypcja = true;
          // Plan powiadomień trzeba odświeżyć, jeżeli seria już trwa.
          silnik().wyslij();
        }
        toast("Powiadomienia włączone — dostaniesz znać o końcu każdej fazy.", "success", 3500);
      } catch (error) {
        toast(error.message || "Nie udało się włączyć powiadomień.", "error", 6000);
      } finally {
        this.pracuje = false;
      }
    },

    async wylacz() {
      this.pracuje = true;
      try {
        const rejestracja = await navigator.serviceWorker.getRegistration();
        const subskrypcja = rejestracja && (await rejestracja.pushManager.getSubscription());
        if (subskrypcja) {
          await api.delete("/api/push/subscriptions", { endpoint: subskrypcja.endpoint });
          await subskrypcja.unsubscribe();
        }
        this.subskrypcja = false;
        toast("Powiadomienia push wyłączone na tym urządzeniu.", "info", 3000);
      } catch (error) {
        toast(error.message || "Nie udało się wyłączyć powiadomień.", "error");
      } finally {
        this.pracuje = false;
      }
    },

    async testuj() {
      if (this.subskrypcja) {
        try {
          const wynik = await api.post("/api/push/test", {});
          toast(wynik.message, "success", 3000);
        } catch (error) {
          toast(error.message, "error", 6000);
        }
        return;
      }
      await this.pokaz("MTQuiz · Pomodoro", "Powiadomienia działają — tak zabrzmi koniec fazy.", true);
    },

    /** Powiadomienie z otwartej karty — gdy urządzenie nie ma subskrypcji push. */
    async pokaz(tytul, tresc, wymus = false) {
      if (!("Notification" in window) || Notification.permission !== "granted") return;
      // Push z serwera przyjdzie i tak — dwa identyczne powiadomienia tylko przeszkadzają.
      if (this.subskrypcja && !wymus) return;
      const opcje = { body: tresc, tag: TAG_POWIADOMIENIA, icon: IKONA, badge: "/static/icons/badge-96.png", data: { url: "/pomodoro" } };
      try {
        const rejestracja = "serviceWorker" in navigator ? await navigator.serviceWorker.getRegistration() : null;
        if (rejestracja) await rejestracja.showNotification(tytul, { ...opcje, renotify: true });
        else new Notification(tytul, opcje);
      } catch (error) {
        /* Część przeglądarek mobilnych pozwala tylko na powiadomienia z service workera. */
      }
    },
  };

  /* ----------------------------------------------------------------------- */
  /* Dźwięki tła: szum i częstotliwości                                       */
  /* ----------------------------------------------------------------------- */
  /**
   * Dźwięk powstaje jako kilkusekundowa pętla WAV odtwarzana elementem <audio>,
   * a nie przez Web Audio na żywo. Tylko tak gra dalej na iPhonie po zablokowaniu
   * ekranu i z wyciszonym przełącznikiem, a na ekranie blokady pojawiają się
   * przyciski odtwarzania (Media Session).
   */
  const PROBKOWANIE = 44100;
  const DLUGOSC_PETLI = 8; // s — częstotliwości zaokrąglane do 1/8 Hz domykają się w pętli bez trzasku
  const PRZENIKANIE = 0.25; // s — szum łączy się w pętlę przez krótkie przenikanie

  const DOMYSLNE_DZWIEKI = {
    szum: "brown",
    glosnoscSzumu: 0.5,
    ton: "brak",
    czestotliwosc: 200,
    roznica: 10,
    glosnoscTonu: 0.25,
    autoSkupienie: false,
    gra: false,
  };

  function generujSzum(rodzaj, probki) {
    const wynik = new Float32Array(probki);
    let b0 = 0, b1 = 0, b2 = 0, b3 = 0, b4 = 0, b5 = 0, b6 = 0, brazowy = 0;
    for (let i = 0; i < probki; i += 1) {
      const bialy = Math.random() * 2 - 1;
      if (rodzaj === "white") {
        wynik[i] = bialy;
      } else if (rodzaj === "pink") {
        // Filtr Paula Kelleta — spadek 3 dB na oktawę.
        b0 = 0.99886 * b0 + bialy * 0.0555179;
        b1 = 0.99332 * b1 + bialy * 0.0750759;
        b2 = 0.969 * b2 + bialy * 0.153852;
        b3 = 0.8665 * b3 + bialy * 0.3104856;
        b4 = 0.55 * b4 + bialy * 0.5329522;
        b5 = -0.7616 * b5 - bialy * 0.016898;
        wynik[i] = b0 + b1 + b2 + b3 + b4 + b5 + b6 + bialy * 0.5362;
        b6 = bialy * 0.115926;
      } else {
        // Szum brązowy: całkowanie z upływem — głęboki, „deszczowy” pomruk.
        brazowy = (brazowy + 0.02 * bialy) / 1.02;
        wynik[i] = brazowy;
      }
    }
    let szczyt = 0;
    for (let i = 0; i < probki; i += 1) szczyt = Math.max(szczyt, Math.abs(wynik[i]));
    const skala = szczyt ? 0.9 / szczyt : 0;
    for (let i = 0; i < probki; i += 1) wynik[i] *= skala;
    return wynik;
  }

  const kwantyzuj = (hz) => Math.round(hz * DLUGOSC_PETLI) / DLUGOSC_PETLI;

  function zbudujWav(cfg) {
    const ramki = PROBKOWANIE * DLUGOSC_PETLI;
    const zakladka = Math.round(PROBKOWANIE * PRZENIKANIE);
    const lewy = new Float32Array(ramki);
    const prawy = new Float32Array(ramki);

    if (cfg.szum !== "brak" && cfg.glosnoscSzumu > 0) {
      for (const kanal of [lewy, prawy]) {
        const surowy = generujSzum(cfg.szum, ramki + zakladka);
        for (let i = 0; i < ramki; i += 1) {
          let probka = surowy[i];
          if (i < zakladka) {
            const t = i / zakladka;
            probka = surowy[i] * t + surowy[ramki + i] * (1 - t);
          }
          kanal[i] += probka * cfg.glosnoscSzumu * 0.8;
        }
      }
    }

    if (cfg.ton !== "brak" && cfg.glosnoscTonu > 0) {
      const nosna = kwantyzuj(cfg.czestotliwosc);
      const prawa = cfg.ton === "binauralny" ? kwantyzuj(cfg.czestotliwosc + cfg.roznica) : nosna;
      const glosnosc = cfg.glosnoscTonu * 0.6;
      for (let i = 0; i < ramki; i += 1) {
        const t = i / PROBKOWANIE;
        let obwiednia = 1;
        if (cfg.ton === "izochroniczny") {
          // Impulsy tonu w rytmie różnicy — działają także bez słuchawek.
          obwiednia = 0.5 - 0.5 * Math.cos(2 * Math.PI * kwantyzuj(cfg.roznica) * t);
        }
        lewy[i] += Math.sin(2 * Math.PI * nosna * t) * glosnosc * obwiednia;
        prawy[i] += Math.sin(2 * Math.PI * prawa * t) * glosnosc * obwiednia;
      }
    }

    const bajty = new ArrayBuffer(44 + ramki * 4);
    const widok = new DataView(bajty);
    const napis = (przesuniecie, tekst) => [...tekst].forEach((znak, i) => widok.setUint8(przesuniecie + i, znak.charCodeAt(0)));
    napis(0, "RIFF");
    widok.setUint32(4, 36 + ramki * 4, true);
    napis(8, "WAVE");
    napis(12, "fmt ");
    widok.setUint32(16, 16, true);
    widok.setUint16(20, 1, true);
    widok.setUint16(22, 2, true);
    widok.setUint32(24, PROBKOWANIE, true);
    widok.setUint32(28, PROBKOWANIE * 4, true);
    widok.setUint16(32, 4, true);
    widok.setUint16(34, 16, true);
    napis(36, "data");
    widok.setUint32(40, ramki * 4, true);
    let pozycja = 44;
    for (let i = 0; i < ramki; i += 1) {
      widok.setInt16(pozycja, Math.max(-1, Math.min(1, lewy[i])) * 32767, true);
      widok.setInt16(pozycja + 2, Math.max(-1, Math.min(1, prawy[i])) * 32767, true);
      pozycja += 4;
    }
    return new Blob([bajty], { type: "audio/wav" });
  }

  const OPIS_SZUMU = { white: "Szum biały", pink: "Szum różowy", brown: "Szum brązowy", brak: "" };
  const OPIS_TONU = { ton: "ton", binauralny: "rytm binauralny", izochroniczny: "rytm izochroniczny", brak: "" };

  const dzwieki = {
    dostepne: Boolean(boot.ambient),
    cfg: { ...DOMYSLNE_DZWIEKI, ...czytaj(KLUCZ_DZWIEKOW, {}) },
    gra: false,
    czekaNaGest: false,
    element: null,
    adres: null,
    odswiezenie: null,
    przeladowanie: false,

    get opis() {
      const czesci = [OPIS_SZUMU[this.cfg.szum], OPIS_TONU[this.cfg.ton]].filter(Boolean);
      if (!czesci.length) return "Cisza";
      const tekst = czesci.join(" + ");
      return tekst.charAt(0).toUpperCase() + tekst.slice(1);
    },

    get faktycznaRoznica() {
      return kwantyzuj(this.cfg.roznica);
    },

    zapiszCfg() {
      zapisz(KLUCZ_DZWIEKOW, { ...this.cfg, gra: this.gra });
    },

    przygotujElement() {
      if (this.element) return this.element;
      this.element = new Audio();
      this.element.loop = true;
      this.element.preload = "auto";
      this.element.setAttribute("playsinline", "");
      // Wstrzymanie i wznowienie z ekranu blokady albo słuchawek.
      this.element.addEventListener("play", () => {
        this.gra = true;
      });
      this.element.addEventListener("pause", () => {
        if (!this.przeladowanie) this.gra = false;
      });
      if ("mediaSession" in navigator) {
        navigator.mediaSession.setActionHandler("play", () => this.wlacz());
        navigator.mediaSession.setActionHandler("pause", () => this.wylacz());
      }
      return this.element;
    },

    zaladuj() {
      const element = this.przygotujElement();
      const stary = this.adres;
      this.adres = URL.createObjectURL(zbudujWav(this.cfg));
      // Podmiana źródła wstrzymuje odtwarzanie — to nie jest decyzja użytkownika.
      this.przeladowanie = true;
      element.src = this.adres;
      window.setTimeout(() => {
        this.przeladowanie = false;
      }, 0);
      if (stary) window.setTimeout(() => URL.revokeObjectURL(stary), 2000);
      if ("mediaSession" in navigator && window.MediaMetadata) {
        navigator.mediaSession.metadata = new MediaMetadata({
          title: this.opis,
          artist: "MTQuiz · Pomodoro",
          artwork: [{ src: "/static/icons/icon-512.png", sizes: "512x512", type: "image/png" }],
        });
      }
    },

    async wlacz() {
      if (!this.dostepne) return;
      const element = this.przygotujElement();
      if (!this.adres) this.zaladuj();
      try {
        await element.play();
        this.gra = true;
        this.czekaNaGest = false;
      } catch (error) {
        // Autoodtwarzanie zablokowane — dźwięk ruszy przy pierwszym kliknięciu na stronie.
        this.gra = false;
        this.czekaNaGest = true;
        const wznow = () => {
          if (this.czekaNaGest) this.wlacz();
        };
        document.addEventListener("pointerdown", wznow, { once: true, capture: true });
        document.addEventListener("keydown", wznow, { once: true, capture: true });
      }
      this.zapiszCfg();
    },

    wylacz() {
      if (this.element) this.element.pause();
      this.gra = false;
      this.czekaNaGest = false;
      this.zapiszCfg();
    },

    przelacz() {
      if (this.gra) this.wylacz();
      else this.wlacz();
    },

    /** Zmiana ustawień: nowa pętla po krótkiej zwłoce (suwaki generują wiele zdarzeń). */
    zmien() {
      this.zapiszCfg();
      window.clearTimeout(this.odswiezenie);
      this.odswiezenie = window.setTimeout(() => {
        if (!this.adres && !this.gra) return;
        const gralo = this.gra;
        this.zaladuj();
        if (gralo) this.element.play().catch(() => {});
      }, 350);
    },

    ustawPreset(preset) {
      Object.assign(this.cfg, preset);
      this.zmien();
      if (!this.gra) this.wlacz();
    },
  };

  /* ----------------------------------------------------------------------- */
  /* Silnik minutnika                                                         */
  /* ----------------------------------------------------------------------- */
  const startowyLokalny = czytaj(KLUCZ_STANU, null);
  const startowySerwer = boot.timer || { revision: 0, state: {} };
  const lokalnyNowszy = startowyLokalny && startowyLokalny.revision > (startowySerwer.revision || 0);
  const startowy = lokalnyNowszy ? startowyLokalny : startowySerwer;

  const magazyn = {
    stan: startowy.state && startowy.state.status ? startowy.state : pustyStan(),
    rewizja: startowy.revision || 0,
    config: { ...boot.config },
    teraz: Date.now(),
    widzet: Boolean(boot.widget),
    zwiniety: czytaj(KLUCZ_ZWINIECIA, false),
    powiadomienia,
    dzwieki,
    czekaNaWysylke: lokalnyNowszy,
    wysylka: null,

    /* --- Odczyty dla widoków ------------------------------------------- */
    get aktywny() {
      return this.stan.status !== "idle";
    },
    get faza() {
      return this.stan.plan[this.stan.index] || null;
    },
    get typFazy() {
      return this.faza ? this.faza.type : "focus";
    },
    get nazwaFazy() {
      if (this.stan.status === "finished") return "Seria ukończona";
      return this.faza ? FAZY[this.faza.type].nazwa : "Pomodoro";
    },
    get jestPrzerwa() {
      return this.typFazy !== "focus";
    },
    get pozostalo() {
      const stan = this.stan;
      if (stan.status === "running") return Math.max(0, (stan.endsAt - this.teraz) / 1000);
      if (stan.status === "paused" || stan.status === "ready") return stan.remaining || 0;
      if (stan.status === "finished") return 0;
      return this.config.focus_minutes * 60;
    },
    get dlugoscFazy() {
      return this.faza ? this.faza.seconds : this.config.focus_minutes * 60;
    },
    get postep() {
      if (this.stan.status === "finished") return 1;
      if (this.stan.status === "idle" || this.stan.status === "ready") return 0;
      return Math.min(1, Math.max(0, 1 - this.pozostalo / this.dlugoscFazy));
    },
    get zegar() {
      return zegar(this.pozostalo);
    },
    get rundy() {
      return this.stan.plan.filter((faza) => faza.type === "focus").length || this.config.rounds;
    },
    /** Numer bieżącej rundy skupienia (przerwa należy do rundy przed nią). */
    get runda() {
      if (!this.stan.plan.length) return 1;
      return this.stan.plan.slice(0, this.stan.index + 1).filter((faza) => faza.type === "focus").length || 1;
    },
    /** Stan kropek rund: done | current | todo. */
    get kropki() {
      return Array.from({ length: this.rundy }, (_, numer) => {
        const runda = numer + 1;
        if (this.stan.status === "finished") return "done";
        if (runda < this.runda || (runda === this.runda && this.jestPrzerwa)) return "done";
        if (runda === this.runda && this.aktywny) return "current";
        return "todo";
      });
    },
    get nastepna() {
      return this.stan.plan[this.stan.index + 1] || null;
    },
    /** Opis przycisku startu fazy oczekującej na użytkownika. */
    get etykietaStartu() {
      const faza = this.faza;
      if (!faza) return "Start";
      return faza.type === "focus"
        ? `Zacznij rundę ${this.runda} (${Math.round(faza.seconds / 60)} min)`
        : `Zacznij ${FAZY[faza.type].nazwa.toLowerCase()} (${Math.round(faza.seconds / 60)} min)`;
    },

    /* --- Zmiany stanu ----------------------------------------------------- */
    autoStart(typ) {
      return typ === "focus" ? Boolean(this.stan.autoFocus) : Boolean(this.stan.autoBreaks);
    },

    zatwierdz({ wyslij = true } = {}) {
      this.stan.updatedAt = Date.now();
      this.rewizja += 1;
      zapisz(KLUCZ_STANU, { revision: this.rewizja, state: this.stan });
      if (wyslij) this.wyslij();
      this.odswiezTytul();
      document.dispatchEvent(new CustomEvent("pomodoro:zmiana"));
    },

    start(etykieta) {
      audio();
      const plan = zbudujPlan(this.config);
      const teraz = Date.now();
      this.stan = {
        status: "running",
        plan,
        index: 0,
        seriesId: `${teraz.toString(36)}${Math.random().toString(36).slice(2, 6)}`,
        label: (etykieta || "").trim().slice(0, 120),
        autoBreaks: this.config.auto_start_breaks,
        autoFocus: this.config.auto_start_focus,
        phaseStartedAt: teraz,
        endsAt: teraz + plan[0].seconds * 1000,
      };
      this.teraz = teraz;
      this.zatwierdz();
      if (this.dzwieki.dostepne && this.dzwieki.cfg.autoSkupienie) this.dzwieki.wlacz();
    },

    zacznijFaze() {
      if (this.stan.status !== "ready") return;
      audio();
      const teraz = Date.now();
      this.stan.status = "running";
      this.stan.phaseStartedAt = teraz;
      this.stan.endsAt = teraz + (this.stan.remaining || this.faza.seconds) * 1000;
      delete this.stan.remaining;
      this.teraz = teraz;
      this.zatwierdz();
      this.dzwiekiDoFazy();
    },

    pauza() {
      if (this.stan.status !== "running") return;
      this.stan.status = "paused";
      this.stan.remaining = Math.max(0, (this.stan.endsAt - Date.now()) / 1000);
      delete this.stan.endsAt;
      this.zatwierdz();
    },

    wznow() {
      if (this.stan.status !== "paused") return;
      audio();
      this.stan.status = "running";
      this.stan.endsAt = Date.now() + this.stan.remaining * 1000;
      delete this.stan.remaining;
      this.teraz = Date.now();
      this.zatwierdz();
    },

    /** Główny przycisk: start, pauza, wznowienie albo start czekającej fazy. */
    przelacz(etykieta) {
      const status = this.stan.status;
      if (status === "running") this.pauza();
      else if (status === "paused") this.wznow();
      else if (status === "ready") this.zacznijFaze();
      else this.start(etykieta);
    },

    /** Dokłada minuty do bieżącej fazy. */
    wydluz(minuty = 5) {
      const faza = this.faza;
      if (!faza || !["running", "paused", "ready"].includes(this.stan.status)) return;
      faza.seconds += minuty * 60;
      if (this.stan.status === "running") this.stan.endsAt += minuty * 60000;
      else this.stan.remaining = (this.stan.remaining || 0) + minuty * 60;
      this.zatwierdz();
    },

    /** Kończy bieżącą fazę przed czasem i od razu zaczyna następną. */
    pomin() {
      const faza = this.faza;
      if (!faza || !["running", "paused", "ready"].includes(this.stan.status)) return;
      const teraz = Date.now();
      if (this.stan.status !== "ready") this.rozlicz(this.stan.index, faza.seconds - this.pozostalo, false, teraz);
      const nastepny = this.stan.index + 1;
      if (nastepny >= this.stan.plan.length) {
        this.stan.status = "finished";
        this.stan.finishedAt = teraz;
        delete this.stan.endsAt;
        delete this.stan.remaining;
      } else {
        this.stan.index = nastepny;
        this.stan.status = "running";
        this.stan.phaseStartedAt = teraz;
        this.stan.endsAt = teraz + this.stan.plan[nastepny].seconds * 1000;
        delete this.stan.remaining;
      }
      this.teraz = teraz;
      this.zatwierdz();
      this.dzwiekiDoFazy();
    },

    /** Przerywa serię. Rozpoczęte skupienie dłuższe niż minuta trafia do statystyk. */
    stop() {
      const faza = this.faza;
      if (faza && ["running", "paused"].includes(this.stan.status)) {
        this.rozlicz(this.stan.index, faza.seconds - this.pozostalo, false, Date.now());
      }
      this.stan = pustyStan();
      this.zatwierdz();
      if (this.dzwieki.cfg.autoSkupienie) this.dzwieki.wylacz();
    },

    zamknij() {
      this.stan = pustyStan();
      this.zatwierdz();
    },

    /** Zapisuje fazę w statystykach (kolejka przeżyje brak sieci i zamknięcie karty). */
    rozlicz(index, sekundy, ukonczona, koniec) {
      const faza = this.stan.plan[index];
      if (!faza) return;
      const faktyczne = Math.round(Math.max(0, Math.min(sekundy, faza.seconds)));
      // Przerwane skupienie krótsze niż minuta i pominięte przerwy to nie nauka.
      if (!ukonczona && (faza.type !== "focus" || faktyczne < 60)) return;
      const start = Math.min(this.stan.phaseStartedAt || koniec - faktyczne * 1000, koniec);
      kolejka.dodaj({
        client_key: `${this.stan.seriesId}:${index}`,
        kind: faza.type,
        planned_seconds: Math.round(faza.seconds),
        actual_seconds: faktyczne,
        completed: ukonczona,
        label: this.stan.label || "",
        started_at: new Date(start).toISOString(),
        ended_at: new Date(koniec).toISOString(),
      });
    },

    /**
     * Rozlicza fazy, które dobiegły końca. ``naZywo`` oznacza, że koniec fazy
     * nastąpił przed chwilą przy otwartej stronie — wtedy gra sygnał i pojawia
     * się komunikat. Po powrocie po dłuższej nieobecności fazy rozliczają się po cichu.
     */
    uzgodnij(naZywo = true) {
      const teraz = Date.now();
      this.teraz = teraz;
      let zmiana = false;
      let ogloszenie = null;
      while (this.stan.status === "running" && teraz >= this.stan.endsAt) {
        const koniec = this.stan.endsAt;
        const index = this.stan.index;
        const faza = this.stan.plan[index];
        this.rozlicz(index, faza.seconds, true, koniec);
        zmiana = true;
        const nastepna = this.stan.plan[index + 1];
        ogloszenie = naZywo && teraz - koniec < 90000 ? komunikat(this.stan, index) : null;
        if (!nastepna) {
          this.stan.status = "finished";
          this.stan.finishedAt = koniec;
          delete this.stan.endsAt;
          break;
        }
        this.stan.index = index + 1;
        if (this.autoStart(nastepna.type)) {
          this.stan.phaseStartedAt = koniec;
          this.stan.endsAt = koniec + nastepna.seconds * 1000;
        } else {
          this.stan.status = "ready";
          this.stan.remaining = nastepna.seconds;
          delete this.stan.endsAt;
        }
      }
      if (zmiana) {
        this.zatwierdz();
        if (ogloszenie) this.oglos(ogloszenie);
      }
      return zmiana;
    },

    oglos({ tytul, tresc, koniecPrzerwy }) {
      if (this.config.sound) zagrajSygnal(koniecPrzerwy);
      if (navigator.vibrate) navigator.vibrate([180, 90, 180]);
      toast(`${tytul} — ${tresc}`, "info", 7000);
      this.powiadomienia.pokaz(tytul, tresc);
      this.dzwiekiDoFazy();
    },

    /** Automatyczne dźwięki tła: grają w skupieniu, milkną w przerwie. */
    dzwiekiDoFazy() {
      const d = this.dzwieki;
      if (!d.dostepne || !d.cfg.autoSkupienie) return;
      const skupienie = this.stan.status === "running" && this.typFazy === "focus";
      if (skupienie && !d.gra) d.wlacz();
      if (!skupienie && d.gra) d.wylacz();
    },

    /** Plan powiadomień push na końce kolejnych faz (do pierwszej fazy czekającej na start). */
    plan() {
      const stan = this.stan;
      if (stan.status !== "running") return [];
      const pozycje = [];
      let koniec = stan.endsAt;
      for (let index = stan.index; index < stan.plan.length && pozycje.length < 30; index += 1) {
        const { tytul, tresc } = komunikat(stan, index);
        pozycje.push({ in_seconds: Math.max(0, (koniec - Date.now()) / 1000), title: tytul, body: tresc });
        const nastepna = stan.plan[index + 1];
        if (!nastepna || !this.autoStart(nastepna.type)) break;
        koniec += nastepna.seconds * 1000;
      }
      return pozycje;
    },

    /** Wysyła stan i plan powiadomień na serwer (z krótką zwłoką scalającą kliknięcia). */
    wyslij() {
      this.czekaNaWysylke = true;
      window.clearTimeout(this.wysylka);
      this.wysylka = window.setTimeout(() => this.wyslijTeraz(), 250);
    },

    async wyslijTeraz() {
      try {
        const odpowiedz = await api.put("/api/pomodoro/state", {
          revision: this.rewizja,
          state: this.stan,
          schedule: this.plan(),
        });
        this.czekaNaWysylke = false;
        // Inne urządzenie zapisało zmianę z tym samym lub wyższym numerem — obowiązuje wersja serwera.
        if (!odpowiedz.accepted && odpowiedz.revision >= this.rewizja) this.przyjmij(odpowiedz, { wymus: true });
      } catch (error) {
        /* Brak sieci — stan zostaje lokalnie i pójdzie przy następnej zmianie albo powrocie sieci. */
      }
    },

    /** Przyjmuje nowszy stan z serwera albo z innej karty. */
    przyjmij({ revision, state }, { wymus = false } = {}) {
      if (revision <= this.rewizja && !wymus) return false;
      this.rewizja = revision;
      this.stan = state && state.status ? state : pustyStan();
      zapisz(KLUCZ_STANU, { revision: this.rewizja, state: this.stan });
      this.uzgodnij(false);
      this.odswiezTytul();
      return true;
    },

    async pobierz() {
      try {
        const odpowiedz = await api.get("/api/pomodoro/state");
        if (odpowiedz.revision > this.rewizja) this.przyjmij(odpowiedz);
        else if (this.czekaNaWysylke || odpowiedz.revision < this.rewizja) this.wyslijTeraz();
      } catch (error) {
        /* spróbujemy przy następnej okazji */
      }
    },

    async zapiszConfig(zmiany) {
      Object.assign(this.config, zmiany);
      const wynik = await api.patch("/api/preferences", { pomodoro: zmiany });
      this.config = { ...wynik.pomodoro };
      return wynik;
    },

    zwin(wartosc) {
      this.zwiniety = wartosc;
      zapisz(KLUCZ_ZWINIECIA, wartosc);
    },

    odswiezTytul() {
      if (!tytulBazowy) return;
      const stan = this.stan;
      if (stan.status === "running" || stan.status === "paused") {
        const znak = stan.status === "paused" ? "⏸ " : "";
        document.title = `${znak}${this.zegar} · ${FAZY[this.typFazy].krotko} — ${tytulBazowy}`;
      } else if (stan.status === "ready") {
        document.title = `▶ ${FAZY[this.typFazy].krotko} czeka — ${tytulBazowy}`;
      } else {
        document.title = tytulBazowy;
      }
    },
  };

  /** Treść powiadomienia o końcu fazy ``index`` serii ``stan``. */
  function komunikat(stan, index) {
    const faza = stan.plan[index];
    const nastepna = stan.plan[index + 1];
    const rundy = stan.plan.filter((pozycja) => pozycja.type === "focus").length;
    const runda = stan.plan.slice(0, index + 1).filter((pozycja) => pozycja.type === "focus").length;
    const minuty = (pozycja) => `${Math.round(pozycja.seconds / 60)} min`;
    const temat = stan.label ? ` „${stan.label}”` : "";

    if (faza.type === "focus") {
      if (!nastepna) {
        return { tytul: "Seria ukończona 🎉", tresc: `${rundy} × skupienie${temat} za Tobą. Świetna robota!`, koniecPrzerwy: false };
      }
      const auto = nastepna.type === "focus" ? stan.autoFocus : stan.autoBreaks;
      const nazwa = nastepna.type === "long_break" ? "Długa przerwa" : "Przerwa";
      return {
        tytul: `Koniec skupienia · runda ${runda}/${rundy}`,
        tresc: auto ? `${nazwa}: ${minuty(nastepna)}. Odejdź od ekranu.` : `${nazwa} (${minuty(nastepna)}) czeka na start.`,
        koniecPrzerwy: false,
      };
    }
    if (!nastepna) {
      return { tytul: "Koniec długiej przerwy", tresc: "Seria zakończona — możesz zacząć kolejną.", koniecPrzerwy: true };
    }
    return {
      tytul: "Koniec przerwy",
      tresc: stan.autoFocus
        ? `Wracamy do pracy — runda ${runda + 1}/${rundy} (${minuty(nastepna)}).`
        : `Runda ${runda + 1}/${rundy} czeka na start (${minuty(nastepna)}).`,
      koniecPrzerwy: true,
    };
  }

  /* ----------------------------------------------------------------------- */
  /* Kolejka wpisów do statystyk                                              */
  /* ----------------------------------------------------------------------- */
  const kolejka = {
    trwa: false,
    dodaj(wpis) {
      const lista = czytaj(KLUCZ_KOLEJKI, []);
      if (!lista.some((pozycja) => pozycja.client_key === wpis.client_key)) lista.push(wpis);
      zapisz(KLUCZ_KOLEJKI, lista.slice(-200));
      this.wyslij();
    },
    async wyslij() {
      if (this.trwa) return;
      this.trwa = true;
      try {
        let lista = czytaj(KLUCZ_KOLEJKI, []);
        while (lista.length) {
          const wpis = lista[0];
          try {
            await api.post("/api/pomodoro/entries", wpis);
          } catch (error) {
            // Błąd sieci — zostawiamy kolejkę na później; odrzucenie przez serwer — wpis znika.
            if (!error.status) break;
          }
          lista = czytaj(KLUCZ_KOLEJKI, []).filter((pozycja) => pozycja.client_key !== wpis.client_key);
          zapisz(KLUCZ_KOLEJKI, lista);
          document.dispatchEvent(new CustomEvent("pomodoro:wpis"));
        }
      } finally {
        this.trwa = false;
      }
    },
  };

  /* ----------------------------------------------------------------------- */
  /* Uruchomienie                                                             */
  /* ----------------------------------------------------------------------- */
  let tytulBazowy = "";
  let reaktywny = magazyn;
  const silnik = () => reaktywny;

  // Start dopiero po zarejestrowaniu magazynu w Alpine: zmiany z timerów i obietnic
  // muszą przechodzić przez obiekt reaktywny, inaczej widok by ich nie zauważył.
  document.addEventListener("alpine:init", () => {
    window.Alpine.store("pomodoro", magazyn);
    reaktywny = window.Alpine.store("pomodoro");
    uruchom();
  });

  function uruchom() {
    tytulBazowy = document.title;
    const s = silnik();
    s.uzgodnij(false);
    s.odswiezTytul();
    if (s.czekaNaWysylke) s.wyslijTeraz();
    kolejka.wyslij();
    s.powiadomienia.przygotuj();

    // Dźwięki tła grały na poprzedniej stronie — próbujemy kontynuować.
    if (s.dzwieki.dostepne && czytaj(KLUCZ_DZWIEKOW, {}).gra) s.dzwieki.wlacz();

    window.setInterval(() => {
      const m = silnik();
      if (!m.uzgodnij(true)) m.teraz = Date.now();
      if (m.stan.status === "running") m.odswiezTytul();
    }, 500);

    // Zmiany z innego urządzenia: przy powrocie na kartę i co pół minuty, gdy strona jest widoczna.
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") {
        silnik().uzgodnij(true);
        silnik().pobierz();
      }
    });
    window.setInterval(() => {
      if (document.visibilityState === "visible") silnik().pobierz();
    }, 30000);
    window.addEventListener("online", () => {
      kolejka.wyslij();
      silnik().pobierz();
    });

    // Inna karta tej samej przeglądarki zmieniła stan.
    window.addEventListener("storage", (event) => {
      if (event.key !== KLUCZ_STANU || !event.newValue) return;
      try {
        const dane = JSON.parse(event.newValue);
        if (dane.revision > silnik().rewizja) silnik().przyjmij(dane);
      } catch (error) {
        /* uszkodzony wpis innej karty */
      }
    });
  }

  /* ----------------------------------------------------------------------- */
  /* Komponenty Alpine                                                        */
  /* ----------------------------------------------------------------------- */
  /** Pływający minutnik (komputer) i pigułka w nagłówku (telefon). */
  function pomodoroWidget() {
    return {
      get p() {
        return this.$store.pomodoro;
      },
      get widoczny() {
        return this.p.widzet && this.p.aktywny && window.location.pathname !== "/pomodoro";
      },

      get kolor() {
        return kolorFazy(this.p);
      },
    };
  }

  /** Klasy kolorów zależne od fazy — skupienie w kolorze marki, przerwy w zieleni i fiolecie. */
  function kolorFazy(p) {
    if (p.stan.status === "paused") return { tekst: "text-amber-600 dark:text-amber-400", tlo: "bg-amber-500", jasne: "bg-amber-100 dark:bg-amber-950", obrys: "stroke-amber-500" };
    if (p.stan.status === "finished") return { tekst: "text-emerald-600 dark:text-emerald-400", tlo: "bg-emerald-500", jasne: "bg-emerald-100 dark:bg-emerald-950", obrys: "stroke-emerald-500" };
    if (p.typFazy === "short_break") return { tekst: "text-emerald-600 dark:text-emerald-400", tlo: "bg-emerald-500", jasne: "bg-emerald-100 dark:bg-emerald-950", obrys: "stroke-emerald-500" };
    if (p.typFazy === "long_break") return { tekst: "text-violet-600 dark:text-violet-400", tlo: "bg-violet-500", jasne: "bg-violet-100 dark:bg-violet-950", obrys: "stroke-violet-500" };
    return { tekst: "text-brand-600 dark:text-brand-400", tlo: "bg-brand-600 dark:bg-brand-500", jasne: "bg-brand-100 dark:bg-brand-950", obrys: "stroke-brand-600 dark:stroke-brand-400" };
  }

  const PRESETY = [
    { nazwa: "Klasyk", focus_minutes: 25, short_break_minutes: 5, rounds: 4, long_break_minutes: 15 },
    { nazwa: "Krótka seria", focus_minutes: 25, short_break_minutes: 5, rounds: 3, long_break_minutes: 0 },
    { nazwa: "Sprint", focus_minutes: 15, short_break_minutes: 3, rounds: 4, long_break_minutes: 10 },
    { nazwa: "Głęboka praca", focus_minutes: 50, short_break_minutes: 10, rounds: 3, long_break_minutes: 20 },
    { nazwa: "Flow", focus_minutes: 90, short_break_minutes: 20, rounds: 2, long_break_minutes: 0 },
  ];

  const PRESETY_DZWIEKOW = [
    { nazwa: "Deszcz", opis: "szum brązowy", cfg: { szum: "brown", ton: "brak" } },
    { nazwa: "Szum różowy", opis: "łagodny, pełny", cfg: { szum: "pink", ton: "brak" } },
    { nazwa: "Skupienie β", opis: "14 Hz + szum", cfg: { szum: "pink", ton: "binauralny", czestotliwosc: 200, roznica: 14 } },
    { nazwa: "Relaks α", opis: "10 Hz", cfg: { szum: "brown", ton: "binauralny", czestotliwosc: 180, roznica: 10 } },
    { nazwa: "Gamma 40 Hz", opis: "izochroniczne", cfg: { szum: "brak", ton: "izochroniczny", czestotliwosc: 220, roznica: 40 } },
  ];

  const OKRESY = [
    { klucz: "day", nazwa: "Dzień" },
    { klucz: "week", nazwa: "Tydzień" },
    { klucz: "month", nazwa: "Miesiąc" },
    { klucz: "year", nazwa: "Rok" },
  ];

  /** Strona /pomodoro: duży minutnik, ustawienia, statystyki i odznaki. */
  function pomodoroPage() {
    return {
      etykieta: "",
      okresy: OKRESY,
      presety: PRESETY,
      presetyDzwiekow: PRESETY_DZWIEKOW,
      okres: czytaj("mtquiz-pomodoro-okres", "week"),
      przesuniecie: 0,
      statystyki: null,
      podsumowanie: null,
      wpisy: [],
      laduje: false,
      ustawienia: { ...boot.config },
      zapisUstawien: null,
      wskazany: null,
      jestIOS,
      jestZainstalowana,

      get p() {
        return this.$store.pomodoro;
      },
      get kolor() {
        return kolorFazy(this.p);
      },
      get obwod() {
        return 2 * Math.PI * 46;
      },

      init() {
        this.etykieta = this.p.stan.label || czytaj("mtquiz-pomodoro-etykieta", "");
        this.wczytaj();
        document.addEventListener("pomodoro:wpis", () => this.odswiezPoWpisie());
        document.addEventListener("keydown", (event) => this.klawiatura(event));
      },

      klawiatura(event) {
        if (event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey || event.repeat) return;
        if (isTypingTarget(event.target) || document.querySelector('[role="dialog"][aria-modal="true"]')) return;
        if (event.key !== " " && event.key !== "Spacebar") return;
        const fokus = document.activeElement;
        if (fokus && fokus !== document.body && fokus.matches("button, a")) fokus.blur();
        event.preventDefault();
        this.glowny();
      },

      glowny() {
        zapisz("mtquiz-pomodoro-etykieta", this.etykieta);
        this.p.przelacz(this.etykieta);
      },

      get etykietaGlownego() {
        const status = this.p.stan.status;
        if (status === "running") return "Pauza";
        if (status === "paused") return "Wznów";
        if (status === "ready") return this.p.etykietaStartu;
        if (status === "finished") return "Nowa seria";
        return "Start";
      },

      /* --- Ustawienia serii ---------------------------------------------- */
      get opisSerii() {
        const u = this.ustawienia;
        const skupienie = u.focus_minutes * u.rounds;
        const przerwy = u.short_break_minutes * (u.rounds - 1) + (u.long_break_minutes || 0);
        return `${u.rounds} × ${u.focus_minutes} min skupienia · razem ${czasTrwania((skupienie + przerwy) * 60)}`;
      },

      presetAktywny(preset) {
        const u = this.ustawienia;
        return (
          u.focus_minutes === preset.focus_minutes &&
          u.short_break_minutes === preset.short_break_minutes &&
          u.rounds === preset.rounds &&
          u.long_break_minutes === preset.long_break_minutes
        );
      },

      wybierzPreset(preset) {
        const { nazwa, ...wartosci } = preset;
        Object.assign(this.ustawienia, wartosci);
        this.zapiszUstawienia();
      },

      zapiszUstawienia() {
        window.clearTimeout(this.zapisUstawien);
        this.zapisUstawien = window.setTimeout(async () => {
          const u = this.ustawienia;
          const ogranicz = (wartosc, min, max, domyslna) => {
            const liczba = Math.round(Number(wartosc));
            return Number.isFinite(liczba) ? Math.min(max, Math.max(min, liczba)) : domyslna;
          };
          const zmiany = {
            focus_minutes: ogranicz(u.focus_minutes, 1, 180, 25),
            short_break_minutes: ogranicz(u.short_break_minutes, 1, 60, 5),
            long_break_minutes: ogranicz(u.long_break_minutes, 0, 90, 15),
            rounds: ogranicz(u.rounds, 1, 12, 4),
            daily_goal: ogranicz(u.daily_goal, 1, 24, 8),
            auto_start_breaks: Boolean(u.auto_start_breaks),
            auto_start_focus: Boolean(u.auto_start_focus),
            sound: Boolean(u.sound),
          };
          Object.assign(this.ustawienia, zmiany);
          try {
            await this.p.zapiszConfig(zmiany);
            toast(this.p.aktywny ? "Zapisano — nowe ustawienia obejmą kolejną serię." : "Ustawienia zapisane.", "success", 1800);
            if (this.podsumowanie && this.podsumowanie.today.goal !== zmiany.daily_goal) this.wczytajPodsumowanie();
          } catch (error) {
            toast(error.message || "Nie udało się zapisać ustawień.", "error");
          }
        }, 450);
      },

      /* --- Statystyki --------------------------------------------------- */
      async wczytaj() {
        await Promise.all([this.wczytajStatystyki(), this.wczytajPodsumowanie(), this.wczytajWpisy()]);
      },

      async wczytajStatystyki() {
        this.laduje = true;
        try {
          this.statystyki = await api.get(`/api/pomodoro/stats?period=${this.okres}&offset=${this.przesuniecie}`);
        } catch (error) {
          toast(error.message || "Nie udało się wczytać statystyk.", "error");
        } finally {
          this.laduje = false;
        }
      },

      async wczytajPodsumowanie() {
        try {
          this.podsumowanie = await api.get("/api/pomodoro/summary");
        } catch (error) {
          /* sekcja zostaje z poprzednimi danymi */
        }
      },

      async wczytajWpisy() {
        try {
          this.wpisy = await api.get("/api/pomodoro/entries?limit=12&kind=focus");
        } catch (error) {
          /* jw. */
        }
      },

      odswiezPoWpisie() {
        window.clearTimeout(this._odswiezenie);
        this._odswiezenie = window.setTimeout(() => this.wczytaj(), 600);
      },

      zmienOkres(klucz) {
        this.okres = klucz;
        this.przesuniecie = 0;
        zapisz("mtquiz-pomodoro-okres", klucz);
        this.wczytajStatystyki();
      },

      przesun(krok) {
        this.przesuniecie = Math.min(0, this.przesuniecie + krok);
        this.wczytajStatystyki();
      },

      async usunWpis(wpis) {
        const potwierdzone = await window.MTQuiz.confirmDialog({
          title: "Usunąć wpis ze statystyk?",
          message: `Blok skupienia ${czasTrwania(wpis.actual_seconds)} z ${this.dzien(wpis.ended_at)} zniknie z wykresów i odznak.`,
          confirmLabel: "Usuń",
          danger: true,
        });
        if (!potwierdzone) return;
        try {
          await api.delete(`/api/pomodoro/entries/${wpis.id}`);
          this.wczytaj();
        } catch (error) {
          toast(error.message, "error");
        }
      },

      get maksimum() {
        if (!this.statystyki) return 0;
        return Math.max(...this.statystyki.buckets.map((kubelek) => kubelek.focus_seconds), 0);
      },

      /** Górna granica osi: okrągła liczba minut powyżej maksimum. */
      get skala() {
        const minuty = this.maksimum / 60;
        if (minuty <= 0) return 60;
        const kroki = [15, 30, 60, 90, 120, 180, 240, 300, 360, 480, 600, 900, 1200, 1800, 2400, 3000, 3600, 4800, 6000, 9000, 12000];
        return (kroki.find((krok) => krok >= minuty) || Math.ceil(minuty / 6000) * 6000) * 60;
      },

      get podzialkaOsi() {
        const skala = this.skala;
        return [skala, skala / 2, 0].map((wartosc) => ({ wartosc, etykieta: wartosc ? czasTrwania(wartosc) : "0" }));
      },

      wysokosc(kubelek) {
        if (!kubelek.focus_seconds) return "0%";
        return `${Math.max(2, (kubelek.focus_seconds / this.skala) * 100)}%`;
      },

      /** Podpisy osi X: przy gęstych wykresach co któryś, żeby się nie nakładały. */
      podpis(index) {
        const s = this.statystyki;
        if (!s) return "";
        if (s.period === "day") return index % 3 === 0 ? `${index}:00` : "";
        if (s.period === "month") return index === 0 || (index + 1) % 5 === 0 ? s.buckets[index].label : "";
        return s.buckets[index].label;
      },

      opisKubelka(kubelek, index) {
        const s = this.statystyki;
        let kiedy = kubelek.label;
        if (s.period === "day") kiedy = `${index}:00–${index + 1}:00`;
        else if (s.period === "month") kiedy = `${kubelek.label}. dzień`;
        const pomidory = kubelek.pomodoros ? ` · ${kubelek.pomodoros} 🍅` : "";
        return `${kiedy}: ${kubelek.focus_seconds ? czasTrwania(kubelek.focus_seconds) : "brak skupienia"}${pomidory}`;
      },

      delta(klucz) {
        return this.statystyki ? this.statystyki.deltas[klucz] : null;
      },

      formatDelta(wartosc) {
        if (wartosc === null || wartosc === undefined) return "";
        return `${wartosc > 0 ? "+" : wartosc < 0 ? "−" : "±"}${Math.abs(wartosc)}%`;
      },

      klasaDelty(wartosc) {
        if (wartosc === null || wartosc === undefined || wartosc === 0) return "bg-ink-100 text-ink-600 dark:bg-ink-800 dark:text-ink-300";
        return wartosc > 0
          ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200"
          : "bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-200";
      },

      czas: czasTrwania,

      godzina(iso) {
        return new Date(iso).toLocaleTimeString("pl-PL", { hour: "2-digit", minute: "2-digit" });
      },

      dzien(iso) {
        const data = new Date(iso);
        const dzis = new Date();
        const wczoraj = new Date(Date.now() - 86400000);
        if (data.toDateString() === dzis.toDateString()) return "dziś";
        if (data.toDateString() === wczoraj.toDateString()) return "wczoraj";
        return data.toLocaleDateString("pl-PL", { day: "numeric", month: "short" });
      },

      get celProcent() {
        if (!this.podsumowanie) return 0;
        const { pomodoros, goal } = this.podsumowanie.today;
        return Math.min(1, goal ? pomodoros / goal : 0);
      },

      get obwodCelu() {
        return 2 * Math.PI * 22;
      },
    };
  }

  window.pomodoroWidget = pomodoroWidget;
  window.pomodoroPage = pomodoroPage;
  window.MTQuizPomodoro = { czasTrwania, zegar };
})();
