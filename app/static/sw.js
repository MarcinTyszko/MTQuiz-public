/**
 * Service worker MTQuiz — wyłącznie powiadomienia.
 *
 * Odbiera wiadomości push o końcu faz Pomodoro i pokazuje je także przy
 * zamkniętej karcie albo zablokowanym telefonie. Celowo nie przechwytuje
 * żądań sieciowych: aplikacja zawsze wczytuje aktualne strony z serwera.
 */
"use strict";

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("push", (event) => {
  let dane = {};
  try {
    dane = event.data ? event.data.json() : {};
  } catch (error) {
    dane = { body: event.data ? event.data.text() : "" };
  }
  const tytul = dane.title || "MTQuiz";
  event.waitUntil(
    self.registration.showNotification(tytul, {
      body: dane.body || "",
      tag: dane.tag || "mtquiz-pomodoro",
      renotify: true,
      icon: "/static/icons/icon-192.png",
      badge: "/static/icons/badge-96.png",
      vibrate: [180, 90, 180],
      data: { url: dane.url || "/pomodoro" },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const cel = new URL((event.notification.data && event.notification.data.url) || "/pomodoro", self.location.origin);
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((okna) => {
      const naMiejscu = okna.find((okno) => new URL(okno.url).pathname === cel.pathname);
      if (naMiejscu) return naMiejscu.focus();
      const dowolne = okna.find((okno) => new URL(okno.url).origin === cel.origin);
      if (dowolne) return dowolne.focus().then((okno) => (okno || dowolne).navigate(cel.href));
      return self.clients.openWindow(cel.href);
    }),
  );
});

// Przeglądarka odnowiła subskrypcję (np. po wygaśnięciu) — przekazujemy nową serwerowi.
self.addEventListener("pushsubscriptionchange", (event) => {
  const opcje = event.oldSubscription ? event.oldSubscription.options : null;
  if (!opcje) return;
  event.waitUntil(
    self.registration.pushManager.subscribe(opcje).then((subskrypcja) =>
      fetch("/api/push/subscriptions", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(subskrypcja.toJSON()),
      }),
    ),
  );
});
