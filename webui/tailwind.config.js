/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{vue,ts}"],
  theme: {
    extend: {
      // 颜色统一映射到 CSS 变量，随 light/dark 主题切换
      colors: {
        bg: {
          base: "var(--bg-base)",
          panel: "var(--bg-panel)",
          raised: "var(--bg-raised)",
          border: "var(--bg-border)",
        },
        brand: {
          DEFAULT: "var(--accent)",
          hover: "var(--accent)",
          soft: "var(--glass-bg)",
        },
        fg: {
          DEFAULT: "var(--fg)",
          muted: "var(--fg-muted)",
          subtle: "var(--fg-subtle)",
        },
      },
      fontFamily: {
        mono: ["JetBrains Mono", "Consolas", "Menlo", "monospace"],
      },
      boxShadow: {
        glow: "var(--glass-shadow)",
      },
      keyframes: {
        "fade-in": {
          "0%": { opacity: "0", transform: "translateY(4px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "pulse-ring": {
          "0%": { boxShadow: "0 0 0 0 rgba(127,127,127,0.4)" },
          "70%": { boxShadow: "0 0 0 10px rgba(127,127,127,0)" },
          "100%": { boxShadow: "0 0 0 0 rgba(127,127,127,0)" },
        },
      },
      animation: {
        "fade-in": "fade-in 0.25s ease-out",
        "pulse-ring": "pulse-ring 1.8s infinite",
      },
    },
  },
  plugins: [],
};
