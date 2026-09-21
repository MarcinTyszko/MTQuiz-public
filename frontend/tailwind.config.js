/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: "class",
  content: [
    "../app/templates/**/*.html",
    "../app/static/js/**/*.js",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eef6ff",
          100: "#d9ebff",
          200: "#bcdcff",
          300: "#8ec6ff",
          400: "#59a6ff",
          500: "#3385fb",
          600: "#1d66f0",
          700: "#1651dc",
          800: "#1843b2",
          900: "#1a3c8c",
          950: "#142555",
        },
        ink: {
          50: "#f6f7f9",
          100: "#eceef2",
          200: "#d5d9e2",
          300: "#b0b8c8",
          400: "#8591a8",
          500: "#66738d",
          600: "#515c74",
          700: "#424b5f",
          800: "#394051",
          900: "#181c26",
          950: "#0e1119",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "Roboto", "Helvetica Neue", "Arial", "sans-serif"],
      },
      boxShadow: {
        card: "0 1px 2px rgba(16,24,40,.06), 0 8px 24px -12px rgba(16,24,40,.18)",
        float: "0 20px 60px -24px rgba(16,24,40,.45)",
      },
      keyframes: {
        "fade-in": { "0%": { opacity: 0, transform: "translateY(6px)" }, "100%": { opacity: 1, transform: "none" } },
        "pop-in": { "0%": { opacity: 0, transform: "scale(.96)" }, "100%": { opacity: 1, transform: "none" } },
      },
      animation: {
        "fade-in": "fade-in .25s ease-out both",
        "pop-in": "pop-in .18s ease-out both",
      },
    },
  },
  plugins: [],
};
