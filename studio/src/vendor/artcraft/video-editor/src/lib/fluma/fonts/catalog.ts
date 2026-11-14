// fluma: curated font catalog (replaces the upstream atlas-based list, whose
// sprite assets are not shipped). "local" fonts are served by the host
// (@font-face in veditor.css / public/fonts); "google" fonts load on demand
// from Google Fonts css2 — Korean families are split into unicode-range
// subsets, so we always load with the actual text (see font-loader.ts).

export type FontCategoryKey =
  | "ko-sans"
  | "ko-serif"
  | "ko-display"
  | "ko-hand"
  | "en-sans"
  | "en-serif"
  | "en-display"
  | "en-script"
  | "mono";

export interface CatalogFont {
  family: string;
  /** Korean display name (optional). */
  label?: string;
  category: FontCategoryKey;
  source: "local" | "google" | "system";
  /** Weights the family really has (used for the weight dropdown). */
  weights: number[];
}

export const FONT_CATEGORY_LABELS: Record<FontCategoryKey, string> = {
  "ko-sans": "한글 고딕",
  "ko-serif": "한글 명조",
  "ko-display": "한글 제목 · 디스플레이",
  "ko-hand": "한글 손글씨",
  "en-sans": "영문 산세리프",
  "en-serif": "영문 세리프",
  "en-display": "영문 디스플레이",
  "en-script": "영문 필기체",
  mono: "고정폭 · 코드",
};

const R = [400];
const RB = [400, 700];
const VAR = [100, 200, 300, 400, 500, 600, 700, 800, 900];

function g(
  family: string,
  category: FontCategoryKey,
  weights: number[] = R,
  label?: string,
): CatalogFont {
  return { family, category, source: "google", weights, label };
}

export const FONT_CATALOG: CatalogFont[] = [
  // ── 한글 고딕 ──
  { family: "Pretendard", label: "프리텐다드", category: "ko-sans", source: "local", weights: [400, 500, 600, 700, 800, 900] },
  g("Noto Sans KR", "ko-sans", VAR, "본고딕 (Noto Sans KR)"),
  g("Nanum Gothic", "ko-sans", [400, 700, 800], "나눔고딕"),
  g("IBM Plex Sans KR", "ko-sans", [100, 200, 300, 400, 500, 600, 700], "IBM Plex Sans KR"),
  g("Gothic A1", "ko-sans", VAR, "고딕 A1"),
  g("Gowun Dodum", "ko-sans", R, "고운돋움"),
  g("Sunflower", "ko-sans", [300, 500, 700], "해바라기"),
  g("Orbit", "ko-sans", R, "오르빗"),
  g("Nanum Gothic Coding", "ko-sans", RB, "나눔고딕코딩"),
  // ── 한글 명조 ──
  g("Noto Serif KR", "ko-serif", [200, 300, 400, 500, 600, 700, 800, 900], "본명조 (Noto Serif KR)"),
  g("Nanum Myeongjo", "ko-serif", [400, 700, 800], "나눔명조"),
  g("Gowun Batang", "ko-serif", RB, "고운바탕"),
  g("Hahmlet", "ko-serif", VAR, "함렛"),
  g("Song Myung", "ko-serif", R, "송명"),
  g("Diphylleia", "ko-serif", R, "디필레이아"),
  // ── 한글 제목 · 디스플레이 ──
  { family: "Black Han Sans", label: "검은고딕", category: "ko-display", source: "local", weights: R },
  g("Do Hyeon", "ko-display", R, "도현"),
  g("Jua", "ko-display", R, "주아"),
  g("Gugi", "ko-display", R, "구기"),
  g("Gasoek One", "ko-display", R, "가석"),
  g("Bagel Fat One", "ko-display", R, "베이글"),
  g("Dongle", "ko-display", [300, 400, 700], "동글"),
  g("Stylish", "ko-display", R, "스타일리시"),
  g("Black And White Picture", "ko-display", R, "흑백사진"),
  g("Kirang Haerang", "ko-display", R, "기랑해랑"),
  g("Moirai One", "ko-display", R, "모이라이"),
  g("Grandiflora One", "ko-display", R, "그랜디플로라"),
  g("Yeon Sung", "ko-display", R, "연성"),
  g("Cute Font", "ko-display", R, "귀여운 글꼴"),
  // ── 한글 손글씨 ──
  g("Nanum Pen Script", "ko-hand", R, "나눔손글씨 펜"),
  g("Nanum Brush Script", "ko-hand", R, "나눔손글씨 붓"),
  g("Gaegu", "ko-hand", [300, 400, 700], "개구"),
  g("Hi Melody", "ko-hand", R, "하이멜로디"),
  g("Poor Story", "ko-hand", R, "푸어스토리"),
  g("East Sea Dokdo", "ko-hand", R, "동해독도"),
  g("Dokdo", "ko-hand", R, "독도"),
  g("Gamja Flower", "ko-hand", R, "감자꽃"),
  g("Single Day", "ko-hand", R, "싱글데이"),
  // ── 영문 산세리프 ──
  g("Inter", "en-sans", VAR),
  g("Roboto", "en-sans", [100, 300, 400, 500, 700, 900]),
  g("Montserrat", "en-sans", VAR),
  g("Poppins", "en-sans", VAR),
  g("Open Sans", "en-sans", [300, 400, 500, 600, 700, 800]),
  g("Lato", "en-sans", [100, 300, 400, 700, 900]),
  g("Raleway", "en-sans", VAR),
  g("Nunito", "en-sans", [200, 300, 400, 500, 600, 700, 800, 900]),
  g("Rubik", "en-sans", [300, 400, 500, 600, 700, 800, 900]),
  g("Work Sans", "en-sans", VAR),
  g("Manrope", "en-sans", [200, 300, 400, 500, 600, 700, 800]),
  g("Outfit", "en-sans", VAR),
  g("Sora", "en-sans", [100, 200, 300, 400, 500, 600, 700, 800]),
  g("Space Grotesk", "en-sans", [300, 400, 500, 600, 700]),
  g("Kanit", "en-sans", VAR),
  g("Barlow Condensed", "en-sans", VAR),
  g("Oswald", "en-sans", [200, 300, 400, 500, 600, 700]),
  g("Archivo", "en-sans", VAR),
  g("Syne", "en-sans", [400, 500, 600, 700, 800]),
  g("Fredoka", "en-sans", [300, 400, 500, 600, 700]),
  g("Comfortaa", "en-sans", [300, 400, 500, 600, 700]),
  { family: "Geist", category: "en-sans", source: "local", weights: R },
  // ── 영문 세리프 ──
  g("Playfair Display", "en-serif", [400, 500, 600, 700, 800, 900]),
  g("Merriweather", "en-serif", [300, 400, 700, 900]),
  g("Lora", "en-serif", [400, 500, 600, 700]),
  g("EB Garamond", "en-serif", [400, 500, 600, 700, 800]),
  g("Cormorant Garamond", "en-serif", [300, 400, 500, 600, 700]),
  g("Libre Baskerville", "en-serif", RB),
  g("DM Serif Display", "en-serif", R),
  g("Crimson Text", "en-serif", [400, 600, 700]),
  g("Roboto Slab", "en-serif", VAR),
  g("Zilla Slab", "en-serif", [300, 400, 500, 600, 700]),
  g("Arvo", "en-serif", RB),
  g("Bitter", "en-serif", VAR),
  g("Cinzel", "en-serif", [400, 500, 600, 700, 800, 900]),
  // ── 영문 디스플레이 ──
  g("Anton", "en-display"),
  g("Bebas Neue", "en-display"),
  g("Archivo Black", "en-display"),
  g("Bungee", "en-display"),
  g("Bungee Shade", "en-display"),
  g("Bangers", "en-display"),
  g("Luckiest Guy", "en-display"),
  g("Titan One", "en-display"),
  g("Bowlby One", "en-display"),
  g("Alfa Slab One", "en-display"),
  g("Abril Fatface", "en-display"),
  g("Righteous", "en-display"),
  g("Russo One", "en-display"),
  g("Black Ops One", "en-display"),
  g("Fjalla One", "en-display"),
  g("Teko", "en-display", [300, 400, 500, 600, 700]),
  g("Unbounded", "en-display", [200, 300, 400, 500, 600, 700, 800, 900]),
  g("Rubik Mono One", "en-display"),
  g("Monoton", "en-display"),
  g("Orbitron", "en-display", [400, 500, 600, 700, 800, 900]),
  g("Audiowide", "en-display"),
  g("Press Start 2P", "en-display"),
  g("Creepster", "en-display"),
  g("Nosifer", "en-display"),
  g("Special Elite", "en-display"),
  // ── 영문 필기체 ──
  g("Pacifico", "en-script"),
  g("Lobster", "en-script"),
  g("Dancing Script", "en-script", [400, 500, 600, 700]),
  g("Caveat", "en-script", [400, 500, 600, 700]),
  g("Satisfy", "en-script"),
  g("Great Vibes", "en-script"),
  g("Kaushan Script", "en-script"),
  g("Yellowtail", "en-script"),
  g("Courgette", "en-script"),
  g("Permanent Marker", "en-script"),
  g("Rock Salt", "en-script"),
  g("Shadows Into Light", "en-script"),
  g("Indie Flower", "en-script"),
  g("Amatic SC", "en-script", RB),
  g("Gloria Hallelujah", "en-script"),
  g("Patrick Hand", "en-script"),
  // ── 고정폭 ──
  { family: "Geist Mono", category: "mono", source: "local", weights: R },
  g("JetBrains Mono", "mono", [100, 200, 300, 400, 500, 600, 700, 800]),
  g("Fira Code", "mono", [300, 400, 500, 600, 700]),
  g("Space Mono", "mono", RB),
  g("IBM Plex Mono", "mono", [100, 200, 300, 400, 500, 600, 700]),
  g("Roboto Mono", "mono", [100, 200, 300, 400, 500, 600, 700]),
  g("Source Code Pro", "mono", VAR),
  g("Inconsolata", "mono", [200, 300, 400, 500, 600, 700, 800, 900]),
  g("Courier Prime", "mono", RB),
  g("VT323", "mono"),
];

const BY_FAMILY = new Map(FONT_CATALOG.map((font) => [font.family, font]));

export function getCatalogFont(family: string): CatalogFont | undefined {
  return BY_FAMILY.get(family);
}

export function getFontLabel(family: string): string {
  return BY_FAMILY.get(family)?.label ?? family;
}

export function getFontWeights(family: string): number[] {
  return BY_FAMILY.get(family)?.weights ?? [400, 700];
}
