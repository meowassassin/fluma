"use client";

import { useEffect } from "react";
import { useEditor } from "../../editor/use-editor";
import { ensureFontStylesheet } from "../../fonts/google-fonts";
import { PanelView } from "../../panels/assets/views/base-panel";
import { DraggableItem } from "../../panels/assets/draggable-item";
import { DEFAULTS } from "../../timeline/defaults";
import { buildTextElement } from "../../timeline/element-utils";
import type { MediaTime } from "../../wasm";
import { Button } from "../../components/ui/button";
import { PlusSignIcon } from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";

// fluma: presets use the real text params (numeric weight, outline, shadow,
// slant, background box) so what you see in the card is what gets inserted.
interface TextPreset {
  id: string;
  name: string;
  category: string;
  content: string;
  params: Record<string, string | number | boolean>;
  previewBg: string;
}

const TEXT_PRESETS: TextPreset[] = [
  {
    id: "plain",
    name: "기본 텍스트",
    category: "기본",
    content: "텍스트를 입력하세요",
    params: { fontFamily: "Pretendard", fontSize: 6, color: "#FFFFFF", fontWeight: "600" },
    previewBg: "bg-slate-800",
  },
  {
    id: "caption-box",
    name: "자막 · 반투명 상자",
    category: "자막",
    content: "설명 자막 한 줄",
    params: {
      fontFamily: "Pretendard", fontSize: 3.4, color: "#FFFFFF", fontWeight: "bold",
      "background.enabled": true, "background.color": "#000000a6", "background.cornerRadius": 20,
      "background.paddingX": 18, "background.paddingY": 10, "transform.positionY": 560,
    },
    previewBg: "bg-slate-700",
  },
  {
    id: "caption-outline",
    name: "예능 자막 · 외곽선",
    category: "자막",
    content: "이거 완전 대박인데요?!",
    params: {
      fontFamily: "Black Han Sans", fontSize: 5, color: "#FACC15",
      "stroke.enabled": true, "stroke.color": "#000000", "stroke.width": 12, "transform.positionY": 560,
    },
    previewBg: "bg-sky-900",
  },
  {
    id: "title-shadow",
    name: "제목 · 그림자",
    category: "제목",
    content: "오늘의 제목",
    params: {
      fontFamily: "Gasoek One", fontSize: 9, color: "#FFFFFF",
      "shadow.enabled": true, "shadow.color": "#000000cc", "shadow.blur": 20, "shadow.offsetX": 4, "shadow.offsetY": 8,
      "transform.positionY": -560,
    },
    previewBg: "bg-gradient-to-r from-blue-900 to-indigo-900",
  },
  {
    id: "slant-impact",
    name: "기울임 강조",
    category: "강조",
    content: "지금 바로!",
    params: {
      fontFamily: "Do Hyeon", fontSize: 8, color: "#FFFFFF", skewX: 12,
      "background.enabled": true, "background.color": "#EF4444", "background.cornerRadius": 8,
      "background.paddingX": 24, "background.paddingY": 10,
    },
    previewBg: "bg-zinc-800",
  },
  {
    id: "serif-mood",
    name: "감성 명조",
    category: "감성",
    content: "가장 아름다운 순간",
    params: { fontFamily: "Gowun Batang", fontSize: 5, color: "#FEF3C7", fontWeight: "normal", letterSpacing: 2 },
    previewBg: "bg-gradient-to-r from-amber-950 to-stone-900",
  },
  {
    id: "hand",
    name: "손글씨 메모",
    category: "감성",
    content: "오늘도 수고했어",
    params: { fontFamily: "Nanum Pen Script", fontSize: 7, color: "#FFFFFF" },
    previewBg: "bg-emerald-950",
  },
  {
    id: "neon",
    name: "네온 강조",
    category: "강조",
    content: "SPECIAL",
    params: {
      fontFamily: "Bebas Neue", fontSize: 10, color: "#67E8F9", letterSpacing: 4,
      "shadow.enabled": true, "shadow.color": "#22D3EE", "shadow.blur": 40, "shadow.offsetX": 0, "shadow.offsetY": 0,
    },
    previewBg: "bg-slate-950",
  },
];

function presetPreviewStyle(preset: TextPreset): React.CSSProperties {
  const p = preset.params;
  const style: React.CSSProperties = {
    fontFamily: `"${String(p.fontFamily)}", Pretendard, sans-serif`,
    color: String(p.color ?? "#fff"),
    fontWeight: p.fontWeight === "bold" ? 700 : p.fontWeight === "normal" ? 400 : Number(p.fontWeight ?? 400),
    letterSpacing: p.letterSpacing ? `${Number(p.letterSpacing) / 4}px` : undefined,
    transform: p.skewX ? `skewX(${-Number(p.skewX)}deg)` : undefined,
    display: "inline-block",
  };
  if (p["stroke.enabled"]) {
    style.WebkitTextStroke = `2px ${String(p["stroke.color"])}`;
    style.paintOrder = "stroke fill";
  }
  if (p["shadow.enabled"]) style.textShadow = `0 2px 8px ${String(p["shadow.color"])}`;
  if (p["background.enabled"]) {
    style.background = String(p["background.color"]);
    style.padding = "1px 8px";
    style.borderRadius = 4;
  }
  return style;
}

export function TextView() {
  const editor = useEditor();
  useEffect(() => {
    for (const preset of TEXT_PRESETS) void ensureFontStylesheet(String(preset.params.fontFamily));
  }, []);

  const insertPreset = (preset: TextPreset, customTime?: MediaTime) => {
    const activeScene = editor.scenes.getActiveScene();
    if (!activeScene) return;

    const time = customTime ?? editor.playback.getCurrentTime();
    const rawElement = {
      ...DEFAULTS.text.element,
      name: preset.name,
      params: {
        ...DEFAULTS.text.element.params,
        content: preset.content,
        ...preset.params,
      },
    };

    const element = buildTextElement({
      raw: rawElement,
      startTime: time,
    });

    editor.timeline.insertElement({
      element,
      placement: { mode: "auto", trackType: "text" },
    });
  };

  return (
    <PanelView title="텍스트">
      <div className="flex flex-col gap-3 p-1">
        {/* 상단 1-클릭 빠른 추가 버튼 */}
        <Button
          onClick={() => insertPreset(TEXT_PRESETS[0])}
          className="w-full gap-2 bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-semibold h-9 shadow-md"
        >
          <HugeiconsIcon icon={PlusSignIcon} className="size-4" />
          <span>텍스트 추가</span>
        </Button>

        {/* 텍스트 & 자막 프리셋 그리드 */}
        <div className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mt-1 px-0.5">
          스타일 프리셋 · 누르면 재생 위치에 추가
        </div>

        <div className="grid grid-cols-1 gap-2">
          {TEXT_PRESETS.map((preset) => (
            <div
              key={preset.id}
              className="group relative flex items-center justify-between p-2.5 rounded-lg border border-border/60 bg-accent/20 hover:bg-accent/40 hover:border-primary/40 transition-all cursor-pointer"
              onClick={() => insertPreset(preset)}
            >
              <div className="min-w-0 flex-1 pr-2">
                <div className="flex items-center gap-1.5 mb-1">
                  <span className="text-[10px] font-medium px-1.5 py-0.2 rounded bg-black/40 text-muted-foreground">
                    {preset.category}
                  </span>
                  <span className="text-xs font-bold text-foreground truncate">{preset.name}</span>
                </div>
                <div className={`truncate rounded px-2 py-2 text-[15px] ${preset.previewBg}`}>
                  <span style={presetPreviewStyle(preset)}>{preset.content}</span>
                </div>
              </div>

              <Button
                variant="ghost"
                size="icon"
                className="size-8 shrink-0 rounded-full group-hover:bg-primary group-hover:text-primary-foreground transition-all"
                onClick={(e) => {
                  e.stopPropagation();
                  insertPreset(preset);
                }}
                title="타임라인에 추가"
              >
                <HugeiconsIcon icon={PlusSignIcon} className="size-4" />
              </Button>
            </div>
          ))}
        </div>
      </div>
    </PanelView>
  );
}
