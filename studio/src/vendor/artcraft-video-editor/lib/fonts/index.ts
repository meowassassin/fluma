// fluma: public surface for fonts — curated catalog + on-demand loader used
// by the preview renderer, the exporter and the font picker.
export { SYSTEM_FONTS } from "./system-fonts";
export {
  FONT_CATALOG,
  FONT_CATEGORY_LABELS,
  getCatalogFont,
  getFontLabel,
  getFontWeights,
} from "./catalog";
export type { CatalogFont, FontCategoryKey } from "./catalog";
export {
  ensureFontStylesheet,
  ensureFontsReady,
  requestFontsForRender,
  getFontsVersion,
  subscribeFontsChanged,
  loadPreviewFont,
  normalizeFontWeight,
  loadFullFont,
  loadFonts,
} from "./google-fonts";
export type { FontRequest } from "./google-fonts";
