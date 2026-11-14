"use client";

// fluma: properties-panel controls added to the upstream PropertyParamField
// (panels/properties/components/property-param-field.tsx, three hook lines):
//   - FlumaBoundedNumber: slider next to the number field when the param has a
//     small finite range (outline width, shadow %, skew …)
//   - FlumaFontSizeField: font size edited in real canvas px with a preset list
//     (shorts caption sizes); stored value stays the upstream unit
import type { ReactNode } from "react";
import { ChevronDown, Check } from "lucide-react";
import type { NumberParamDefinition } from "../params";
import { Slider } from "../components/ui/slider";
import { NumberField } from "../components/ui/number-field";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "../components/ui/dropdown-menu";
import { usePropertyDraft } from "../panels/properties/hooks/use-property-draft";
import { useEditor } from "../editor/use-editor";
import { FONT_SIZE_SCALE_REFERENCE } from "../text/typography";
import { cn } from "../utils/ui";

export function FlumaBoundedNumber({
  param,
  displayValue,
  onPreviewDisplay,
  onCommit,
  children,
}: {
  param: NumberParamDefinition;
  displayValue: number;
  onPreviewDisplay: (value: number) => void;
  onCommit: () => void;
  children: ReactNode;
}) {
  const { min, max, step } = param;
  const bounded =
    max !== undefined && Number.isFinite(max) && Number.isFinite(min) && max - min <= 1000;
  if (!bounded) return <>{children}</>;
  return (
    <div className="flex items-center gap-2.5">
      <Slider
        className="min-w-0 flex-1"
        min={min}
        max={max}
        step={step}
        value={[Math.max(min, Math.min(max, displayValue))]}
        onValueChange={([next]) => onPreviewDisplay(next)}
        onValueCommit={() => onCommit()}
      />
      <div className="w-[4.5rem] shrink-0">{children}</div>
    </div>
  );
}

// 쇼츠 자막 기준 크기(px, 1920 높이 화면 기준이 아니라 실제 캔버스 px)
const FONT_SIZE_PRESETS_PX: Array<{ px: number; label?: string }> = [
  { px: 16, label: "최소" },
  { px: 24 },
  { px: 32 },
  { px: 40, label: "설명" },
  { px: 48 },
  { px: 56 },
  { px: 64, label: "자막 기본" },
  { px: 72 },
  { px: 80, label: "자막 강조" },
  { px: 96 },
  { px: 128, label: "소제목" },
  { px: 160 },
  { px: 192, label: "제목" },
  { px: 240, label: "큰 제목" },
  { px: 320, label: "화면 가득" },
];

export function FlumaFontSizeField({
  value,
  onPreview,
  onCommit,
}: {
  value: number;
  onPreview: (value: number) => void;
  onCommit: () => void;
}) {
  const canvasHeight = useEditor(
    (e) => e.project.getActive()?.settings?.canvasSize?.height ?? 1920,
  );
  const scale = canvasHeight / FONT_SIZE_SCALE_REFERENCE;
  const currentPx = Math.max(1, Math.round(value * scale));

  const previewFromPx = (nextPx: number) => {
    const clampedPx = Math.max(1, Math.min(600, Math.round(nextPx)));
    onPreview(Math.round((clampedPx / scale) * 100) / 100);
  };

  const draft = usePropertyDraft({
    displayValue: String(currentPx),
    parse: (input) => {
      const parsed = Number.parseFloat(input);
      if (Number.isNaN(parsed) || parsed <= 0) return null;
      return Math.round(parsed);
    },
    onPreview: previewFromPx,
    onCommit,
  });

  return (
    <div className="flex items-center gap-1.5">
      <div className="min-w-0 flex-1">
        <NumberField
          value={draft.displayValue}
          suffix="px"
          dragSensitivity="slow"
          onFocus={draft.onFocus}
          onChange={draft.onChange}
          onBlur={draft.onBlur}
          onScrub={previewFromPx}
          onScrubEnd={onCommit}
        />
      </div>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            className="border-border bg-accent hover:bg-popover-hover flex h-7 shrink-0 items-center justify-center rounded-md border px-2"
            title="글자 크기 목록"
            aria-label="글자 크기 목록"
          >
            <ChevronDown className="size-3.5 opacity-70" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="max-h-64 w-44 overflow-y-auto">
          {FONT_SIZE_PRESETS_PX.map((opt) => {
            const isSelected = Math.abs(currentPx - opt.px) <= 2;
            return (
              <DropdownMenuItem
                key={opt.px}
                onSelect={() => {
                  previewFromPx(opt.px);
                  onCommit();
                }}
                className={cn("justify-between text-xs", isSelected && "text-primary-400")}
              >
                <span className="flex items-center gap-2">
                  {isSelected ? <Check className="size-3.5" /> : <span className="size-3.5" />}
                  <span className="tabular-nums">{opt.px}px</span>
                </span>
                {opt.label && <span className="text-muted-foreground text-[11px]">{opt.label}</span>}
              </DropdownMenuItem>
            );
          })}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
