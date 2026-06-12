/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: ["class"],
  content: [
    './pages/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './app/**/*.{ts,tsx}',
    './lib/**/*.{ts,tsx}',
  ],
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: { "2xl": "1400px" },
    },
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      keyframes: {
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
        "scan-line": {
          "0%": { transform: "translateY(0)", opacity: "0" },
          "10%": { opacity: "1" },
          "90%": { opacity: "1" },
          "100%": { transform: "translateY(800px)", opacity: "0" },
        },
        // UAT ロゴの光沢: 0→33%(=1.5s)で光が左→右に走り、残り(=3s)は待機。
        // 開始位置と終了位置はどちらも光沢バンドが文字外＝単色なので loop 折返しの段差は出ない。
        "logo-shine": {
          "0%": { backgroundPosition: "0% 0" },
          "33%": { backgroundPosition: "100% 0" },
          "100%": { backgroundPosition: "100% 0" },
        },
        // ウルトラマン カラータイマー: 5s サイクル、4回点滅
        "color-timer": {
          "0%":   { opacity: "1" },
          "9%":   { opacity: "0.15" },
          "18%":  { opacity: "1" },
          "27%":  { opacity: "0.15" },
          "36%":  { opacity: "1" },
          "45%":  { opacity: "0.15" },
          "54%":  { opacity: "1" },
          "63%":  { opacity: "0.15" },
          "72%":  { opacity: "1" },
          "100%": { opacity: "1" },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
        "scan-line": "scan-line 2s ease-in-out forwards",
        // sweep 1.5s + wait 3s = 4.5s 周期で無限ループ
        "logo-shine": "logo-shine 4.5s ease-in-out infinite",
        "color-timer": "color-timer 5s linear infinite",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};
