import type { Config } from "tailwindcss";
import tailwindAnimate from "tailwindcss-animate";
import tailwindTypography from "@tailwindcss/typography";

export default {
  darkMode: ["class"],
  content: ["./index.html", "./pages/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./app/**/*.{ts,tsx}", "./src/**/*.{ts,tsx}"],
  prefix: "",
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: {
        "2xl": "1400px",
      },
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
        // Sacred Energy Colors
        ojas: {
          DEFAULT: "hsl(var(--ojas-gold))",
          light: "hsl(var(--ojas-gold-light))",
          dark: "hsl(var(--ojas-gold-dark))",
        },
        tejas: {
          DEFAULT: "hsl(var(--tejas-white))",
          glow: "hsl(var(--tejas-glow))",
        },
        prana: {
          DEFAULT: "hsl(var(--prana-blue))",
          light: "hsl(var(--prana-blue-light))",
          dark: "hsl(var(--prana-blue-dark))",
        },
        // Serene UI design tokens (namespaced to avoid collisions)
        serene: {
          primary: "#D4A574",
          secondary: "#7B9E87",
          accent: "#C9A96E",
          background: "#FAF7F2",
          surface: "#FFFFFF",
          textPrimary: "#2C2420",
          textSecondary: "#6B5E54",
          textMuted: "#9B8E84",
          border: "#E8E0D8",
          error: "#C47065",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
        display: ['Outfit', 'sans-serif'],
        serif: ['Playfair Display', 'serif'],
        mono: ['JetBrains Mono', 'monospace'],
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
        "fade-in": {
          "0%": { opacity: "0", transform: "translateY(10px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "fade-in-up": {
          "0%": { opacity: "0", transform: "translateY(30px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "scale-in": {
          "0%": { transform: "scale(0.95)", opacity: "0" },
          "100%": { transform: "scale(1)", opacity: "1" },
        },
        "slide-in-right": {
          "0%": { transform: "translateX(20px)", opacity: "0" },
          "100%": { transform: "translateX(0)", opacity: "1" },
        },
        "lotus-bloom": {
          "0%": { transform: "rotateX(60deg) scale(0.8)", opacity: "0" },
          "50%": { transform: "rotateX(20deg) scale(1.05)" },
          "100%": { transform: "rotateX(0deg) scale(1)", opacity: "1" },
        },
        "petal-sway": {
          "0%, 100%": { transform: "rotateY(-3deg) rotateX(2deg)" },
          "50%": { transform: "rotateY(3deg) rotateX(-2deg)" },
        },
        "voice-pulse": {
          "0%, 100%": { transform: "scale(1)", opacity: "0.5" },
          "50%": { transform: "scale(1.3)", opacity: "0" },
        },
        // Serene UI keyframes
        breathe: {
          "0%, 100%": { transform: "scale(1)" },
          "50%": { transform: "scale(1.02)" },
        },
        "pulse-soft": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.7" },
        },
        "slide-up": {
          "0%": { transform: "translateY(20px)", opacity: "0" },
          "100%": { transform: "translateY(0)", opacity: "1" },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
        "fade-in": "fade-in 0.5s ease-out forwards",
        "fade-in-up": "fade-in-up 0.7s ease-out forwards",
        "scale-in": "scale-in 0.3s ease-out forwards",
        "slide-in-right": "slide-in-right 0.4s ease-out forwards",
        "lotus-bloom": "lotus-bloom 1.5s ease-out forwards",
        "petal-sway": "petal-sway 4s ease-in-out infinite",
        "voice-pulse": "voice-pulse 1.5s ease-in-out infinite",
        // Serene UI animations
        breathe: "breathe 4s ease-in-out infinite",
        "pulse-soft": "pulse-soft 2s ease-in-out infinite",
        "slide-up": "slide-up 0.4s cubic-bezier(0.16, 1, 0.3, 1)",
      },
    },
  },
  plugins: [tailwindAnimate, tailwindTypography],
} satisfies Config;
