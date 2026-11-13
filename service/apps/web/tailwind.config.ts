import type { Config } from "tailwindcss";

// 색상은 CSS 변수(src/app/globals.css)로만 정의한다. 하드코딩 색상 금지(README 14.5).
const token = (name: string) => `rgb(var(--${name}) / <alpha-value>)`;

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    screens: { sm: "640px", md: "768px", lg: "1024px", xl: "1280px", "2xl": "1536px" },
    colors: {
      transparent: "transparent",
      current: "currentColor",
      white: "rgb(255 255 255 / <alpha-value>)",
      bg: token("bg"),
      subtle: token("bg-subtle"),
      surface: token("surface"),
      border: token("border"),
      "border-strong": token("border-strong"),
      text: token("text"),
      muted: token("text-muted"),
      primary: { DEFAULT: token("primary"), hover: token("primary-hover"), fg: token("primary-fg"), soft: token("primary-soft") },
      human: { DEFAULT: token("human"), soft: token("human-soft") },
      ai: { DEFAULT: token("ai"), soft: token("ai-soft") },
      uncertain: { DEFAULT: token("uncertain"), soft: token("uncertain-soft") },
      warning: { DEFAULT: token("warning"), soft: token("warning-soft") },
      danger: { DEFAULT: token("danger"), soft: token("danger-soft") },
      success: { DEFAULT: token("success"), soft: token("success-soft") },
      star: token("star"),
    },
    fontFamily: {
      sans: ["var(--font-pretendard)", "Pretendard", "-apple-system", "BlinkMacSystemFont", "system-ui", "Apple SD Gothic Neo", "Noto Sans KR", "sans-serif"],
    },
    // 타이포 스케일 6단계만 사용 (Display / H1 / H2 / H3 / Body / Caption)
    fontSize: {
      caption: ["0.875rem", { lineHeight: "1.375rem" }],
      body: ["1.0625rem", { lineHeight: "1.75rem" }],
      h3: ["1.25rem", { lineHeight: "1.75rem", fontWeight: "700" }],
      h2: ["1.75rem", { lineHeight: "2.375rem", fontWeight: "700", letterSpacing: "-0.01em" }],
      h1: ["2.5rem", { lineHeight: "3.25rem", fontWeight: "800", letterSpacing: "-0.02em" }],
      display: ["3.5rem", { lineHeight: "4.25rem", fontWeight: "800", letterSpacing: "-0.03em" }],
    },
    borderRadius: { none: "0", sm: "8px", DEFAULT: "12px", lg: "12px", xl: "16px", full: "9999px" },
    boxShadow: { none: "none", card: "0 1px 2px rgb(var(--shadow) / 0.06), 0 4px 16px rgb(var(--shadow) / 0.05)" },
    extend: {
      maxWidth: { content: "72rem", prose: "44rem" },
      transitionDuration: { DEFAULT: "200ms" },
      keyframes: {
        "fade-in": { from: { opacity: "0", transform: "translateY(4px)" }, to: { opacity: "1", transform: "none" } },
      },
      animation: { "fade-in": "fade-in 200ms ease-out both" },
    },
  },
  plugins: [],
};

export default config;
