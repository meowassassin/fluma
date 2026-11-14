import type {
  ParamDefinition,
  ParamValue,
  ParamValues,
} from "./index";
import { MIN_TRANSFORM_SCALE } from "../animation/transform";
import type { BlendMode } from "../rendering";
import type {
  ElementType,
  TimelineElement,
} from "../timeline/types";
import { DEFAULTS } from "../timeline/defaults";
import { VOLUME_DB_MAX, VOLUME_DB_MIN } from "../timeline/audio-constants";
import {
  CORNER_RADIUS_MAX,
  CORNER_RADIUS_MIN,
} from "../text/background";

// Per-element-type parameter registry. Each ElementType maps to an
// ordered list of ParamDefinitions; the properties panel iterates these
// to render the editor controls. ParamDefinition.read/write are
// optional overrides for cases where the param doesn't live in
// `element.params` (e.g. element.type, mediaId, etc.) — most params use
// the default `element.params[key]` accessor.
//
// The registry is keyed by ElementType, so adding a new element type
// requires registering its params here at module-init time.

export type ElementParamDefinition<TKey extends string = string> =
  ParamDefinition<TKey> & {
    read?: ({ element }: { element: TimelineElement }) => ParamValue | null;
    write?: ({
      element,
      value,
    }: {
      element: TimelineElement;
      value: ParamValue;
    }) => TimelineElement;
  };

export function buildDefaultParamValues(
  params: readonly ParamDefinition[],
): ParamValues {
  const values: ParamValues = {};
  for (const param of params) {
    values[param.key] = param.default;
  }
  return values;
}

export class DefinitionRegistry<TKey extends string, TDefinition> {
  private definitions = new Map<TKey, TDefinition>();
  private entityName: string;

  constructor(entityName: string) {
    this.entityName = entityName;
  }

  register({
    key,
    definition,
  }: {
    key: TKey;
    definition: TDefinition;
  }): void {
    this.definitions.set(key, definition);
  }

  has(key: TKey): boolean {
    return this.definitions.has(key);
  }

  get(key: TKey): TDefinition {
    const def = this.definitions.get(key);
    if (!def) {
      throw new Error(`Unknown ${this.entityName}: ${key}`);
    }
    return def;
  }

  getAll(): TDefinition[] {
    return Array.from(this.definitions.values());
  }
}

// fluma: Korean labels throughout; text params grouped by the properties
// panel (see panels/properties/registry.tsx). New text params: skewX,
// stroke.*, shadow.*; numeric font weights.
const BLEND_MODE_OPTIONS: Array<{ value: BlendMode; label: string }> = [
  { value: "normal", label: "보통" },
  { value: "multiply", label: "곱하기" },
  { value: "screen", label: "스크린" },
  { value: "overlay", label: "오버레이" },
  { value: "darken", label: "어둡게" },
  { value: "lighten", label: "밝게" },
  { value: "color-burn", label: "색상 번" },
  { value: "color-dodge", label: "색상 닷지" },
  { value: "plus-lighter", label: "더하기" },
  { value: "soft-light", label: "소프트 라이트" },
  { value: "hard-light", label: "하드 라이트" },
  { value: "difference", label: "차이" },
  { value: "exclusion", label: "제외" },
  { value: "hue", label: "색조" },
  { value: "saturation", label: "채도" },
  { value: "color", label: "색상" },
  { value: "luminosity", label: "광도" },
];

const visualElementParams: ElementParamDefinition[] = [
  {
    key: "transform.positionX",
    label: "가로 위치",
    shortLabel: "X",
    type: "number",
    default: DEFAULTS.element.transform.position.x,
    min: -100_000,
    step: 1,
  },
  {
    key: "transform.positionY",
    label: "세로 위치",
    shortLabel: "Y",
    type: "number",
    default: DEFAULTS.element.transform.position.y,
    min: -100_000,
    step: 1,
  },
  {
    key: "transform.scaleX",
    label: "가로 배율",
    shortLabel: "W",
    type: "number",
    default: DEFAULTS.element.transform.scaleX,
    min: MIN_TRANSFORM_SCALE,
    step: 0.01,
  },
  {
    key: "transform.scaleY",
    label: "세로 배율",
    shortLabel: "H",
    type: "number",
    default: DEFAULTS.element.transform.scaleY,
    min: MIN_TRANSFORM_SCALE,
    step: 0.01,
  },
  {
    key: "transform.rotate",
    label: "회전",
    shortLabel: "°",
    type: "number",
    default: DEFAULTS.element.transform.rotate,
    min: -360,
    max: 360,
    step: 1,
  },
  {
    key: "opacity",
    label: "불투명도 (%)",
    type: "number",
    default: DEFAULTS.element.opacity,
    min: 0,
    max: 100,
    step: 1,
    displayMultiplier: 100,
  },
  {
    key: "blendMode",
    label: "혼합 모드",
    type: "select",
    default: DEFAULTS.element.blendMode,
    keyframable: false,
    options: BLEND_MODE_OPTIONS,
  },
];

const audioElementParams: ElementParamDefinition[] = [
  {
    key: "volume",
    label: "볼륨 (dB)",
    type: "number",
    default: DEFAULTS.element.volume,
    min: VOLUME_DB_MIN,
    max: VOLUME_DB_MAX,
    step: 0.1,
  },
  {
    key: "muted",
    label: "음소거",
    type: "boolean",
    default: false,
    keyframable: false,
  },
];

const FONT_WEIGHT_OPTIONS = [
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

const textElementParams: ElementParamDefinition[] = [
  {
    key: "content",
    label: "내용",
    type: "text",
    default: "텍스트",
    keyframable: false,
  },
  {
    key: "fontFamily",
    label: "글꼴",
    type: "font",
    default: "Pretendard",
    keyframable: false,
  },
  {
    key: "fontSize",
    label: "크기",
    type: "number",
    default: 15,
    min: 1,
    max: 300,
    step: 0.5,
  },
  {
    key: "fontWeight",
    label: "굵기",
    type: "select",
    default: "normal",
    keyframable: false,
    options: FONT_WEIGHT_OPTIONS,
  },
  {
    key: "color",
    label: "글자 색",
    type: "color",
    default: "#ffffff",
  },
  {
    key: "textAlign",
    label: "정렬",
    type: "select",
    default: "center",
    keyframable: false,
    options: [
      { value: "left", label: "왼쪽" },
      { value: "center", label: "가운데" },
      { value: "right", label: "오른쪽" },
    ],
  },
  {
    key: "fontStyle",
    label: "이탤릭",
    type: "select",
    default: "normal",
    keyframable: false,
    options: [
      { value: "normal", label: "똑바로" },
      { value: "italic", label: "이탤릭 (기울임꼴)" },
    ],
  },
  {
    key: "skewX",
    label: "기울기 (°)",
    type: "number",
    default: 0,
    min: -45,
    max: 45,
    step: 1,
  },
  {
    key: "textDecoration",
    label: "밑줄 · 취소선",
    type: "select",
    default: "none",
    keyframable: false,
    options: [
      { value: "none", label: "없음" },
      { value: "underline", label: "밑줄" },
      { value: "line-through", label: "취소선" },
    ],
  },
  {
    key: "letterSpacing",
    label: "자간",
    type: "number",
    default: DEFAULTS.text.letterSpacing,
    min: -50,
    max: 200,
    step: 0.5,
  },
  {
    key: "lineHeight",
    label: "줄 간격",
    type: "number",
    default: DEFAULTS.text.lineHeight,
    min: 0.5,
    max: 4,
    step: 0.05,
  },
  {
    key: "stroke.enabled",
    label: "외곽선",
    type: "boolean",
    default: false,
    keyframable: false,
  },
  {
    key: "stroke.color",
    label: "외곽선 색",
    type: "color",
    default: "#000000",
    dependencies: onlyWhen("stroke.enabled"),
  },
  {
    key: "stroke.width",
    label: "외곽선 두께 (%)",
    type: "number",
    default: 8,
    min: 0,
    max: 40,
    step: 0.5,
    dependencies: onlyWhen("stroke.enabled"),
  },
  {
    key: "shadow.enabled",
    label: "그림자",
    type: "boolean",
    default: false,
    keyframable: false,
  },
  {
    key: "shadow.color",
    label: "그림자 색",
    type: "color",
    default: "#000000b3",
    dependencies: onlyWhen("shadow.enabled"),
  },
  {
    key: "shadow.blur",
    label: "그림자 흐림 (%)",
    type: "number",
    default: 15,
    min: 0,
    max: 100,
    step: 1,
    dependencies: onlyWhen("shadow.enabled"),
  },
  {
    key: "shadow.offsetX",
    label: "그림자 가로 (%)",
    type: "number",
    default: 6,
    min: -100,
    max: 100,
    step: 1,
    dependencies: onlyWhen("shadow.enabled"),
  },
  {
    key: "shadow.offsetY",
    label: "그림자 세로 (%)",
    type: "number",
    default: 6,
    min: -100,
    max: 100,
    step: 1,
    dependencies: onlyWhen("shadow.enabled"),
  },
  {
    key: "background.enabled",
    label: "배경 상자",
    type: "boolean",
    default: DEFAULTS.text.background.enabled,
    keyframable: false,
  },
  {
    key: "background.color",
    label: "배경 색",
    type: "color",
    default: DEFAULTS.text.background.color,
    dependencies: onlyWhen("background.enabled"),
  },
  {
    key: "background.cornerRadius",
    label: "모서리 둥글기",
    type: "number",
    default: DEFAULTS.text.background.cornerRadius,
    min: CORNER_RADIUS_MIN,
    max: CORNER_RADIUS_MAX,
    step: 1,
    dependencies: onlyWhen("background.enabled"),
  },
  {
    key: "background.paddingX",
    label: "가로 여백",
    type: "number",
    default: DEFAULTS.text.background.paddingX,
    min: 0,
    step: 1,
    dependencies: onlyWhen("background.enabled"),
  },
  {
    key: "background.paddingY",
    label: "세로 여백",
    type: "number",
    default: DEFAULTS.text.background.paddingY,
    min: 0,
    step: 1,
    dependencies: onlyWhen("background.enabled"),
  },
  {
    key: "background.offsetX",
    label: "배경 가로 이동",
    type: "number",
    default: DEFAULTS.text.background.offsetX,
    min: -100_000,
    step: 1,
    dependencies: onlyWhen("background.enabled"),
  },
  {
    key: "background.offsetY",
    label: "배경 세로 이동",
    type: "number",
    default: DEFAULTS.text.background.offsetY,
    min: -100_000,
    step: 1,
    dependencies: onlyWhen("background.enabled"),
  },
];

export const elementParamRegistry = new DefinitionRegistry<
  ElementType,
  readonly ElementParamDefinition[]
>("element params");

elementParamRegistry.register({
  key: "video",
  definition: [...visualElementParams, ...audioElementParams],
});
elementParamRegistry.register({ key: "image", definition: visualElementParams });
elementParamRegistry.register({
  key: "text",
  definition: [...textElementParams, ...visualElementParams],
});
elementParamRegistry.register({
  key: "sticker",
  definition: visualElementParams,
});
elementParamRegistry.register({
  key: "graphic",
  definition: visualElementParams,
});
elementParamRegistry.register({ key: "audio", definition: audioElementParams });
elementParamRegistry.register({ key: "effect", definition: [] });

export function getElementParams({
  element,
}: {
  element: TimelineElement;
}): readonly ElementParamDefinition[] {
  return elementParamRegistry.has(element.type)
    ? elementParamRegistry.get(element.type)
    : [];
}

export function getBuiltInElementParams({
  type,
}: {
  type: ElementType;
}): readonly ElementParamDefinition[] {
  return elementParamRegistry.has(type) ? elementParamRegistry.get(type) : [];
}

export function getElementParam({
  element,
  key,
}: {
  element: TimelineElement;
  key: string;
}): ElementParamDefinition | null {
  return (
    getElementParams({ element }).find((param) => param.key === key) ?? null
  );
}

export function readElementParamValue({
  element,
  param,
}: {
  element: TimelineElement;
  param: ElementParamDefinition;
}): ParamValue | null {
  if (param.read) {
    return param.read({ element });
  }
  if ("params" in element) {
    return element.params[param.key] ?? param.default;
  }
  return null;
}

export function writeElementParamValue({
  element,
  param,
  value,
}: {
  element: TimelineElement;
  param: ElementParamDefinition;
  value: ParamValue;
}): TimelineElement {
  if (param.write) {
    return param.write({ element, value });
  }
  if ("params" in element) {
    return {
      ...element,
      params: {
        ...element.params,
        [param.key]: value,
      },
    };
  }
  return element;
}

export function buildElementParamValues({
  element,
}: {
  element: TimelineElement;
}): ParamValues {
  const values: ParamValues = {};
  for (const param of getElementParams({ element })) {
    const value = readElementParamValue({ element, param });
    if (value !== null) {
      values[param.key] = value;
    }
  }
  return values;
}
