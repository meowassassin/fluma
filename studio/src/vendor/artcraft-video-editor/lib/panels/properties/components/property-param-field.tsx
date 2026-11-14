"use client";

// fluma: one consistent control per param type, used by every properties
// tab (element params, effects, …):
//   number  → slider + numeric field (bounded) or numeric field (unbounded);
//             font size adds a preset dropdown next to the field
//   color   → swatch popover (presets · picker · hex · opacity %)
//   font    → searchable font dropdown, each font previewed in its own face
//   select  → dropdown
//   boolean → switch on the label row
//   text    → textarea
import type {
  ParamDefinition,
  NumberParamDefinition,
  ParamValue,
} from "../../../params";
import {
  formatNumberForDisplay,
  getFractionDigitsForStep,
  snapToStep,
} from "../../../utils/math";
import { SectionField } from "../../../components/section";
import { NumberField } from "../../../components/ui/number-field";
import { Switch } from "../../../components/ui/switch";
import { Slider } from "../../../components/ui/slider";
import { ColorPicker } from "../../../components/ui/color-picker";
import { FontPicker } from "../../../components/ui/font-picker";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../../../components/ui/select";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "../../../components/ui/dropdown-menu";
import { ChevronDown, Check } from "lucide-react";
import { usePropertyDraft } from "../hooks/use-property-draft";
import { KeyframeToggle } from "./keyframe-toggle";
import { Textarea } from "../../../components/ui/textarea";
import { Label } from "../../../components/ui/label";
import { cn } from "../../../utils/ui";
import { useEditor } from "../../../editor/use-editor";
import { FONT_SIZE_SCALE_REFERENCE } from "../../../text/typography";

// 표준 폰트 크기 프리셋 (px 단위)
const FONT_SIZE_OPTIONS_PX: Array<{ px: number; label?: string }> = [
  { px: 16, label: "최소" },
  { px: 20 },
  { px: 24 },
  { px: 28 },
  { px: 32 },
  { px: 40, label: "설명" },
  { px: 48 },
  { px: 56 },
  { px: 64, label: "자막 기본" },
  { px: 72 },
  { px: 80, label: "자막 강조" },
  { px: 96 },
  { px: 112 },
  { px: 128, label: "소제목" },
  { px: 144 },
  { px: 160 },
  { px: 192, label: "제목" },
  { px: 240, label: "큰 제목" },
  { px: 320, label: "화면 가득" },
];

export function PropertyParamField({
  param,
  value,
  onPreview,
  onCommit,
  keyframe,
}: {
  param: ParamDefinition;
  value: ParamValue;
  onPreview: (value: ParamValue) => void;
  onCommit: () => void;
  keyframe?: {
    isActive: boolean;
    isDisabled: boolean;
    onToggle: () => void;
  };
}) {
  const keyframeToggle =
    keyframe && param.keyframable !== false ? (
      <KeyframeToggle
        isActive={keyframe.isActive}
        isDisabled={keyframe.isDisabled}
        title={`${param.label} 키프레임`}
        onToggle={keyframe.onToggle}
      />
    ) : undefined;

  if (param.type === "boolean") {
    return (
      <div className="flex h-7 items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-1.5">
          {keyframeToggle}
          <Label className="truncate">{param.label}</Label>
        </div>
        <Switch
          checked={Boolean(value)}
          onCheckedChange={(checked) => {
            onPreview(checked);
            onCommit();
          }}
        />
      </div>
    );
  }

  return (
    <SectionField label={param.label} beforeLabel={keyframeToggle}>
      <ParamInput param={param} value={value} onPreview={onPreview} onCommit={onCommit} />
    </SectionField>
  );
}

function ParamInput({
  param,
  value,
  onPreview,
  onCommit,
}: {
  param: ParamDefinition;
  value: ParamValue;
  onPreview: (value: ParamValue) => void;
  onCommit: () => void;
}) {
  switch (param.type) {
    case "number":
      return (
        <NumberParamField
          param={param}
          value={typeof value === "number" ? value : Number(value)}
          onPreview={onPreview}
          onCommit={onCommit}
        />
      );
    case "select": {
      const current = String(value);
      const known = param.options.some((o) => o.value === current);
      return (
        <Select
          value={known ? current : String(param.default)}
          onValueChange={(selected) => {
            onPreview(selected);
            onCommit();
          }}
        >
          <SelectTrigger className="h-8 w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {param.options.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      );
    }
    case "color":
      return (
        <ColorPicker
          value={String(value)}
          onChange={(color) => onPreview(`#${color}`)}
          onChangeEnd={(color) => {
            onPreview(`#${color}`);
            onCommit();
          }}
        />
      );
    case "text":
      return (
        <Textarea
          value={String(value)}
          className="min-h-16"
          onChange={(event) => onPreview(event.currentTarget.value)}
          onBlur={onCommit}
        />
      );
    case "font":
      return (
        <FontPicker
          value={String(value || "Pretendard")}
          onValueChange={(family) => {
            onPreview(family);
            onCommit();
          }}
        />
      );
    default:
      return null;
  }
}

function FontSizeField({
  value,
  onPreview,
  onCommit,
}: {
  value: number;
  onPreview: (value: number) => void;
  onCommit: () => void;
}) {
  const canvasHeight = useEditor(
    (e) => e.project.getActive()?.settings?.canvasSize?.height ?? 1920
  );
  const scale = canvasHeight / FONT_SIZE_SCALE_REFERENCE;

  // 현재 픽셀 값 (반올림)
  const currentPx = Math.max(1, Math.round(value * scale));

  const previewFromPx = (nextPx: number) => {
    const clampedPx = Math.max(1, Math.min(600, Math.round(nextPx)));
    const nextVal = clampedPx / scale;
    onPreview(Math.round(nextVal * 100) / 100);
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

  const handleSelectPreset = (px: number) => {
    previewFromPx(px);
    onCommit();
  };

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
          className="h-8"
        />
      </div>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            className="border-input bg-accent/60 hover:bg-accent flex h-8 shrink-0 items-center justify-center rounded-md border px-2 text-xs text-foreground font-medium transition-colors"
            title="폰트 크기 프리셋 목록"
            aria-label="폰트 크기 프리셋"
          >
            <ChevronDown className="size-3.5 opacity-70" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="max-h-64 w-44 overflow-y-auto">
          {FONT_SIZE_OPTIONS_PX.map((opt) => {
            const isSelected = Math.abs(currentPx - opt.px) <= 2;
            return (
              <DropdownMenuItem
                key={opt.px}
                onSelect={() => handleSelectPreset(opt.px)}
                className={cn(
                  "flex items-center justify-between text-xs py-1.5 cursor-pointer",
                  isSelected && "text-primary font-semibold bg-accent/50"
                )}
              >
                <div className="flex items-center gap-2">
                  {isSelected ? (
                    <Check className="size-3.5 text-primary" />
                  ) : (
                    <span className="size-3.5" />
                  )}
                  <span className="tabular-nums font-mono">{opt.px}px</span>
                </div>
                {opt.label && (
                  <span className="text-[11px] text-muted-foreground">{opt.label}</span>
                )}
              </DropdownMenuItem>
            );
          })}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}

function NumberParamField({
  param,
  value,
  onPreview,
  onCommit,
}: {
  param: NumberParamDefinition;
  value: number;
  onPreview: (value: number) => void;
  onCommit: () => void;
}) {
  if (param.key === "fontSize") {
    return (
      <FontSizeField
        value={value}
        onPreview={onPreview}
        onCommit={onCommit}
      />
    );
  }
  const { min, max, step, displayMultiplier = 1 } = param;
  const displayValue = value * displayMultiplier;
  const clampDisplayValue = (nextDisplayValue: number) =>
    Math.max(min, max !== undefined ? Math.min(max, nextDisplayValue) : nextDisplayValue);

  const previewFromDisplay = (displayVal: number) => {
    const clamped = clampDisplayValue(snapToStep({ value: displayVal, step }));
    onPreview(clamped / displayMultiplier);
  };

  const maxFractionDigits = getFractionDigitsForStep({ step });

  const draft = usePropertyDraft({
    displayValue: formatNumberForDisplay({ value: displayValue, maxFractionDigits }),
    parse: (input) => {
      const parsed = Number.parseFloat(input);
      if (Number.isNaN(parsed)) return null;
      return clampDisplayValue(snapToStep({ value: parsed, step }));
    },
    onPreview: previewFromDisplay,
    onCommit,
  });

  const handleReset = () => {
    onPreview(param.default);
    onCommit();
  };

  const field = (
    <NumberField
      icon={param.shortLabel}
      value={draft.displayValue}
      dragSensitivity="slow"
      isDefault={value === param.default}
      onFocus={draft.onFocus}
      onChange={draft.onChange}
      onBlur={draft.onBlur}
      onScrub={previewFromDisplay}
      onScrubEnd={onCommit}
      onReset={handleReset}
      className="h-8"
    />
  );

  const bounded = max !== undefined && Number.isFinite(max) && Number.isFinite(min) && max - min <= 1000;
  if (!bounded) return field;

  return (
    <div className="flex items-center gap-2.5">
      <Slider
        className="min-w-0 flex-1"
        min={min}
        max={max}
        step={step}
        value={[Math.max(min, Math.min(max!, displayValue))]}
        onValueChange={([next]) => previewFromDisplay(next)}
        onValueCommit={() => onCommit()}
      />
      <div className="w-[4.5rem] shrink-0">{field}</div>
    </div>
  );
}
