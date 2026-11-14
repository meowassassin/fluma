import { BaseNode } from "./base-node";
import type { TextElement } from "../../../timeline/types";
import type { EffectPass } from "../../../effects/types";
import type { BlendMode, Transform } from "../../../rendering";
import {
  drawMeasuredTextLayout,
  type TextShadowStyle,
  type TextStrokeStyle,
} from "../../../text/primitives";
import type { MeasuredTextElement } from "../../../text/measure-element";

export type TextNodeParams = TextElement & {
  transform: Transform;
  opacity: number;
  blendMode?: BlendMode;
  canvasCenter: { x: number; y: number };
  canvasHeight: number;
  textBaseline?: CanvasTextBaseline;
};

export interface ResolvedTextNodeState {
  transform: Transform;
  opacity: number;
  textColor: string;
  backgroundColor: string;
  effectPasses: EffectPass[][];
  measuredText: MeasuredTextElement;
}

export class TextNode extends BaseNode<TextNodeParams, ResolvedTextNodeState> {}

export function renderTextToContext({
  node,
  ctx,
}: {
  node: TextNode;
  ctx: CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D;
}): void {
  const resolved = node.resolved;
  if (!resolved) {
    return;
  }

  const x = resolved.transform.position.x + node.params.canvasCenter.x;
  const y = resolved.transform.position.y + node.params.canvasCenter.y;
  const baseline = node.params.textBaseline ?? "middle";

  ctx.save();
  ctx.translate(x, y);
  ctx.scale(resolved.transform.scaleX, resolved.transform.scaleY);
  if (resolved.transform.rotate) {
    ctx.rotate((resolved.transform.rotate * Math.PI) / 180);
  }
  // fluma: slant (skewX, degrees). Positive leans the glyph tops right, like italics.
  const skew = readNumber(node.params.params, "skewX", 0);
  if (skew) {
    ctx.transform(1, 0, -Math.tan((Math.max(-60, Math.min(60, skew)) * Math.PI) / 180), 1, 0, 0);
  }

  const fontPx = resolved.measuredText.scaledFontSize;
  const params = node.params.params;
  const stroke: TextStrokeStyle | null =
    params["stroke.enabled"] === true
      ? {
          color: readString(params, "stroke.color", "#000000"),
          width: (readNumber(params, "stroke.width", 8) / 100) * fontPx,
        }
      : null;
  const shadowScale = Math.abs(resolved.transform.scaleY) || 1;
  const shadow: TextShadowStyle | null =
    params["shadow.enabled"] === true
      ? {
          color: readString(params, "shadow.color", "#000000b3"),
          blur: (readNumber(params, "shadow.blur", 15) / 100) * fontPx * shadowScale,
          offsetX: (readNumber(params, "shadow.offsetX", 6) / 100) * fontPx * shadowScale,
          offsetY: (readNumber(params, "shadow.offsetY", 6) / 100) * fontPx * shadowScale,
        }
      : null;

  drawMeasuredTextLayout({
    ctx,
    layout: resolved.measuredText,
    textColor: resolved.textColor,
    background: resolved.measuredText.resolvedBackground,
    backgroundColor: resolved.backgroundColor,
    textBaseline: baseline,
    stroke,
    shadow,
  });

  ctx.restore();
}

function readNumber(params: Record<string, unknown>, key: string, fallback: number): number {
  const value = params[key];
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function readString(params: Record<string, unknown>, key: string, fallback: string): string {
  const value = params[key];
  return typeof value === "string" && value ? value : fallback;
}
