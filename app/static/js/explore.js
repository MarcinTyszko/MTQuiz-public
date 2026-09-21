/** Widok „Baza publiczna”: wyszukiwanie, sortowanie, ulubione i klonowanie. */
(function () {
  "use strict";
  const { api, toast } = window.MTQuiz;

  function exploreFeed(initial) {
    return {
      items: [],
      tags: [],
      loading: true,
      busyId: null,
      authenticated: Boolean(initial.authenticated),
      filters: { q: initial.q || "", tag: initial.tag || "", sort: initial.sort || "newest" },

      async load(withTags = false) {
        this.loading = true;
        const params = new URLSearchParams();
        if (this.filters.q.trim()) params.set("q", this.filters.q.trim());
        if (this.filters.tag) params.set("tag", this.filters.tag);
        params.set("sort", this.filters.sort);

        try {
          this.items = await api.get(`/api/public/sets?${params.toString()}`);
          if (withTags) this.tags = await api.get("/api/public/tags?limit=24");
          this.syncUrl(params);
        } catch (error) {
          toast(error.message || "Nie udało się pobrać zestawów.", "error");
          this.items = [];
        } finally {
          this.loading = false;
        }
      },

      syncUrl(params) {
        const query = params.toString();
        const url = query ? `/baza-publiczna?${query}` : "/baza-publiczna";
        window.history.replaceState({}, "", url);
      },

      setTag(tag) {
        this.filters.tag = this.filters.tag === tag ? "" : tag;
        this.load();
      },

      reset() {
        this.filters.q = "";
        this.filters.tag = "";
        this.load();
      },

      async toggleFavorite(item) {
        if (!this.authenticated) {
          window.location.href = "/logowanie?next=/baza-publiczna";
          return;
        }
        const next = !item.is_favorite;
        item.is_favorite = next;
        item.favorites_count += next ? 1 : -1;
        try {
          if (next) await api.post(`/api/sets/${item.id}/favorite`, {});
          else await api.delete(`/api/sets/${item.id}/favorite`);
          toast(next ? "Zapisano w ulubionych." : "Usunięto z ulubionych.", "success", 2200);
        } catch (error) {
          item.is_favorite = !next;
          item.favorites_count += next ? -1 : 1;
          toast(error.message || "Operacja nie powiodła się.", "error");
        }
      },

      async fork(item) {
        if (!this.authenticated) {
          window.location.href = "/logowanie?next=/baza-publiczna";
          return;
        }
        this.busyId = item.id;
        try {
          const clone = await api.post(`/api/sets/${item.id}/fork`, {});
          item.fork_count += 1;
          toast("Utworzono prywatną kopię zestawu.", "success");
          window.location.href = `/zestawy/${clone.id}/edycja`;
        } catch (error) {
          toast(error.message || "Nie udało się skopiować zestawu.", "error");
        } finally {
          this.busyId = null;
        }
      },
    };
  }

  window.exploreFeed = exploreFeed;
})();
