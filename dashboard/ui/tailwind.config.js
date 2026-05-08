// dashboard/ui/tailwind.config.js
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        sidebar: "#ededf5",
        "sidebar-border": "#dddde8",
        "sidebar-active": "rgba(120,90,255,0.10)",
        accent: "#7b5cff",
        "accent-hover": "#6a4de8",
        surface: "#f6f6fa",
        card: "#ffffff",
        "card-border": "#e4e4f0",
        "text-primary": "#1a1a2e",
        "text-secondary": "#6060a0",
        "text-muted": "#9090b0",
        profit: "#16a34a",
        loss: "#dc2626",
        paper: "#2563eb",
      },
    },
  },
  plugins: [],
}
