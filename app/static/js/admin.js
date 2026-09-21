/** Panel administratora: konta, moderacja, kopie zapasowe i dziennik zdarzeń. */
(function () {
  "use strict";
  const { api, toast, confirmDialog } = window.MedFiszki;

  function adminPanel() {
    return {
      tab: "users",
      tabs: [
        { key: "users", label: "Użytkownicy" },
        { key: "sets", label: "Moderacja zestawów" },
        { key: "backup", label: "Kopie zapasowe" },
        { key: "audit", label: "Dziennik zdarzeń" },
      ],
      stats: { database_path: "", database_size_bytes: 0 },
      users: [],
      sets: [],
      audit: [],
      userQuery: "",
      setQuery: "",
      onlyPublic: false,
      onlyHidden: false,
      busy: false,
      temporaryPassword: "",
      restoreFile: null,
      restoreFileName: "",

      init() {
        this.loadStats();
        this.loadUsers();
        this.loadSets();
        this.loadAudit();
      },

      get tiles() {
        const s = this.stats;
        return [
          { label: "Konta", value: s.users_total ?? 0, hint: `${s.users_active ?? 0} aktywnych · ${s.admins ?? 0} adm.` },
          { label: "Zestawy", value: s.sets_total ?? 0, hint: `${s.sets_public ?? 0} publicznych` },
          { label: "Treść", value: (s.cards_total ?? 0) + (s.questions_total ?? 0), hint: `${s.cards_total ?? 0} fiszek · ${s.questions_total ?? 0} pytań` },
          { label: "Sesje nauki", value: s.sessions_total ?? 0, hint: `Baza: ${this.formatBytes(s.database_size_bytes)}` },
        ];
      },

      formatBytes(value) {
        let size = Number(value || 0);
        const units = ["B", "KB", "MB", "GB"];
        let unit = 0;
        while (size >= 1024 && unit < units.length - 1) {
          size /= 1024;
          unit += 1;
        }
        return unit === 0 ? `${size} B` : `${size.toFixed(1)} ${units[unit]}`;
      },

      formatDate(value) {
        if (!value) return "—";
        try {
          return new Date(value).toLocaleString("pl-PL", { dateStyle: "short", timeStyle: "short" });
        } catch (error) {
          return value;
        }
      },

      async loadStats() {
        try {
          this.stats = await api.get("/api/admin/stats");
        } catch (error) {
          toast(error.message || "Nie udało się pobrać statystyk.", "error");
        }
      },

      async loadUsers() {
        try {
          const params = this.userQuery.trim() ? `?q=${encodeURIComponent(this.userQuery.trim())}` : "";
          this.users = await api.get(`/api/admin/users${params}`);
        } catch (error) {
          toast(error.message || "Nie udało się pobrać listy kont.", "error");
        }
      },

      async loadSets() {
        try {
          const params = new URLSearchParams();
          if (this.setQuery.trim()) params.set("q", this.setQuery.trim());
          if (this.onlyPublic) params.set("only_public", "true");
          if (this.onlyHidden) params.set("only_hidden", "true");
          this.sets = await api.get(`/api/admin/sets?${params.toString()}`);
        } catch (error) {
          toast(error.message || "Nie udało się pobrać zestawów.", "error");
        }
      },

      async loadAudit() {
        try {
          this.audit = await api.get("/api/admin/audit?limit=120");
        } catch (error) {
          toast(error.message || "Nie udało się pobrać dziennika.", "error");
        }
      },

      async patchUser(item, payload, successMessage) {
        try {
          const updated = await api.patch(`/api/admin/users/${item.id}`, payload);
          Object.assign(item, updated);
          if (successMessage) toast(successMessage, "success");
          this.loadStats();
        } catch (error) {
          toast(error.message || "Operacja nie powiodła się.", "error");
          this.loadUsers();
        }
      },

      toggleActive(item) {
        const next = !item.is_active;
        this.patchUser(item, { is_active: next }, next ? "Konto aktywowane." : "Konto zostało zablokowane.");
      },

      setRole(item, role) {
        if (role === item.role) return;
        this.patchUser(item, { role }, "Zmieniono uprawnienia konta.");
      },

      async resetPassword(item) {
        const confirmed = await confirmDialog({
          title: "Zresetować hasło?",
          message: `Konto „${item.username}” otrzyma hasło tymczasowe i będzie musiało ustawić nowe przy następnym logowaniu.`,
          confirmLabel: "Zresetuj hasło",
        });
        if (!confirmed) return;
        try {
          const result = await api.post(`/api/admin/users/${item.id}/reset-password`, {});
          this.temporaryPassword = result.message;
          item.must_change_password = true;
          toast("Hasło zresetowane — skopiuj hasło tymczasowe.", "success");
        } catch (error) {
          toast(error.message || "Nie udało się zresetować hasła.", "error");
        }
      },

      async deleteUser(item) {
        const confirmed = await confirmDialog({
          title: "Usunąć konto?",
          message: `Konto „${item.username}” zostanie trwale usunięte razem ze wszystkimi jego zestawami i historią nauki.`,
          confirmLabel: "Usuń konto",
          danger: true,
          requirePhrase: item.username,
        });
        if (!confirmed) return;
        try {
          await api.delete(`/api/admin/users/${item.id}`);
          this.users = this.users.filter((row) => row.id !== item.id);
          toast("Konto zostało usunięte.", "success");
          this.loadStats();
          this.loadSets();
        } catch (error) {
          toast(error.message || "Nie udało się usunąć konta.", "error");
        }
      },

      async togglePublished(item) {
        const next = !item.is_published;
        try {
          const updated = await api.patch(`/api/admin/sets/${item.id}`, { is_published: next });
          Object.assign(item, updated);
          toast(next ? "Zestaw przywrócony do bazy publicznej." : "Zestaw zdjęty z bazy publicznej.", "success");
          this.loadStats();
        } catch (error) {
          toast(error.message || "Operacja nie powiodła się.", "error");
        }
      },

      async deleteSet(item) {
        const confirmed = await confirmDialog({
          title: "Usunąć zestaw?",
          message: `Zestaw „${item.title}” (autor: ${item.author_username}) zostanie trwale usunięty.`,
          confirmLabel: "Usuń zestaw",
          danger: true,
        });
        if (!confirmed) return;
        try {
          await api.delete(`/api/admin/sets/${item.id}`);
          this.sets = this.sets.filter((row) => row.id !== item.id);
          toast("Zestaw został usunięty.", "success");
          this.loadStats();
        } catch (error) {
          toast(error.message || "Nie udało się usunąć zestawu.", "error");
        }
      },

      /** Pobiera archiwum ZIP przez fetch, aby zachować nagłówki uwierzytelnienia. */
      async downloadBackup() {
        this.busy = true;
        try {
          const response = await fetch("/api/admin/backup", { method: "POST", credentials: "same-origin" });
          if (!response.ok) {
            let detail = `Błąd ${response.status}`;
            try {
              const payload = await response.json();
              detail = payload.detail || detail;
            } catch (error) {
              /* Odpowiedź bez treści JSON. */
            }
            throw new Error(detail);
          }

          const disposition = response.headers.get("content-disposition") || "";
          const match = disposition.match(/filename="?([^"]+)"?/);
          const blob = await response.blob();
          const url = URL.createObjectURL(blob);
          const link = document.createElement("a");
          link.href = url;
          link.download = match ? match[1] : "medfiszki-backup.zip";
          document.body.appendChild(link);
          link.click();
          link.remove();
          URL.revokeObjectURL(url);
          toast("Kopia zapasowa została pobrana.", "success");
          this.loadAudit();
        } catch (error) {
          toast(error.message || "Nie udało się utworzyć kopii.", "error");
        } finally {
          this.busy = false;
        }
      },

      onRestoreFile(event) {
        const [file] = event.target.files || [];
        if (!file) return;
        this.restoreFile = file;
        this.restoreFileName = `${file.name} (${Math.max(1, Math.round(file.size / 1024))} KB)`;
      },

      async restore() {
        if (!this.restoreFile) return;
        const confirmed = await confirmDialog({
          title: "Przywrócić bazę danych?",
          message:
            "Wszystkie obecne dane zostaną zastąpione zawartością wgranego pliku. " +
            "Kopia bezpieczeństwa bieżącego stanu zapisze się automatycznie w katalogu /data/backups.",
          confirmLabel: "Przywróć bazę",
          danger: true,
          requirePhrase: "PRZYWROC",
        });
        if (!confirmed) return;

        this.busy = true;
        try {
          const form = new FormData();
          form.append("file", this.restoreFile);
          const result = await api.upload("/api/admin/restore?confirm=PRZYWROC", form);
          toast(result.message || "Baza została przywrócona.", "success", 8000);
          window.setTimeout(() => window.location.reload(), 2500);
        } catch (error) {
          toast(error.message || "Nie udało się przywrócić bazy.", "error", 8000);
        } finally {
          this.busy = false;
        }
      },
    };
  }

  window.adminPanel = adminPanel;
})();
