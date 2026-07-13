/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#141310",
          900: "#1b1a17",
          800: "#232019",
          700: "#2b271f",
          600: "#3a352a",
          500: "#5a5342",
        },
        parchment: {
          100: "#efe9df",
          300: "#c9c1b0",
          500: "#9a9284",
          700: "#6b6457",
        },
        brass: {
          400: "#e6b45c",
          500: "#d9a441",
          600: "#ad7f2f",
          900: "#3a2c14",
        },
        teal: {
          400: "#7fb3a8",
          500: "#5b8a80",
          600: "#3f635c",
        },
        rust: {
          400: "#e0796a",
          500: "#c1554c",
          600: "#94382f",
        },
        moss: {
          400: "#9bc99e",
          500: "#7fae83",
        },
      },
      fontFamily: {
        display: ["Space Grotesk", "sans-serif"],
        body: ["Inter", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
      boxShadow: {
        panel: "0 10px 30px -15px rgba(0,0,0,0.6), inset 0 1px 0 rgba(255,255,255,0.03)",
      },
    },
  },
  plugins: [],
};
