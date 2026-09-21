/**
 * Wspólna warstwa kliencka: motyw, komunikaty, klient API i drobne narzędzia.
 * Skrypt jest celowo pozbawiony zależności — ładuje się przed Alpine.js.
 */
(function () {
  "use strict";

  const THEME_KEY = "medfiszki-theme";

  /* ----------------------------------------------------------------------- */
  /* Motyw jasny / ciemny                                                     */
  /* ----------------------------------------------------------------------- */
  const theme = {
    current() {
      return document.documentElement.classList.contains("dark") ? "dark" : "light";
    },
    apply(value) {
      document.documentElement.classList.toggle("dark", value === "dark");
      try {
        localStorage.setItem(THEME_KEY, value);
      } catch (error) {
        /* Brak dostępu do localStorage — motyw działa tylko w bieżącej karcie. */
      }
      document.dispatchEvent(new CustomEvent("theme:change", { detail: { theme: value } }));
    },
    toggle() {
      this.apply(this.current() === "dark" ? "light" : "dark");
    },
  };

  document.addEventListener("click", (event) => {
    const trigger = event.target.closest("[data-theme-toggle]");
    if (trigger) {
      event.preventDefault();
      theme.toggle();
    }
  });

  // Reakcja na zmianę ustawień systemowych, dopóki użytkownik nie wybrał motywu ręcznie.
  try {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    media.addEventListener("change", (event) => {
      if (!localStorage.getItem(THEME_KEY)) {
        document.documentElement.classList.toggle("dark", event.matches);
      }
    });
  } catch (error) {
    /* Starsze przeglądarki bez addEventListener na MediaQueryList. */
  }

  /* ----------------------------------------------------------------------- */
  /* Powiadomienia                                                            */
  /* ----------------------------------------------------------------------- */
  const TOAST_STYLES = {
    success: "border-emerald-300 bg-emerald-50 text-emerald-900 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-100",
    error: "border-rose-300 bg-rose-50 text-rose-900 dark:border-rose-800 dark:bg-rose-950 dark:text-rose-100",
    info: "border-ink-200 bg-white text-ink-900 dark:border-ink-700 dark:bg-ink-900 dark:text-ink-100",
    warning: "border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100",
  };

  function toast(message, kind = "info", timeout = 4200) {
    const host = document.getElementById("toasts");
    if (!host || !message) return;

    const element = document.createElement("div");
    element.className =
      "pointer-events-auto w-full max-w-md animate-pop-in rounded-xl border px-4 py-3 text-sm shadow-float " +
      (TOAST_STYLES[kind] || TOAST_STYLES.info);
    element.textContent = message;
    element.addEventListener("click", () => element.remove());
    host.appendChild(element);

    window.setTimeout(() => {
      element.style.transition = "opacity .25s ease, transform .25s ease";
      element.style.opacity = "0";
      element.style.transform = "translateY(8px)";
      window.setTimeout(() => element.remove(), 260);
    }, timeout);
  }

  /* ----------------------------------------------------------------------- */
  /* Klient API                                                               */
  /* ----------------------------------------------------------------------- */
  class ApiError extends Error {
    constructor(message, status, payload) {
      super(message);
      this.name = "ApiError";
      this.status = status;
      this.payload = payload;
    }
  }

  async function readBody(response) {
    const type = response.headers.get("content-type") || "";
    if (type.includes("application/json")) {
      try {
        return await response.json();
      } catch (error) {
        return null;
      }
    }
    try {
      return await response.text();
    } catch (error) {
      return null;
    }
  }

  async function request(url, options = {}) {
    const config = { credentials: "same-origin", headers: {}, ...options };

    if (config.body !== undefined && !(config.body instanceof FormData)) {
      config.headers["Content-Type"] = "application/json";
      config.body = typeof config.body === "string" ? config.body : JSON.stringify(config.body);
    }
    config.headers["Accept"] = config.headers["Accept"] || "application/json";

    const response = await fetch(url, config);
    const payload = await readBody(response);

    if (!response.ok) {
      const detail =
        (payload && typeof payload === "object" && payload.detail) ||
        (typeof payload === "string" && payload.slice(0, 200)) ||
        `Błąd ${response.status}`;
      throw new ApiError(typeof detail === "string" ? detail : "Nieprawidłowe dane.", response.status, payload);
    }
    return payload;
  }

  const api = {
    get: (url) => request(url),
    post: (url, body) => request(url, { method: "POST", body }),
    put: (url, body) => request(url, { method: "PUT", body }),
    patch: (url, body) => request(url, { method: "PATCH", body }),
    delete: (url) => request(url, { method: "DELETE" }),
    upload: (url, formData) => request(url, { method: "POST", body: formData }),
  };

  /* ----------------------------------------------------------------------- */
  /* Wylogowanie                                                              */
  /* ----------------------------------------------------------------------- */
  document.addEventListener("click", async (event) => {
    const trigger = event.target.closest("[data-logout]");
    if (!trigger) return;
    event.preventDefault();
    try {
      await api.post("/api/auth/logout", {});
    } catch (error) {
      /* Nawet przy błędzie sieci przechodzimy na stronę logowania. */
    }
    window.location.href = "/logowanie";
  });

  /* ----------------------------------------------------------------------- */
  /* Okno potwierdzenia                                                       */
  /* ----------------------------------------------------------------------- */
  /**
   * Dostępne okno potwierdzenia zastępujące natywne `window.confirm`.
   * Zwraca obietnicę rozwiązywaną wartością logiczną.
   */
  function confirmDialog(options = {}) {
    const {
      title = "Potwierdź operację",
      message = "",
      confirmLabel = "Potwierdź",
      cancelLabel = "Anuluj",
      danger = false,
      requirePhrase = "",
    } = options;

    return new Promise((resolve) => {
      const previouslyFocused = document.activeElement;
      const overlay = document.createElement("div");
      overlay.className =
        "fixed inset-0 z-[60] flex items-end justify-center bg-ink-950/60 p-4 backdrop-blur-sm sm:items-center";
      overlay.setAttribute("role", "dialog");
      overlay.setAttribute("aria-modal", "true");

      const phraseBlock = requirePhrase
        ? `<label class="mt-4 block text-sm font-medium text-ink-700 dark:text-ink-300">
             Wpisz <code class="rounded bg-ink-200 px-1 dark:bg-ink-800">${requirePhrase}</code>, aby potwierdzić
             <input data-phrase class="input mt-1.5" autocomplete="off">
           </label>`
        : "";

      overlay.innerHTML = `
        <div class="w-full max-w-md animate-pop-in rounded-2xl border border-ink-200 bg-white p-6 shadow-float dark:border-ink-700 dark:bg-ink-900">
          <h2 class="text-base font-semibold text-ink-900 dark:text-white"></h2>
          <p class="mt-2 whitespace-pre-line text-sm text-ink-600 dark:text-ink-300"></p>
          ${phraseBlock}
          <div class="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <button type="button" data-cancel class="btn-secondary"></button>
            <button type="button" data-confirm class="${danger ? "btn-danger" : "btn-primary"}"></button>
          </div>
        </div>`;

      overlay.querySelector("h2").textContent = title;
      overlay.querySelector("p").textContent = message;
      const cancelButton = overlay.querySelector("[data-cancel]");
      const confirmButton = overlay.querySelector("[data-confirm]");
      const phraseInput = overlay.querySelector("[data-phrase]");
      cancelButton.textContent = cancelLabel;
      confirmButton.textContent = confirmLabel;

      function close(result) {
        document.removeEventListener("keydown", onKeydown, true);
        overlay.remove();
        if (previouslyFocused && typeof previouslyFocused.focus === "function") previouslyFocused.focus();
        resolve(result);
      }

      function onKeydown(event) {
        if (event.key === "Escape") {
          event.preventDefault();
          close(false);
        }
        if (event.key === "Tab") {
          const focusable = overlay.querySelectorAll("button, input");
          const first = focusable[0];
          const last = focusable[focusable.length - 1];
          if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
          } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
          }
        }
      }

      if (phraseInput) {
        confirmButton.disabled = true;
        phraseInput.addEventListener("input", () => {
          confirmButton.disabled = phraseInput.value.trim().toUpperCase() !== requirePhrase.toUpperCase();
        });
      }

      cancelButton.addEventListener("click", () => close(false));
      confirmButton.addEventListener("click", () => close(true));
      overlay.addEventListener("mousedown", (event) => {
        if (event.target === overlay) close(false);
      });
      document.addEventListener("keydown", onKeydown, true);

      document.body.appendChild(overlay);
      (phraseInput || confirmButton).focus();
    });
  }

  /* ----------------------------------------------------------------------- */
  /* Narzędzia współdzielone                                                  */
  /* ----------------------------------------------------------------------- */
  function shuffle(items) {
    const copy = items.slice();
    for (let index = copy.length - 1; index > 0; index -= 1) {
      const swap = Math.floor(Math.random() * (index + 1));
      [copy[index], copy[swap]] = [copy[swap], copy[index]];
    }
    return copy;
  }

  function formatDuration(seconds) {
    const total = Math.max(0, Math.round(seconds));
    const minutes = Math.floor(total / 60);
    const rest = total % 60;
    return `${String(minutes).padStart(2, "0")}:${String(rest).padStart(2, "0")}`;
  }

  function plural(count, one, few, many) {
    if (count === 1) return one;
    const lastTwo = count % 100;
    const last = count % 10;
    if (last >= 2 && last <= 4 && !(lastTwo >= 12 && lastTwo <= 14)) return few;
    return many;
  }

  function readJsonScript(id) {
    const node = document.getElementById(id);
    if (!node) return null;
    try {
      return JSON.parse(node.textContent);
    } catch (error) {
      console.error("Nie udało się odczytać danych strony:", error);
      return null;
    }
  }

  /**
   * Prosty detektor gestów przesunięcia — obsługa fiszek na urządzeniach dotykowych.
   */
  function bindSwipe(element, { onLeft, onRight, threshold = 60 } = {}) {
    if (!element) return () => {};
    let startX = 0;
    let startY = 0;
    let tracking = false;

    const start = (event) => {
      const point = event.changedTouches ? event.changedTouches[0] : event;
      startX = point.clientX;
      startY = point.clientY;
      tracking = true;
    };

    const end = (event) => {
      if (!tracking) return;
      tracking = false;
      const point = event.changedTouches ? event.changedTouches[0] : event;
      const deltaX = point.clientX - startX;
      const deltaY = point.clientY - startY;
      if (Math.abs(deltaX) < threshold || Math.abs(deltaX) < Math.abs(deltaY)) return;
      if (deltaX < 0 && typeof onLeft === "function") onLeft();
      if (deltaX > 0 && typeof onRight === "function") onRight();
    };

    element.addEventListener("touchstart", start, { passive: true });
    element.addEventListener("touchend", end, { passive: true });

    return () => {
      element.removeEventListener("touchstart", start);
      element.removeEventListener("touchend", end);
    };
  }

  window.MedFiszki = {
    api,
    ApiError,
    toast,
    theme,
    shuffle,
    formatDuration,
    plural,
    readJsonScript,
    bindSwipe,
    confirmDialog,
  };
})();
