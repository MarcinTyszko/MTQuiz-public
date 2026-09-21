/** Akcje na stronie szczegółów zestawu: ulubione, kopiowanie, usuwanie. */
(function () {
  "use strict";
  const { api, toast, confirmDialog } = window.MTQuiz;

  function setActions(initial) {
    return {
      id: initial.id,
      title: initial.title,
      isFavorite: Boolean(initial.is_favorite),
      isOwner: Boolean(initial.is_owner),
      authenticated: Boolean(initial.authenticated),
      busy: false,

      async toggleFavorite() {
        if (!this.authenticated) {
          window.location.href = `/logowanie?next=/zestawy/${this.id}`;
          return;
        }
        const next = !this.isFavorite;
        this.isFavorite = next;
        try {
          if (next) await api.post(`/api/sets/${this.id}/favorite`, {});
          else await api.delete(`/api/sets/${this.id}/favorite`);
          toast(next ? "Zapisano w ulubionych." : "Usunięto z ulubionych.", "success", 2200);
        } catch (error) {
          this.isFavorite = !next;
          toast(error.message || "Operacja nie powiodła się.", "error");
        }
      },

      async fork() {
        this.busy = true;
        try {
          const clone = await api.post(`/api/sets/${this.id}/fork`, {});
          toast("Utworzono prywatną kopię zestawu.", "success");
          window.location.href = `/zestawy/${clone.id}`;
        } catch (error) {
          toast(error.message || "Nie udało się skopiować zestawu.", "error");
        } finally {
          this.busy = false;
        }
      },

      async remove() {
        const confirmed = await confirmDialog({
          title: "Usunąć zestaw?",
          message: `Zestaw „${this.title}” zostanie skasowany wraz z fiszkami, pytaniami i historią nauki. Tej operacji nie można cofnąć.`,
          confirmLabel: "Usuń zestaw",
          danger: true,
        });
        if (!confirmed) return;
        this.busy = true;
        try {
          await api.delete(`/api/sets/${this.id}`);
          window.location.href = "/pulpit";
        } catch (error) {
          toast(error.message || "Nie udało się usunąć zestawu.", "error");
          this.busy = false;
        }
      },
    };
  }

  window.setActions = setActions;
})();
