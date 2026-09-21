/** Formularze logowania, rejestracji i zmiany hasła (komponenty Alpine.js). */
(function () {
  "use strict";
  const { api, toast } = window.MTQuiz;

  function authForm(isRegister, nextUrl) {
    return {
      isRegister,
      nextUrl: nextUrl || "/pulpit",
      busy: false,
      error: "",
      showPassword: false,
      form: { username: "", email: "", password: "", remember: true },

      async submit() {
        this.error = "";
        if (this.form.password.length < 8 && this.isRegister) {
          this.error = "Hasło musi mieć co najmniej 8 znaków.";
          return;
        }
        this.busy = true;
        try {
          if (this.isRegister) {
            const body = { username: this.form.username.trim(), password: this.form.password };
            if (this.form.email.trim()) body.email = this.form.email.trim();
            await api.post("/api/auth/register", body);
          } else {
            await api.post("/api/auth/login", {
              username: this.form.username.trim(),
              password: this.form.password,
              remember: this.form.remember,
            });
          }
          window.location.href = this.nextUrl;
        } catch (error) {
          this.error = error.message || "Nie udało się zalogować.";
        } finally {
          this.busy = false;
        }
      },
    };
  }

  function scorePassword(value) {
    if (!value) return 0;
    let score = Math.min(40, value.length * 4);
    if (/[a-z]/.test(value) && /[A-Z]/.test(value)) score += 15;
    if (/\d/.test(value)) score += 15;
    if (/[^\w\s]/.test(value)) score += 20;
    if (value.length >= 14) score += 10;
    return Math.min(100, score);
  }

  function passwordForm(forced) {
    return {
      forced,
      busy: false,
      error: "",
      form: { current_password: "", new_password: "", repeat: "" },

      get strength() {
        return scorePassword(this.form.new_password);
      },
      get strengthLabel() {
        const value = this.strength;
        if (!this.form.new_password) return "Minimum 8 znaków. Użyj liter, cyfr i znaku specjalnego.";
        if (value < 40) return "Siła hasła: słabe";
        if (value < 70) return "Siła hasła: przeciętne";
        return "Siła hasła: mocne";
      },
      get strengthClass() {
        const value = this.strength;
        if (value < 40) return "bg-rose-500";
        if (value < 70) return "bg-amber-500";
        return "bg-emerald-500";
      },

      async submit() {
        this.error = "";
        if (this.form.new_password !== this.form.repeat) {
          this.error = "Powtórzone hasło nie jest identyczne.";
          return;
        }
        if (this.form.new_password.length < 8) {
          this.error = "Nowe hasło musi mieć co najmniej 8 znaków.";
          return;
        }
        this.busy = true;
        try {
          await api.post("/api/auth/change-password", {
            current_password: this.form.current_password,
            new_password: this.form.new_password,
          });
          toast("Hasło zostało zmienione.", "success");
          window.setTimeout(() => {
            window.location.href = "/pulpit";
          }, 600);
        } catch (error) {
          this.error = error.message || "Nie udało się zmienić hasła.";
        } finally {
          this.busy = false;
        }
      },
    };
  }

  window.authForm = authForm;
  window.passwordForm = passwordForm;
})();
