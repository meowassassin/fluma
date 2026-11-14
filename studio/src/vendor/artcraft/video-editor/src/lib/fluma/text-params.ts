// fluma: text param additions — numeric font weights, slant (skewX), outline
// (stroke.*) and drop shadow (shadow.*); Pretendard default. Applied to the
// upstream text param list in params/registry.ts (one call), drawn in
// text/primitives.ts + services/renderer/nodes/text-node.ts.
// Labels are Korean (Fluma source language); upstream English labels are
// translated by the host (features/veditor/editorKo.ts).
import type { ElementParamDefinition } from "../params/registry";

export const FLUMA_DEFAULT_FONT = "Pretendard";

export const FONT_WEIGHT_OPTIONS = [
  { value: "100", label: "100 · 가장 가늘게" },
  { value: "200", label: "200 · 아주 가늘게" },
  { value: "300", label: "300 · 가늘게" },
  { value: "normal", label: "400 · 보통" },
  { value: "500", label: "500 · 중간" },
  { value: "600", label: "600 · 약간 굵게" },
  { value: "bold", label: "700 · 굵게" },
  { value: "800", label: "800 · 아주 굵게" },
  { value: "900", label: "900 · 가장 굵게" },
];

const onlyWhen = (param: string) => [{ param, equals: true }];

const SKEW_PARAM: ElementParamDefinition = {
  key: "skewX",
  label: "기울기 (°)",
  type: "number",
  default: 0,
  min: -45,
  max: 45,
  step: 1,
};

const STROKE_SHADOW_PARAMS: ElementParamDefinition[] = [
  { key: "stroke.enabled", label: "외곽선", type: "boolean", default: false, keyframable: false },
  { key: "stroke.color", label: "외곽선 색", type: "color", default: "#000000", dependencies: onlyWhen("stroke.enabled") },
  { key: "stroke.width", label: "외곽선 두께 (%)", type: "number", default: 8, min: 0, max: 40, step: 0.5, dependencies: onlyWhen("stroke.enabled") },
  { key: "shadow.enabled", label: "그림자", type: "boolean", default: false, keyframable: false },
  { key: "shadow.color", label: "그림자 색", type: "color", default: "#000000b3", dependencies: onlyWhen("shadow.enabled") },
  { key: "shadow.blur", label: "그림자 흐림 (%)", type: "number", default: 15, min: 0, max: 100, step: 1, dependencies: onlyWhen("shadow.enabled") },
  { key: "shadow.offsetX", label: "그림자 가로 (%)", type: "number", default: 6, min: -100, max: 100, step: 1, dependencies: onlyWhen("shadow.enabled") },
  { key: "shadow.offsetY", label: "그림자 세로 (%)", type: "number", default: 6, min: -100, max: 100, step: 1, dependencies: onlyWhen("shadow.enabled") },
];

/** Upstream text params → Fluma text params (same order, extras inserted). */
export function withFlumaTextParams(
  params: readonly ElementParamDefinition[],
): ElementParamDefinition[] {
  const out: ElementParamDefinition[] = [];
  for (const param of params) {
    if (param.key === "fontFamily") {
      out.push({ ...param, default: FLUMA_DEFAULT_FONT } as ElementParamDefinition);
    } else if (param.key === "fontWeight" && param.type === "select") {
      out.push({ ...param, options: FONT_WEIGHT_OPTIONS });
    } else {
      out.push(param);
    }
    if (param.key === "fontStyle") out.push(SKEW_PARAM);
    if (param.key === "lineHeight") out.push(...STROKE_SHADOW_PARAMS);
  }
  return out;
}

/** Properties panel grouping for the text tab (fluma/grouped-params-tab.tsx). */
export interface ParamGroupSpec {
  id: string;
  title?: string;
  keys: readonly string[];
  collapsed?: boolean;
}

export const TEXT_PARAM_GROUPS: readonly ParamGroupSpec[] = [
  { id: "content", keys: ["content"] },
  { id: "font", title: "글꼴", keys: ["fontFamily", "fontSize", "fontWeight", "color", "textAlign"] },
  { id: "slant", title: "기울임 · 장식", keys: ["fontStyle", "skewX", "textDecoration"] },
  { id: "spacing", title: "간격", keys: ["letterSpacing", "lineHeight"] },
  { id: "stroke", title: "외곽선", keys: ["stroke.enabled", "stroke.color", "stroke.width"] },
  { id: "shadow", title: "그림자", keys: ["shadow.enabled", "shadow.color", "shadow.blur", "shadow.offsetX", "shadow.offsetY"] },
  {
    id: "background",
    title: "배경 상자",
    keys: [
      "background.enabled",
      "background.color",
      "background.cornerRadius",
      "background.paddingX",
      "background.paddingY",
      "background.offsetX",
      "background.offsetY",
    ],
  },
];

/** "100".."900" | numbers | normal | bold → TextFontWeight-compatible string, or null. */
export function readNumericFontWeight(value: unknown): `${number}` | null {
  const n = Number(value);
  if (Number.isFinite(n) && n >= 100 && n <= 950) {
    return String(Math.round(n / 100) * 100) as `${number}`;
  }
  return null;
}
