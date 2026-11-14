// fluma: canvas text styling — outline (stroke.*), drop shadow (shadow.*) and
// slant (skewX). Used by text/primitives.ts (draw) and
// services/renderer/nodes/text-node.ts (read params). No editor imports here
// (primitives.ts is low in the module graph).
type ShadowCtx = { shadowColor: string; shadowBlur: number; shadowOffsetX: number; shadowOffsetY: number };

/** Sets (or clears, when null) the canvas shadow. */
export function applyCanvasShadow(ctx: ShadowCtx, shadow: TextShadowStyle | null | undefined): void {
  ctx.shadowColor = shadow ? shadow.color : "transparent";
  ctx.shadowBlur = shadow ? shadow.blur : 0;
  ctx.shadowOffsetX = shadow ? shadow.offsetX : 0;
  ctx.shadowOffsetY = shadow ? shadow.offsetY : 0;
}


export interface TextStrokeStyle {
  color: string;
  width: number; // canvas px
}

export interface TextShadowStyle {
  color: string;
  blur: number; // canvas px
  offsetX: number;
  offsetY: number;
}

function readNumber(params: Record<string, unknown>, key: string, fallback: number): number {
  const value = params[key];
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function readString(params: Record<string, unknown>, key: string, fallback: string): string {
  const value = params[key];
  return typeof value === "string" && value ? value : fallback;
}

/** Applies skewX (degrees, positive leans glyph tops right like italics). */
export function applyTextSkew(ctx: { transform: (a: number, b: number, c: number, d: number, e: number, f: number) => void }, params: Record<string, unknown>): void {
  const skew = readNumber(params, "skewX", 0);
  if (!skew) return;
  ctx.transform(1, 0, -Math.tan((Math.max(-60, Math.min(60, skew)) * Math.PI) / 180), 1, 0, 0);
}

export function readTextStroke(params: Record<string, unknown>, fontPx: number): TextStrokeStyle | null {
  if (params["stroke.enabled"] !== true) return null;
  return {
    color: readString(params, "stroke.color", "#000000"),
    width: (readNumber(params, "stroke.width", 8) / 100) * fontPx,
  };
}

export function readTextShadow(params: Record<string, unknown>, fontPx: number, scale: number): TextShadowStyle | null {
  if (params["shadow.enabled"] !== true) return null;
  return {
    color: readString(params, "shadow.color", "#000000b3"),
    blur: (readNumber(params, "shadow.blur", 15) / 100) * fontPx * scale,
    offsetX: (readNumber(params, "shadow.offsetX", 6) / 100) * fontPx * scale,
    offsetY: (readNumber(params, "shadow.offsetY", 6) / 100) * fontPx * scale,
  };
}
