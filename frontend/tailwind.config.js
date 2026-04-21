/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Menlo", "monospace"],
      },
      colors: {
        navy: {
          950: "#050c1a",
          900: "#0a1628",
          800: "#0f2040",
          700: "#162d57",
        },
      },
    },
  },
  plugins: [],
};
