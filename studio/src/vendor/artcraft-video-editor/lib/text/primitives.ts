import type { TextCanvasContext, TextBlockMeasurement } from "./layout";
import { DEFAULTS } from "../timeline/defaults";
import { clamp } from "../utils/math";
import { CORNER_RADIUS_MAX, CORNER_RADIUS_MIN } from "./background";
import {
  drawTextDecoration,
  getTextBackgroundRect,
  measureTextBlock,
  setCanvasLetterSpacing,
} from "./layout";
import { FONT_SIZE_SCALE_REFERENCE } from "./typography";

// Full text-layout pipeline used by both the renderer (canvas draw)
// and the preview (hit-test bounds). Single source of truth for text
// metrics — if the renderer and the bounding box ever drift, look
// here first.

export type TextAlign = "left" | "center" | "right";
// fluma: numeric weights (100–900) in addition to normal/bold
export type TextFontWeight = "normal" | "bold" | `${number}`;
export type TextFontStyle = "normal" | "italic";
export type TextDecoration = "none" | "underline" | "line-through";

export interface TextLayoutParams {
  content: string;
  fontSize: number;
  fontFamily: string;
  fontWeight: TextFontWeight;
  fontStyle: TextFontStyle;
  textAlign: TextAlign;
  textDecoration?: TextDecoration;
  letterSpacing?: number;
  lineHeight?: number;
}

export interface ResolvedTextLayout {
  scaledFontSize: number;
  fontString: string;
  letterSpacing: number;
  lineHeightPx: number;
  fontSizeRatio: number;
  textAlign: TextAlign;
  textDecoration: TextDecoration;
}

export interface MeasuredTextLayout extends ResolvedTextLayout {
  lines: string[];
  lineMetrics: TextMetrics[];
  block: TextBlockMeasurement;
}

export interface ResolvedTextBackgroundLike {
  enabled: boolean;
  color: string;
  paddingX: number;
  paddingY: number;
  offsetX: number;
  offsetY: number;
  cornerRadius: number;
}

export function quoteFontFamily({ fontFamily }: { fontFamily: string }): string {
  return `"${fontFamily.replace(/"/g, '\\"')}"`;
}

export function buildTextFontString({
  fontFamily,
  fontWeight,
  fontStyle,
  scaledFontSize,
}: {
  fontFamily: string;
  fontWeight: TextFontWeight;
  fontStyle: TextFontStyle;
  scaledFontSize: number;
}): string {
  return `${fontStyle} ${fontWeight} ${scaledFontSize}px ${quoteFontFamily({ fontFamily })}, sans-serif`;
}

export function resolveTextLayout({
  text,
  canvasHeight,
}: {
  text: TextLayoutParams;
  canvasHeight: number;
}): ResolvedTextLayout {
  const scaledFontSize =
    text.fontSize * (canvasHeight / FONT_SIZE_SCALE_REFERENCE);
  const fontWeight = text.fontWeight ?? "normal";
  const fontStyle = text.fontStyle === "italic" ? "italic" : "normal";
  const letterSpacing = text.letterSpacing ?? DEFAULTS.text.letterSpacing;
  const lineHeightPx =
    scaledFontSize * (text.lineHeight ?? DEFAULTS.text.lineHeight);
  const fontSizeRatio = text.fontSize / 15;

  return {
    scaledFontSize,
    fontString: buildTextFontString({
      fontFamily: text.fontFamily,
      fontWeight,
      fontStyle,
      scaledFontSize,
    }),
    letterSpacing,
    lineHeightPx,
    fontSizeRatio,
    textAlign: text.textAlign,
    textDecoration: text.textDecoration ?? "none",
  };
}

export function measureTextLayout({
  text,
  canvasHeight,
  ctx,
}: {
  text: TextLayoutParams;
  canvasHeight: number;
  ctx: TextCanvasContext;
}): MeasuredTextLayout {
  const resolvedLayout = resolveTextLayout({ text, canvasHeight });
  const lines = text.content.split("\n");

  ctx.save();
  ctx.font = resolvedLayout.fontString;
  ctx.textBaseline = "middle";
  setCanvasLetterSpacing({
    ctx,
    letterSpacingPx: resolvedLayout.letterSpacing,
  });
  const lineMetrics = lines.map((line) => ctx.measureText(line));
  ctx.restore();

  const block = measureTextBlock({
    lineMetrics,
    lineHeightPx: resolvedLayout.lineHeightPx,
  });

  return {
    ...resolvedLayout,
    lines,
    lineMetrics,
    block,
  };
}

// fluma: outline + drop shadow drawn with the glyphs (preview and export
// share this function, so both get them).
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

export function drawMeasuredTextLayout({
  ctx,
  layout,
  textColor,
  background,
  backgroundColor,
  textBaseline = "middle",
  stroke,
  shadow,
}: {
  ctx: TextCanvasContext;
  layout: MeasuredTextLayout;
  textColor: string;
  background?: ResolvedTextBackgroundLike | null;
  backgroundColor?: string;
  textBaseline?: CanvasTextBaseline;
  stroke?: TextStrokeStyle | null;
  shadow?: TextShadowStyle | null;
}): void {
  ctx.font = layout.fontString;
  ctx.textAlign = layout.textAlign;
  ctx.textBaseline = textBaseline;
  ctx.fillStyle = textColor;
  setCanvasLetterSpacing({ ctx, letterSpacingPx: layout.letterSpacing });

  if (
    background?.enabled &&
    backgroundColor &&
    backgroundColor !== "transparent" &&
    layout.lines.length > 0
  ) {
    const backgroundRect = getTextBackgroundRect({
      textAlign: layout.textAlign,
      block: layout.block,
      background: {
        ...background,
        color: backgroundColor,
      },
      fontSizeRatio: layout.fontSizeRatio,
    });
    if (backgroundRect) {
      const p =
        clamp({
          value: background.cornerRadius,
          min: CORNER_RADIUS_MIN,
          max: CORNER_RADIUS_MAX,
        }) / 100;
      const radius =
        (Math.min(backgroundRect.width, backgroundRect.height) / 2) * p;
      ctx.fillStyle = backgroundColor;
      ctx.beginPath();
      ctx.roundRect(
        backgroundRect.left,
        backgroundRect.top,
        backgroundRect.width,
        backgroundRect.height,
        radius,
      );
      ctx.fill();
      ctx.fillStyle = textColor;
    }
  }

  const hasStroke = Boolean(stroke && stroke.width > 0);
  const applyShadow = () => {
    if (!shadow) return;
    ctx.shadowColor = shadow.color;
    ctx.shadowBlur = shadow.blur;
    ctx.shadowOffsetX = shadow.offsetX;
    ctx.shadowOffsetY = shadow.offsetY;
  };
  const clearShadow = () => {
    ctx.shadowColor = "transparent";
    ctx.shadowBlur = 0;
    ctx.shadowOffsetX = 0;
    ctx.shadowOffsetY = 0;
  };

  // Stroke first (outside the fill) — the shadow is cast by the outline when
  // there is one, otherwise by the glyph fill.
  if (hasStroke && stroke) {
    ctx.save();
    applyShadow();
    ctx.strokeStyle = stroke.color;
    ctx.lineWidth = stroke.width * 2;
    ctx.lineJoin = "round";
    ctx.miterLimit = 2;
    for (let index = 0; index < layout.lines.length; index++) {
      const lineY = index * layout.lineHeightPx - layout.block.visualCenterOffset;
      ctx.strokeText(layout.lines[index], 0, lineY);
    }
    ctx.restore();
  }

  for (let index = 0; index < layout.lines.length; index++) {
    const lineY = index * layout.lineHeightPx - layout.block.visualCenterOffset;
    if (!hasStroke) applyShadow();
    ctx.fillText(layout.lines[index], 0, lineY);
    clearShadow();
    drawTextDecoration({
      ctx,
      textDecoration: layout.textDecoration,
      lineWidth: layout.lineMetrics[index].width,
      lineY,
      metrics: layout.lineMetrics[index],
      scaledFontSize: layout.scaledFontSize,
      textAlign: layout.textAlign,
    });
  }
}

export function strokeMeasuredTextLayout({
  ctx,
  layout,
  strokeColor,
  strokeWidth,
  textBaseline = "middle",
}: {
  ctx: TextCanvasContext;
  layout: MeasuredTextLayout;
  strokeColor: string;
  strokeWidth: number;
  textBaseline?: CanvasTextBaseline;
}): void {
  ctx.font = layout.fontString;
  ctx.textAlign = layout.textAlign;
  ctx.textBaseline = textBaseline;
  ctx.strokeStyle = strokeColor;
  ctx.lineWidth = strokeWidth;
  ctx.lineJoin = "round";
  ctx.lineCap = "round";
  setCanvasLetterSpacing({ ctx, letterSpacingPx: layout.letterSpacing });

  for (let index = 0; index < layout.lines.length; index++) {
    const lineY = index * layout.lineHeightPx - layout.block.visualCenterOffset;
    ctx.strokeText(layout.lines[index], 0, lineY);
  }
}
