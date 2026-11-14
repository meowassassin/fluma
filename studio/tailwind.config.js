// ArtCraft 부품(영상 편집기 + src/vendor/artcraft/** 공용 부품 · 무드보드 · 2D · 3D) 전용 Tailwind — 하나의 범위 시스템.
// - content 를 ArtCraft 폴더로만 좁히고, preflight(전역 초기화)를 꺼서 기존 Fluma 화면 스타일을 건드리지 않는다.
// - important: ".ac-root" 또는 ".ve-root" 안에서만 유틸리티가 이긴다. Radix/headless 포털은 body 에 붙으므로
//   호스트 화면은 떠 있는 동안 document.body 에 ac-root(편집기는 ve-root) 클래스를 단다 — src/vendor/artcraft/ORIGIN.md 참고.
// - 키는 ArtCraft 원본 tailwind.config.ts 와 같게, 값은 Fluma 색(shadcn hsl 변수). 변수 값: .ac-root · .ve-root 공통
//   → src/vendor/artcraft/_theme/artcraft-fluma.css (편집기만의 글꼴 · 화면 틀은 src/features/veditor/veditor.css).
import plugin from "tailwindcss/plugin.js";

// Fluma 보라 단계(500 = --primary #5850f8, 400 = --brand #8b80ff)
const flumaPurple = {
  50: "#f2f1ff", 100: "#e4e2ff", 200: "#ccc8ff", 300: "#aba3ff", 400: "#8b80ff", 500: "#5850f8",
  600: "#4a41e0", 700: "#3d35bd", 800: "#332d98", 900: "#2c2878", 950: "#1b1847",
};
// Fluma 회색 단계(VS Code 다크 계열; 950 = --bg-3)
const flumaGray = {
  50: "#f5f5f5", 100: "#e2e2e2", 200: "#cccccc", 300: "#a6a6a6", 400: "#8a8a8a", 500: "#6e6e6e",
  600: "#555555", 700: "#45454a", 800: "#3c3c42", 900: "#333337", 950: "#2d2d2d",
};
const hsl = (v) => `hsl(var(--${v}) / <alpha-value>)`;
// ArtCraft 타임라인 색(원본 키 그대로) — 값은 Fluma 톤으로 채도를 낮춤
const track = (unselected, selected, clip, groupBg, titleBg) => ({ unselected, selected, clip, groupBg, titleBg });

export default {
  content: [
    "./src/features/veditor/**/*.{ts,tsx}",
    "./src/vendor/artcraft/**/*.{ts,tsx}",
    "./src/features/artcraft-dev/**/*.{ts,tsx}",
  ],
  important: ":is(.ac-root, .ve-root)",
  corePlugins: { preflight: false },
  theme: {
    extend: {
      fontFamily: {
        sans: ["Pretendard", "system-ui", "sans-serif"],
        mono: ["Geist Mono", "ui-monospace", "monospace"],
        // ArtCraft 의 display(Archivo) → Fluma 제목 글꼴
        display: ["Wanted Sans", "Pretendard", "system-ui", "sans-serif"],
        "custom-font": ["Pretendard", "system-ui", "sans-serif"],
      },
      colors: {
        background: "hsl(var(--background) / <alpha-value>)", foreground: "hsl(var(--foreground) / <alpha-value>)",
        card: { DEFAULT: "hsl(var(--card) / <alpha-value>)", foreground: "hsl(var(--card-foreground) / <alpha-value>)" },
        popover: { DEFAULT: "hsl(var(--popover) / <alpha-value>)", foreground: "hsl(var(--popover-foreground) / <alpha-value>)" },
        primary: { DEFAULT: "hsl(var(--primary) / <alpha-value>)", foreground: "hsl(var(--primary-foreground) / <alpha-value>)", hover: "#655cff", ...flumaPurple },
        secondary: { DEFAULT: "hsl(var(--secondary) / <alpha-value>)", foreground: "hsl(var(--secondary-foreground) / <alpha-value>)", ...flumaGray },
        muted: { DEFAULT: "hsl(var(--muted) / <alpha-value>)", foreground: "hsl(var(--muted-foreground) / <alpha-value>)" },
        accent: { DEFAULT: "hsl(var(--accent) / <alpha-value>)", foreground: "hsl(var(--accent-foreground) / <alpha-value>)" },
        destructive: { DEFAULT: "hsl(var(--destructive) / <alpha-value>)", foreground: "hsl(var(--destructive-foreground) / <alpha-value>)" },
        border: "hsl(var(--border) / <alpha-value>)", input: "hsl(var(--input) / <alpha-value>)", ring: "hsl(var(--ring) / <alpha-value>)",
        // 편집기 원본이 쓰는 추가 토큰(Tailwind 4 테마에만 있던 것) — 없으면 클래스가 비어 테두리 · 강조색이 사라진다
        "popover-hover": "hsl(var(--popover-hover) / <alpha-value>)",
        "secondary-border": "hsl(var(--border) / <alpha-value>)",
        caution: "hsl(var(--caution) / <alpha-value>)",
        constructive: "hsl(var(--constructive) / <alpha-value>)",
        "primary-foreground": hsl("primary-foreground"),
        "secondary-foreground": hsl("secondary-foreground"),
        ui: {
          panel: "hsl(var(--card) / <alpha-value>)",
          "panel-bg": "hsl(var(--card) / <alpha-value>)",
          "panel-border": "hsl(var(--border) / <alpha-value>)",
          fg: "hsl(var(--foreground) / <alpha-value>)",
          controls: "hsl(var(--muted) / <alpha-value>)",
          "controls-border": "hsl(var(--border) / <alpha-value>)",
          // ArtCraft 원본 ui.* 키(값은 같은 shadcn 변수로)
          background: hsl("background"),
          border: hsl("border"),
          "controls-button": hsl("muted"),
          divider: hsl("border"),
          ink: hsl("foreground"),
          "accent-ink": "#8b80ff",
          sunken: "#181818",
          // 원본에선 base.css 의 일반 클래스(.bg-ui-modal) — 알파 수식(/60)을 쓰려고 색 키로도 둔다
          modal: hsl("card"),
        },
        "base-fg": hsl("foreground"),
        "brand-primary": { DEFAULT: "#5850f8", ...flumaPurple },
        "brand-secondary": { DEFAULT: "#333337", ...flumaGray },
        "brand-tertiary": { DEFAULT: "#2dd4bf", 50: "#effefb", 100: "#c8fff4", 200: "#92fee9", 300: "#53f5db", 400: "#2dd4bf", 500: "#14b8a6", 600: "#0e9488", 700: "#11766e", 800: "#135e59", 900: "#154e4a", 950: "#052e2d" },
        action: { DEFAULT: "#333337", ...flumaGray },
        danger: { DEFAULT: "#f2555a", 50: "#fef2f2", 100: "#fde3e4", 200: "#fbcdce", 300: "#f8a9ab", 400: "#f47b7e", 500: "#f2555a", 600: "#de3238", 700: "#bb252b", 800: "#9b2227", 900: "#812326", 950: "#460d0f" },
        success: { DEFAULT: "#3ccb7f", 50: "#effcf4", 100: "#d9f7e4", 200: "#b5eecc", 300: "#83e0ac", 400: "#3ccb7f", 500: "#25b067", 600: "#188e52", 700: "#167144", 800: "#165a38", 900: "#134a30", 950: "#082919" },
        // pagescene 이 쓰는 error-* (원본 설정엔 없어 무효였던 키) → danger 와 같은 값
        error: { 400: "#f47b7e", 500: "#f2555a", 600: "#de3238" },
        red: { DEFAULT: "#f2555a" },
        green: { DEFAULT: "#3ccb7f" },
        blue: { DEFAULT: "#38bdf8" },
        character: { ...track("#3f466b", "#8b80ff", "#7268e0", "#2a2c3d", "#363a55"), frame: "#7268e0" },
        camera: track("#3b5a63", "#38bdf8", "#4f8fa3", "#26333a", "#304750"),
        global_audio: track("#6b3f58", "#e070a8", "#c86a98", "#33262f", "#4a3443"),
        object: track("#6b4c3e", "#f5a524", "#c88f5c", "#332b28", "#4a3d36"),
        prompt: track("#4d3f72", "#a99bff", "#8b80ff", "#2f2943", "#463b66"),
        keyframe: { unselected: "#e2e2e2", selected: "#f5a524" },
        assets: { background: "#252526", selectedTab: "#333337" },
        dnd: { canDrop: "#2f7d5a", canDropBorder: "#3ccb7f", timeGrid: "#4f4aa8", timeGridBorder: "#8b80ff", cannotDrop: "#8a3a3d", wrapper: "#2d2d33" },
        media: { "audio-tts": "#3ccb7f", "audio-v2v": "#38bdf8", "audio-upload": "#8b80ff", "audio-demo": "#f2555a", "is-new": "#f5a524" },
        inference: { pending: "#6e6e6e", generating: "#5850f8", error: "#f2555a" },
        "axis-x": "#f2555a",
        "axis-y": "#3ccb7f",
        "axis-z": "#38bdf8",
        facebook: "#4267b2", reddit: "#ff5700", whatsapp: "#25d366", x: "#000000", email: "#858585",
      },
      // Tailwind 4 기본값에만 있던 키(ArtCraft 부품이 씀)
      spacing: { 4.5: "1.125rem", 6.5: "1.625rem", 18: "4.5rem" },
      opacity: { 2: "0.02", 3: "0.03", 4: "0.04", 6: "0.06", 7: "0.07", 8: "0.08", 12: "0.12", 35: "0.35", 45: "0.45", 55: "0.55", 65: "0.65", 85: "0.85" },
      zIndex: { 60: "60", 70: "70", 100: "100", 200: "200", 250: "250", 9999: "9999" },
      boxShadow: { xs: "0 1px 2px 0 rgb(0 0 0 / 0.05)", "2xs": "0 1px rgb(0 0 0 / 0.05)", pop: "var(--shadow-pop)", modal: "var(--shadow-modal)" },
      borderRadius: { xs: "0.125rem", lg: "var(--radius)", md: "calc(var(--radius) - 2px)", sm: "calc(var(--radius) - 4px)" },
      keyframes: {
        fadeIn: { "0%": { opacity: "0" }, "100%": { opacity: "1" } },
        shimmer: { "0%": { backgroundPosition: "200% 0" }, "100%": { backgroundPosition: "-200% 0" } },
        marquee: { "0%": { transform: "translateX(0%)" }, "100%": { transform: "translateX(-100%)" } },
      },
      animation: {
        fadeIn: "fadeIn 0.2s ease-in-out",
        shimmer: "shimmer 2s ease-in-out infinite",
        marquee: "marquee 8s linear infinite paused",
      },
    },
  },
  safelist: [
    "lucide",
    // ArtCraft 원본 safelist(동적으로 조합되는 타임라인 색)
    { pattern: /^bg-(character|camera|global_audio|object|prompt)-(selected|unselected|clip)$/ },
    { pattern: /^bg-(facebook|reddit|whatsapp|x|email)$/ },
  ],
  plugins: [
    // Tailwind 4 문법 호환: outline-hidden · bg-linear-to-* · text-shadow-*
    plugin(({ addUtilities, matchUtilities }) => {
      addUtilities({ ".outline-hidden": { outline: "2px solid transparent", "outline-offset": "2px" } });
      const dirs = { t: "to top", tr: "to top right", r: "to right", br: "to bottom right", b: "to bottom", bl: "to bottom left", l: "to left", tl: "to top left" };
      addUtilities(Object.fromEntries(Object.entries(dirs).map(([k, v]) => [`.bg-linear-to-${k}`, { "background-image": `linear-gradient(${v}, var(--tw-gradient-stops))` }])));
      matchUtilities(
        { "text-shadow": (value) => ({ "text-shadow": value }) },
        { values: { sm: "0 1px 2px rgb(0 0 0 / 0.35)", DEFAULT: "0 1px 3px rgb(0 0 0 / 0.45)", md: "0 2px 6px rgb(0 0 0 / 0.5)", lg: "0 4px 14px rgb(0 0 0 / 0.55)", none: "none" } },
      );
    }),
  ],
};
