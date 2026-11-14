"use client";

// fluma: properties-panel additions, mounted from panels/properties/registry.tsx
//   - GroupedParamsTab: text params in collapsible groups (글꼴 · 외곽선 · 그림자 …)
//   - TransformPresets: 화면에 맞춤 / 화면 채우기 / 원본 픽셀 from the real media
//     size (scale 1 = "contain" in this renderer)
//   - CropAndBorderSection: margins (rectangle mask) + border for video/image
import type { ReactNode } from "react";
import { RotateCcw } from "lucide-react";
import {
  Section,
  SectionContent,
  SectionFields,
  SectionHeader,
  SectionTitle,
} from "../components/section";
import { Slider } from "../components/ui/slider";
import { useEditor } from "../editor/use-editor";
import { useElementPlayhead } from "../panels/properties/hooks/use-element-playhead";
import {
  ElementParamField,
  buildValues,
  isVisible,
} from "../panels/properties/components/element-params-tab";
import { getElementParams, type ElementParamDefinition } from "../params/registry";
import type { TimelineElement } from "../timeline/types";
import type { ParamGroupSpec } from "./text-params";
import { generateUUID } from "../utils/id";

export function GroupedParamsTab({
  element,
  trackId,
  groups,
  sectionKey,
}: {
  element: TimelineElement;
  trackId: string;
  groups: readonly ParamGroupSpec[];
  sectionKey: string;
}) {
  const { localTime, isPlayheadWithinElementRange } = useElementPlayhead({
    startTime: element.startTime,
    duration: element.duration,
  });
  const allParams = getElementParams({ element });
  const baseValues = buildValues({ element, params: allParams });

  return (
    <div className="flex flex-col">
      {groups.map((group) => {
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
              <SectionFields>
                {params.map((param) => (
                  <ElementParamField
                    key={param.key}
                    element={element}
                    trackId={trackId}
                    param={param}
                    baseValue={baseValues[param.key] ?? param.default}
                    localTime={localTime}
                    isPlayheadWithinElementRange={isPlayheadWithinElementRange}
                  />
                ))}
              </SectionFields>
            </SectionContent>
          </Section>
        );
      })}
    </div>
  );
}

/** Transform tab for video / image: fit presets + crop/border above the upstream fields. */
export function VisualTransformExtras({
  element,
  trackId,
  children,
}: {
  element: TimelineElement;
  trackId: string;
  children: ReactNode;
}) {
  if (element.type !== "video" && element.type !== "image") return <>{children}</>;
  return (
    <div className="flex flex-col">
      <TransformPresets element={element} trackId={trackId} />
      {children}
      <CropAndBorderSection element={element} trackId={trackId} />
    </div>
  );
}

function TransformPresets({ element, trackId }: { element: TimelineElement; trackId: string }) {
  const editor = useEditor();
  const assets = useEditor((e) => e.media.getAssets());
  const project = useEditor((e) => e.project.getActive());
  const mediaId = "mediaId" in element ? (element as { mediaId?: string }).mediaId : undefined;
  const asset = assets.find((a) => a.id === mediaId);
  const canvas = project?.settings.canvasSize;
  if (!asset?.width || !asset?.height || !canvas || !("params" in element)) return null;

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
    <div className="grid grid-cols-3 gap-1.5 border-b border-border px-4 pt-4 pb-3">
      {presets.map((preset) => (
        <button
          key={preset.label}
          type="button"
          title={preset.hint}
          onClick={() => apply(preset.scale)}
          className="border-border bg-accent hover:bg-popover-hover h-8 truncate rounded-md border px-1.5 text-xs"
        >
          {preset.label}
        </button>
      ))}
    </div>
  );
}

type RectMaskLike = { id?: string; type: string; params?: Record<string, unknown> };

function CropAndBorderSection({ element, trackId }: { element: TimelineElement; trackId: string }) {
  const editor = useEditor();
  const masks = ((element as { masks?: RectMaskLike[] }).masks ?? []) as RectMaskLike[];
  const rectMask = masks.find((m) => m.type === "rectangle");

  const widthRatio = Number(rectMask?.params?.width ?? 1);
  const heightRatio = Number(rectMask?.params?.height ?? 1);
  const strokeWidth = Number(rectMask?.params?.strokeWidth ?? 0);
  const strokeColor = String(rectMask?.params?.strokeColor ?? "#ffffff");
  const horizontal = Math.max(0, Math.min(45, Math.round(((1 - widthRatio) / 2) * 100)));
  const vertical = Math.max(0, Math.min(45, Math.round(((1 - heightRatio) / 2) * 100)));

  const commit = (masksNext: RectMaskLike[]) => {
    editor.timeline.updateElements({
      // the rectangle mask shape is the upstream one (masks/builtin/definitions/rectangle.ts)
      updates: [{ trackId, elementId: element.id, patch: { masks: masksNext } as never }],
      pushHistory: true,
    });
  };

  const apply = (h: number, v: number, sw: number, sc: string) => {
    const others = masks.filter((m) => m.type !== "rectangle");
    const mask: RectMaskLike = {
      ...(rectMask ?? {}),
      id: rectMask?.id ?? generateUUID(),
      type: "rectangle",
      params: {
        centerX: 0,
        centerY: 0,
        rotation: 0,
        scale: 1,
        feather: 0,
        inverted: false,
        strokeAlign: "center",
        ...(rectMask?.params ?? {}),
        width: Math.max(0.1, 1 - (h * 2) / 100),
        height: Math.max(0.1, 1 - (v * 2) / 100),
        strokeWidth: sw,
        strokeColor: sc,
      },
    };
    commit(h > 0 || v > 0 || sw > 0 ? [...others, mask] : others);
  };

  const row = (label: string, value: number, max: number, unit: string, onChange: (n: number) => void) => (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-muted-foreground">
        <span>{label}</span>
        <span className="tabular-nums text-foreground">
          {value}
          {unit}
        </span>
      </div>
      <Slider value={[value]} min={0} max={max} step={1} onValueChange={([n]) => onChange(n)} />
    </div>
  );

  return (
    <Section collapsible defaultOpen={false} sectionKey={`${element.id}:fluma-crop`}>
      <SectionHeader>
        <SectionTitle>여백 · 테두리</SectionTitle>
      </SectionHeader>
      <SectionContent>
        <div className="space-y-3 pt-1 text-xs">
          {row("위 · 아래 여백", vertical, 45, "%", (n) => apply(horizontal, n, strokeWidth, strokeColor))}
          {row("왼쪽 · 오른쪽 여백", horizontal, 45, "%", (n) => apply(n, vertical, strokeWidth, strokeColor))}
          {row("테두리 두께", strokeWidth, 30, "px", (n) => apply(horizontal, vertical, n, strokeColor))}
          {strokeWidth > 0 && (
            <div className="flex items-center justify-between pt-1">
              <span className="text-muted-foreground">테두리 색</span>
              <div className="flex items-center gap-1.5">
                {["#ffffff", "#000000", "#ffcc00", "#ff3b30", "#34c759", "#007aff"].map((c) => (
                  <button
                    key={c}
                    type="button"
                    aria-label={c}
                    onClick={() => apply(horizontal, vertical, strokeWidth, c)}
                    style={{ backgroundColor: c }}
                    className={`size-4 rounded-full border ${
                      strokeColor.toLowerCase() === c ? "border-primary ring-1 ring-primary" : "border-border"
                    }`}
                  />
                ))}
              </div>
            </div>
          )}
          {(horizontal > 0 || vertical > 0 || strokeWidth > 0) && (
            <div className="flex justify-end pt-1">
              <button
                type="button"
                onClick={() => commit(masks.filter((m) => m.type !== "rectangle"))}
                className="flex items-center gap-1 rounded border border-border px-2 py-0.5 text-[11px] text-muted-foreground hover:text-foreground"
              >
                <RotateCcw className="size-3" />
                <span>여백 · 테두리 초기화</span>
              </button>
            </div>
          )}
        </div>
      </SectionContent>
    </Section>
  );
}
