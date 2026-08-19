/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        pixel: ['Silkscreen', 'monospace'],
        mono: ['"JetBrains Mono"', 'monospace'],
        sans: ['"JetBrains Mono"', 'sans-serif'],
      },
      colors: {
        cyber: {
          black: "#000000",
          dark: "#080808",
          card: "#0d0d0d",
          gray: "#171717",
          border: "#262626",
          lightBorder: "#ffffff",
          cyan: "#00f3ff",
          mint: "#00ffcc",
          green: "#22c55e",
          amber: "#f59e0b",
          pink: "#ec4899",
          purple: "#a855f7",
        },
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
      },
      boxShadow: {
        pixel: "3px 3px 0px 0px #ffffff",
        'pixel-sm': "2px 2px 0px 0px #ffffff",
        'pixel-cyan': "3px 3px 0px 0px #00f3ff",
        'pixel-cyan-sm': "2px 2px 0px 0px #00f3ff",
        'pixel-dark': "3px 3px 0px 0px #000000",
        'glow-cyan': "0 0 15px rgba(0, 243, 255, 0.4)",
      },
    },
  },
  plugins: [],
}
