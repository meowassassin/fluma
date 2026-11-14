"use client";

import { resolveAnimationPathValueAtTime } from "../../../animation";
import {
  Section,
  SectionContent,
  SectionFields,
  SectionHeader,
  SectionTitle,
} from "../../../components/section";
import { useElementPlayhead } from "../hooks/use-element-playhead";
import { useKeyframedParamProperty } from "../hooks/use-keyframed-param-property";
import { useEditor } from "../../../editor/use-editor";
import { cn } from "../../../utils/ui";
import { PropertyParamField } from "./property-param-field";
import type { ParamValue, ParamValues } from "../../../params";
import {
  getElementParams,
  readElementParamValue,
  writeElementParamValue,
  type ElementParamDefinition,
} from "../../../params/registry";
import type { TimelineElement } from "../../../timeline/types";
import type { MediaTime } from "../../../wasm";

import { Slider } from "../../../components/ui/slider";
import { RotateCcw } from "lucide-react";

// fluma: fit presets computed from the real media size and canvas size
// (scale 1 = "contain" in this renderer). Replaces hard-coded 1.78×/2× guesses.
function TransformPresets({
  element,
  trackId,
}: {
  element: TimelineElement;
  trackId: string;
}) {
  const editor = useEditor();
  const assets = useEditor((e) => e.media.getAssets());
  const project = useEditor((e) => e.project.getActive());
  const mediaId = "mediaId" in element ? (element as { mediaId?: string }).mediaId : undefined;
  const asset = assets.find((a) => a.id === mediaId);
  const canvas = project?.settings.canvasSize;
  if (!asset?.width || !asset?.height || !canvas) return null;

  const contain = Math.min(canvas.width / asset.width, canvas.height / asset.height);
  const cover = Math.max(canvas.width / asset.width, canvas.height / asset.height) / contain;
  const actual = 1 / contain;
  const round = (n: number) => Math.round(n * 1000) / 1000;

  const apply = (scale: number) => {
    editor.timeline.updateElements({
      updates: [
        {
          trackId,
          elementId: element.id,
          patch: {
            params: {
              ...element.params,
              "transform.scaleX": round(scale),
              "transform.scaleY": round(scale),
              "transform.positionX": 0,
              "transform.positionY": 0,
            },
          },
        },
      ],
    });
  };

  const presets = [
    { label: "화면에 맞춤", scale: 1, hint: "전체가 보이게 (여백 생김)" },
    { label: "화면 채우기", scale: cover, hint: "여백 없이 꽉 차게 (가장자리 잘림)" },
    { label: "원본 픽셀", scale: actual, hint: `${asset.width}×${asset.height} 그대로` },
  ];

  return (
    <div className="grid grid-cols-3 gap-1.5">
      {presets.map((preset) => (
        <button
          key={preset.label}
          type="button"
          title={preset.hint}
          onClick={() => apply(preset.scale)}
          className="border-input bg-accent hover:bg-popover-hover h-8 truncate rounded-md border px-1.5 text-xs"
        >
          {preset.label}
        </button>
      ))}
    </div>
  );
}

// fluma: 영상 여백(상·하·좌·우 마우스 크롭) 및 테두리(선 두께·색상) 컨트롤러
function VideoCropAndBorderSection({
  element,
  trackId,
}: {
  element: TimelineElement;
  trackId: string;
}) {
  const editor = useEditor();
  const masks = (element as { masks?: any[] }).masks ?? [];
  const rectMask = masks.find((m) => m.type === "rectangle");

  // 마스크 파라미터에서 현재 여백(상, 하, 좌, 우) 계산
  const widthRatio = Number(rectMask?.params?.width ?? 1.0);
  const heightRatio = Number(rectMask?.params?.height ?? 1.0);
  const strokeWidth = Number(rectMask?.params?.strokeWidth ?? 0);
  const strokeColor = String(rectMask?.params?.strokeColor ?? "#ffffff");

  // 여백 퍼센트 (0% ~ 45%)
  const horizontalMargin = Math.max(0, Math.min(45, Math.round(((1.0 - widthRatio) / 2) * 100)));
  const verticalMargin = Math.max(0, Math.min(45, Math.round(((1.0 - heightRatio) / 2) * 100)));

  const applyCropAndBorder = (newHoriz: number, newVert: number, newStrokeW: number, newStrokeC: string) => {
    const nextWidth = Math.max(0.1, 1.0 - (newHoriz * 2) / 100);
    const nextHeight = Math.max(0.1, 1.0 - (newVert * 2) / 100);

    const updatedMask = {
      type: "rectangle" as const,
      params: {
        centerX: 0,
        centerY: 0,
        width: nextWidth,
        height: nextHeight,
        rotation: 0,
        scale: 1,
        feather: 0,
        inverted: false,
        strokeWidth: newStrokeW,
        strokeColor: newStrokeC,
        strokeAlign: "center",
      },
    };

    const otherMasks = masks.filter((m) => m.type !== "rectangle");
    const nextMasks = (newHoriz > 0 || newVert > 0 || newStrokeW > 0)
      ? [...otherMasks, updatedMask]
      : otherMasks;

    editor.timeline.updateElements({
      updates: [
        {
          trackId,
          elementId: element.id,
          patch: { masks: nextMasks },
        },
      ],
      pushHistory: true,
    });
  };

  const handleReset = () => {
    const otherMasks = masks.filter((m) => m.type !== "rectangle");
    editor.timeline.updateElements({
      updates: [{ trackId, elementId: element.id, patch: { masks: otherMasks } }],
      pushHistory: true,
    });
  };

  return (
    <Section collapsible defaultOpen={false}>
      <SectionHeader>
        <SectionTitle>여백 (상·하·좌·우) 및 테두리</SectionTitle>
      </SectionHeader>
      <SectionContent>
        <div className="space-y-3 pt-1 text-xs">
          {/* 상하 여백 조절 */}
          <div className="space-y-1">
            <div className="flex items-center justify-between text-muted-foreground">
              <span>상·하 여백 (위 / 아래)</span>
              <span className="font-mono text-foreground">{verticalMargin}%</span>
            </div>
            <Slider
              value={[verticalMargin]}
              min={0}
              max={45}
              step={1}
              onValueChange={([val]) => applyCropAndBorder(horizontalMargin, val, strokeWidth, strokeColor)}
            />
          </div>

          {/* 좌우 여백 조절 */}
          <div className="space-y-1">
            <div className="flex items-center justify-between text-muted-foreground">
              <span>좌·우 여백 (왼쪽 / 오른쪽)</span>
              <span className="font-mono text-foreground">{horizontalMargin}%</span>
            </div>
            <Slider
              value={[horizontalMargin]}
              min={0}
              max={45}
              step={1}
              onValueChange={([val]) => applyCropAndBorder(val, verticalMargin, strokeWidth, strokeColor)}
            />
          </div>

          {/* 영상 테두리 두께 조절 */}
          <div className="space-y-1 pt-1 border-t border-border/40">
            <div className="flex items-center justify-between text-muted-foreground">
              <span>테두리 두께</span>
              <span className="font-mono text-foreground">{strokeWidth}px</span>
            </div>
            <Slider
              value={[strokeWidth]}
              min={0}
              max={30}
              step={1}
              onValueChange={([val]) => applyCropAndBorder(horizontalMargin, verticalMargin, val, strokeColor)}
            />
          </div>

          {/* 테두리 색상 선택 */}
          {strokeWidth > 0 && (
            <div className="flex items-center justify-between pt-1">
              <span className="text-muted-foreground">테두리 색상</span>
              <div className="flex items-center gap-1.5">
                {["#ffffff", "#000000", "#ffcc00", "#ff3b30", "#34c759", "#007aff"].map((c) => (
                  <button
                    key={c}
                    type="button"
                    onClick={() => applyCropAndBorder(horizontalMargin, verticalMargin, strokeWidth, c)}
                    style={{ backgroundColor: c }}
                    className={`size-4 rounded-full border transition-transform ${
                      strokeColor.toLowerCase() === c.toLowerCase()
                        ? "scale-125 border-primary ring-1 ring-primary"
                        : "border-border/60 hover:scale-110"
                    }`}
                  />
                ))}
              </div>
            </div>
          )}

          {(horizontalMargin > 0 || verticalMargin > 0 || strokeWidth > 0) && (
            <div className="flex justify-end pt-1">
              <button
                type="button"
                onClick={handleReset}
                className="flex items-center gap-1 px-2 py-0.5 rounded text-[11px] text-muted-foreground hover:text-foreground bg-muted/40 hover:bg-muted border border-border/50"
              >
                <RotateCcw className="size-3" />
                <span>여백·테두리 초기화</span>
              </button>
            </div>
          )}
        </div>
      </SectionContent>
    </Section>
  );
}

export type ParamGroupSpec = {
  id: string;
  title?: string;
  keys: readonly string[];
  /** start collapsed (e.g. rarely used groups) */
  collapsed?: boolean;
  /** lay fields out in two columns (X/Y, W/H pairs); an odd last field spans both */
  columns?: 2;
};

export function ElementParamsTab({
  element,
  trackId,
  paramKeys,
  groups,
  sectionKey,
}: {
  element: TimelineElement;
  trackId: string;
  paramKeys?: readonly string[];
  groups?: readonly ParamGroupSpec[];
  sectionKey: string;
}) {
  const { localTime, isPlayheadWithinElementRange } = useElementPlayhead({
    startTime: element.startTime,
    duration: element.duration,
  });
  const allParams = getElementParams({ element });
  const resolvedGroups: readonly ParamGroupSpec[] =
    groups ?? [{ id: "all", keys: paramKeys ?? allParams.map((p) => p.key) }];
  const baseValues = buildValues({ element, params: allParams });
  const isVisual =
    element.type === "video" || element.type === "image";

  return (
    <div className="flex flex-col">
      {sectionKey === "transform" && isVisual && (
        <>
          <div className="border-b border-white/5 px-4 pt-4 pb-3">
            <TransformPresets element={element} trackId={trackId} />
          </div>
          <VideoCropAndBorderSection element={element} trackId={trackId} />
        </>
      )}
      {resolvedGroups.map((group) => {
        const params = group.keys
          .map((key) => allParams.find((p) => p.key === key))
          .filter((p): p is ElementParamDefinition => Boolean(p))
          .filter((param) => isVisible({ param, values: baseValues }));
        if (params.length === 0) return null;
        return (
          <Section
            key={group.id}
            sectionKey={`${element.id}:${sectionKey}:${group.id}`}
            collapsible={Boolean(group.title)}
            defaultOpen={!group.collapsed}
          >
            {group.title && (
              <SectionHeader>
                <SectionTitle>{group.title}</SectionTitle>
              </SectionHeader>
            )}
            <SectionContent className={group.title ? "" : "pt-4"}>
              <SectionFields
                className={group.columns === 2 ? "grid grid-cols-2 gap-x-2.5 gap-y-3.5" : undefined}
              >
                {params.map((param, index) => (
                  <div
                    key={param.key}
                    className={cn(
                      "min-w-0",
                      group.columns === 2 &&
                        index === params.length - 1 &&
                        params.length % 2 === 1 &&
                        "col-span-2",
                    )}
                  >
                    <ElementParamField
                      element={element}
                      trackId={trackId}
                      param={param}
                      baseValue={baseValues[param.key] ?? param.default}
                      localTime={localTime}
                      isPlayheadWithinElementRange={isPlayheadWithinElementRange}
                    />
                  </div>
                ))}
              </SectionFields>
            </SectionContent>
          </Section>
        );
      })}
    </div>
  );
}

function ElementParamField({
  element,
  trackId,
  param,
  baseValue,
  localTime,
  isPlayheadWithinElementRange,
}: {
  element: TimelineElement;
  trackId: string;
  param: ElementParamDefinition;
  baseValue: ParamValue;
  localTime: MediaTime;
  isPlayheadWithinElementRange: boolean;
}) {
  const resolvedValue = resolveAnimationPathValueAtTime({
    animations: element.animations,
    propertyPath: param.key,
    localTime,
    fallbackValue: baseValue,
  });
  const animatedParam = useKeyframedParamProperty({
    param,
    trackId,
    elementId: element.id,
    animations: element.animations,
    propertyPath: param.key,
    localTime,
    isPlayheadWithinElementRange,
    resolvedValue,
    buildBaseUpdates: ({ value }) =>
      writeElementParamValue({ element, param, value }),
  });

  return (
    <PropertyParamField
      param={param}
      value={resolvedValue}
      onPreview={animatedParam.onPreview}
      onCommit={animatedParam.onCommit}
      keyframe={
        param.keyframable === false
          ? undefined
          : {
              isActive: animatedParam.isKeyframedAtTime,
              isDisabled: !isPlayheadWithinElementRange,
              onToggle: animatedParam.toggleKeyframe,
            }
      }
    />
  );
}

function buildValues({
  element,
  params,
}: {
  element: TimelineElement;
  params: readonly ElementParamDefinition[];
}): ParamValues {
  const values: ParamValues = {};
  for (const param of params) {
    const value = readElementParamValue({ element, param });
    if (value !== null) {
      values[param.key] = value;
    }
  }
  return values;
}

function isVisible({
  param,
  values,
}: {
  param: ElementParamDefinition;
  values: ParamValues;
}): boolean {
  return (param.dependencies ?? []).every((dependency) =>
    areParamValuesEqual({
      left: values[dependency.param],
      right: dependency.equals,
    }),
  );
}

function areParamValuesEqual({
  left,
  right,
}: {
  left: ParamValue | undefined;
  right: ParamValue;
}): boolean {
  return left === right;
}
