// fluma: font loading for preview AND export. Rewritten from the upstream
// atlas loader (whose /fonts/font-atlas.json sprites are not shipped and whose
// loadFonts() was never called, so non-system fonts silently fell back).
//
// - ensureFontStylesheet(family): injects the Google Fonts css2 link once.
// - requestFontsForRender(reqs): sync check used by the renderer; when a face
//   (or a Korean unicode-range subset needed by the text) is missing it starts
//   loading and bumps the fonts version when done, so the preview re-renders.
// - ensureFontsReady(reqs): awaited before export so every frame uses the
//   real fonts.
// - loadPreviewFont(family): loads a tiny glyph subset under an alias family
//   for the font picker rows.
import { getCatalogFont, getFontWeights, getFontLabel } from "./catalog";
import { SYSTEM_FONTS } from "../../fonts/system-fonts";

const GOOGLE_FONTS_CSS = "https://fonts.googleapis.com/css2";

export interface FontRequest {
  family: string;
  weight?: number | string;
  style?: string;
  text?: string;
}

const stylesheetPromises = new Map<string, Promise<void>>();
const stylesheetReady = new Set<string>();
const pendingLoads = new Set<string>();
const previewPromises = new Map<string, Promise<string>>();
let fontsVersion = 0;
const listeners = new Set<() => void>();

export function getFontsVersion(): number {
  return fontsVersion;
}

export function subscribeFontsChanged(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function bumpVersion() {
  fontsVersion++;
  for (const listener of listeners) listener();
}

function isRemote(family: string): boolean {
  const entry = getCatalogFont(family);
  if (entry) return entry.source === "google";
  // Unknown families (typed by hand / older projects): try Google unless it
  // is a generic or OS font.
  return !SYSTEM_FONTS.has(family) && !/^(sans-serif|serif|monospace|system-ui)$/i.test(family);
}

function cssUrl(family: string, extra = ""): string {
  const name = family.trim().replace(/ /g, "+");
  const weights = getFontWeights(family);
  const spec = weights.length > 1 ? `:wght@${weights.join(";")}` : "";
  return `${GOOGLE_FONTS_CSS}?family=${encodeURIComponent(name).replace(/%2B/g, "+")}${spec}&display=swap${extra}`;
}

export function ensureFontStylesheet(family: string): Promise<void> {
  if (typeof document === "undefined" || !isRemote(family)) {
    stylesheetReady.add(family);
    return Promise.resolve();
  }
  const existing = stylesheetPromises.get(family);
  if (existing) return existing;
  const promise = new Promise<void>((resolve) => {
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = cssUrl(family);
    link.dataset.flumaFont = family;
    const done = () => {
      stylesheetReady.add(family);
      resolve();
    };
    link.addEventListener("load", done, { once: true });
    link.addEventListener("error", done, { once: true });
    document.head.appendChild(link);
  });
  stylesheetPromises.set(family, promise);
  return promise;
}

export function normalizeFontWeight(weight: number | string | undefined): number {
  if (weight === undefined || weight === "normal") return 400;
  if (weight === "bold") return 700;
  const n = Number(weight);
  return Number.isFinite(n) && n > 0 ? n : 400;
}

function fontSpec(req: FontRequest): string {
  const style = req.style === "italic" ? "italic" : "normal";
  return `${style} ${normalizeFontWeight(req.weight)} 32px "${req.family.replace(/"/g, '\\"')}"`;
}

function sampleText(req: FontRequest): string {
  const text = (req.text ?? "").trim();
  return text.length > 0 ? text : "Aa가";
}

/**
 * Renderer-side check. Returns true when every requested face is ready.
 * Otherwise kicks off loading (once per face+text) and returns false; the
 * fonts version bumps when the load finishes.
 */
export function requestFontsForRender(requests: FontRequest[]): boolean {
  if (typeof document === "undefined" || !document.fonts) return true;
  let ready = true;
  for (const req of requests) {
    if (!req.family) continue;
    if (!stylesheetReady.has(req.family) && isRemote(req.family)) {
      ready = false;
      const key = `css:${req.family}`;
      if (!pendingLoads.has(key)) {
        pendingLoads.add(key);
        void ensureFontStylesheet(req.family).then(() => {
          pendingLoads.delete(key);
          bumpVersion();
        });
      }
      continue;
    }
    const spec = fontSpec(req);
    const text = sampleText(req);
    let ok = true;
    try {
      ok = document.fonts.check(spec, text);
    } catch {
      ok = true;
    }
    if (ok) continue;
    ready = false;
    const key = `${spec}|${text}`;
    if (pendingLoads.has(key)) continue;
    pendingLoads.add(key);
    void document.fonts
      .load(spec, text)
      .catch(() => [])
      .then(() => {
        pendingLoads.delete(key);
        bumpVersion();
      });
  }
  return ready;
}

/** Awaitable variant used before export / after project open. */
export async function ensureFontsReady(requests: FontRequest[]): Promise<void> {
  if (typeof document === "undefined" || !document.fonts) return;
  const families = [...new Set(requests.map((r) => r.family).filter(Boolean))];
  await Promise.all(families.map((family) => ensureFontStylesheet(family)));
  await Promise.all(
    requests
      .filter((r) => r.family)
      .map((req) =>
        Promise.race([
          document.fonts.load(fontSpec(req), sampleText(req)).catch(() => []),
          new Promise((resolve) => setTimeout(resolve, 15000)),
        ]),
      ),
  );
  bumpVersion();
}

/**
 * Loads just enough glyphs to draw `family`'s own name (plus a Korean
 * sample) under an alias family, so font picker rows render in their face
 * without pulling every full font. Resolves to the CSS family to use.
 */
export function loadPreviewFont(family: string, sample: string): Promise<string> {
  if (typeof document === "undefined" || !isRemote(family)) {
    return Promise.resolve(family);
  }
  const existing = previewPromises.get(family);
  if (existing) return existing;
  const alias = `${family} __preview`;
  const promise = fetch(cssUrl(family, `&text=${encodeURIComponent(sample)}`).replace(/:wght@[^&]*/, ""))
    .then((response) => (response.ok ? response.text() : ""))
    .then(async (css) => {
      if (!css) return family;
      const style = document.createElement("style");
      style.textContent = css.replace(/font-family:\s*'[^']*'/g, `font-family: '${alias}'`);
      document.head.appendChild(style);
      await document.fonts.load(`400 16px "${alias}"`, sample).catch(() => []);
      return alias;
    })
    .catch(() => family);
  previewPromises.set(family, promise);
  return promise;
}

export function previewSampleFor(family: string): string {
  const label = getFontLabel(family);
  return `${label} ${family} 가나다 Aa`;
}

// Upstream-compatible helpers.
export async function loadFullFont({ family }: { family: string; weights?: number[] }): Promise<void> {
  await ensureFontsReady([{ family }]);
}

export async function loadFonts({ families }: { families: string[] }): Promise<void> {
  await ensureFontsReady(families.map((family) => ({ family })));
}

/** Every font a scene needs (text elements + text masks) — awaited before export. */
export function collectFontRequests(tracks: {
  overlay: ReadonlyArray<{ elements: ReadonlyArray<unknown> }>;
  main: { elements: ReadonlyArray<unknown> };
  audio: ReadonlyArray<{ elements: ReadonlyArray<unknown> }>;
}): FontRequest[] {
  const requests: FontRequest[] = [];
  for (const track of [...tracks.overlay, tracks.main, ...tracks.audio]) {
    for (const raw of track.elements) {
      const element = raw as { type?: string; params?: Record<string, unknown>; masks?: Array<{ type?: string; params?: Record<string, unknown> }> };
      if (element.type === "text" && element.params) {
        requests.push({
          family: String(element.params.fontFamily ?? "Pretendard"),
          weight: element.params.fontWeight as string | undefined,
          style: element.params.fontStyle as string | undefined,
          text: String(element.params.content ?? ""),
        });
      }
      for (const mask of element.masks ?? []) {
        if (mask.type === "text" && mask.params?.fontFamily) {
          requests.push({ family: String(mask.params.fontFamily), text: String(mask.params.content ?? "") });
        }
      }
    }
  }
  return requests;
}
