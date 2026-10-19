module.exports = {
  content: ["./app/static/index.html", "./app/static/app.js"],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        sans: ["-apple-system", "BlinkMacSystemFont", "Segoe UI", "Roboto", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Monaco", "Consolas", "monospace"],
      },
      colors: {
        brand: { 400: "#38bdf8", 500: "#0284c7", 600: "#0369a1" },
      },
    },
  },
  plugins: [],
};
