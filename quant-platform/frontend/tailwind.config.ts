import type { Config } from "tailwindcss";

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: { 950: "#07090c", 900: "#0b0f14", 850: "#10151c", 800: "#151b24", 700: "#1f2733", 600: "#2b3544" },
        accent: "#f5a524",
        up: "#22c55e",
        down: "#ef4444",
      },
      fontFamily: { mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"] },
    },
  },
  plugins: [],
} satisfies Config;
