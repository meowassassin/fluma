"use client";

// fluma: "자막 목록" — replaces the upstream "Captions view coming soon"
// placeholder. Lists every text element in time order; click to jump + select,
// edit wording in place, and copy the selected caption's look to the others.
import { useMemo, useState } from "react";
import { PanelView } from "../../panels/assets/views/base-panel";
import { useEditor } from "../../editor/use-editor";
import { Button } from "../../components/ui/button";
import { TICKS_PER_SECOND } from "../../wasm";
import { cn } from "../../utils/ui";
import type { TextElement } from "../../timeline/types";
import type { ParamValues } from "../../params";

// Look-only params copied by "스타일 맞추기" (never content / position).
const STYLE_KEYS = [
  "fontFamily",
  "fontSize",
  "fontWeight",
  "fontStyle",
  "skewX",
  "color",
  "textAlign",
  "textDecoration",
  "letterSpacing",
  "lineHeight",
  "stroke.enabled",
  "stroke.color",
  "stroke.width",
  "shadow.enabled",
  "shadow.color",
  "shadow.blur",
  "shadow.offsetX",
  "shadow.offsetY",
  "background.enabled",
  "background.color",
  "background.cornerRadius",
  "background.paddingX",
  "background.paddingY",
];

function formatTime(ticks: number): string {
  const seconds = ticks / TICKS_PER_SECOND;
  const m = Math.floor(seconds / 60);
  const s = seconds - m * 60;
  return `${m}:${s.toFixed(1).padStart(4, "0")}`;
}

export function CaptionsView() {
  const editor = useEditor();
  const scene = useEditor((e) => e.scenes.getActiveSceneOrNull());
  const selected = useEditor((e) => e.selection.getSelectedElements());
  const currentTime = useEditor((e) => e.playback.getCurrentTime());
  const [notice, setNotice] = useState<string | null>(null);

  const rows = useMemo(() => {
    if (!scene) return [];
    const list: Array<{ trackId: string; trackName: string; element: TextElement }> = [];
    for (const track of scene.tracks.overlay) {
      for (const element of track.elements) {
        if (element.type === "text") {
          list.push({ trackId: track.id, trackName: track.name, element: element as TextElement });
        }
      }
    }
    return list.sort((a, b) => a.element.startTime - b.element.startTime);
  }, [scene]);

  const selectedRow = rows.find((row) =>
    selected.some((s) => s.elementId === row.element.id),
  );

  const jumpTo = (row: (typeof rows)[number]) => {
    editor.playback.seek({ time: row.element.startTime });
    editor.selection.setSelectedElements({
      elements: [{ trackId: row.trackId, elementId: row.element.id }],
    });
  };

  const setContent = (row: (typeof rows)[number], content: string) => {
    if (content === row.element.params.content) return;
    editor.timeline.updateElements({
      updates: [
        {
          trackId: row.trackId,
          elementId: row.element.id,
          patch: { params: { ...row.element.params, content } },
        },
      ],
    });
  };

  const matchStyle = () => {
    if (!selectedRow) return;
    const source = selectedRow.element.params;
    const style: ParamValues = {};
    for (const key of STYLE_KEYS) {
      if (source[key] !== undefined) style[key] = source[key];
    }
    const targets = rows.filter(
      (row) => row.trackId === selectedRow.trackId && row.element.id !== selectedRow.element.id,
    );
    if (targets.length === 0) return;
    editor.timeline.updateElements({
      updates: targets.map((row) => ({
        trackId: row.trackId,
        elementId: row.element.id,
        patch: { params: { ...row.element.params, ...style } },
      })),
    });
    setNotice(`같은 트랙 자막 ${targets.length}개에 스타일을 맞췄습니다`);
  };

  return (
    <PanelView
      title={`자막 목록 ${rows.length}`}
      actions={
        <Button
          size="sm"
          variant="secondary"
          className="h-7 text-xs"
          disabled={!selectedRow}
          onClick={matchStyle}
          title="선택한 자막의 글꼴 · 색 · 외곽선 · 배경을 같은 트랙의 다른 자막에 복사"
        >
          스타일 맞추기
        </Button>
      }
    >
      {notice && (
        <p className="mb-2 rounded-md bg-constructive/15 px-2.5 py-1.5 text-xs text-constructive">{notice}</p>
      )}
      {rows.length === 0 && (
        <p className="py-8 text-center text-sm text-muted-foreground">
          텍스트 트랙에 자막이 없습니다. 텍스트 탭에서 추가하세요.
        </p>
      )}
      <ol className="flex flex-col gap-1 pb-3">
        {rows.map((row) => {
          const isSelected = row.element.id === selectedRow?.element.id;
          const isNow =
            currentTime >= row.element.startTime &&
            currentTime < row.element.startTime + row.element.duration;
          return (
            <li
              key={row.element.id}
              className={cn(
                "group flex gap-2 rounded-md border px-2 py-1.5",
                isSelected ? "border-primary/60 bg-primary/10" : "border-transparent hover:bg-accent/60",
              )}
            >
              <button
                type="button"
                onClick={() => jumpTo(row)}
                className={cn(
                  "w-12 shrink-0 pt-0.5 text-left font-mono text-[11px] tabular-nums",
                  isNow ? "text-primary" : "text-muted-foreground",
                )}
                title="이 자막으로 이동"
              >
                {formatTime(row.element.startTime)}
              </button>
              <textarea
                defaultValue={String(row.element.params.content ?? "")}
                key={`${row.element.id}:${String(row.element.params.content ?? "")}`}
                rows={1}
                onFocus={() => jumpTo(row)}
                onBlur={(event) => setContent(row, event.currentTarget.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    event.currentTarget.blur();
                  }
                }}
                className="min-h-6 w-full resize-none bg-transparent text-sm leading-6 outline-none [field-sizing:content]"
                style={{ fontFamily: `"${String(row.element.params.fontFamily ?? "Pretendard")}", Pretendard, sans-serif` }}
              />
            </li>
          );
        })}
      </ol>
    </PanelView>
  );
}
