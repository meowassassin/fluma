"use client";

// fluma: Media tab kind filter (전체 · 영상 · 오디오 · 이미지) + name search.
// Hooked into panels/assets/views/assets.tsx with three lines: filter the
// list, render the bar, show an empty hint when the filter hides everything.
import { create } from "zustand";
import { Film, Image as ImageIcon, LayoutGrid, Music, Search, X } from "lucide-react";
import { cn } from "../utils/ui";

export type MediaKindFilter = "all" | "video" | "audio" | "image";

interface MediaFilterState {
  kind: MediaKindFilter;
  query: string;
  set: (patch: Partial<Pick<MediaFilterState, "kind" | "query">>) => void;
}

export const useFlumaMediaFilter = create<MediaFilterState>((set) => ({
  kind: "all",
  query: "",
  set: (patch) => set(patch),
}));

export function isFlumaMediaFilterActive(state: Pick<MediaFilterState, "kind" | "query">): boolean {
  return state.kind !== "all" || state.query.trim() !== "";
}

export function applyFlumaMediaFilter<T extends { type: string; name: string }>(
  items: T[],
  state: Pick<MediaFilterState, "kind" | "query">,
): T[] {
  const q = state.query.trim().toLowerCase();
  return items.filter(
    (item) => (state.kind === "all" || item.type === state.kind) && (!q || item.name.toLowerCase().includes(q)),
  );
}

const KINDS: Array<{ kind: MediaKindFilter; label: string; Icon: typeof Film }> = [
  { kind: "all", label: "전체", Icon: LayoutGrid },
  { kind: "video", label: "영상", Icon: Film },
  { kind: "audio", label: "오디오", Icon: Music },
  { kind: "image", label: "이미지", Icon: ImageIcon },
];

export function FlumaMediaFilterBar({ items }: { items: ReadonlyArray<{ type: string }> }) {
  const { kind, query, set } = useFlumaMediaFilter();
  const count = (k: MediaKindFilter) => (k === "all" ? items.length : items.filter((i) => i.type === k).length);
  return (
    <div className="flex items-center gap-1.5 pb-2">
      <div className="flex shrink-0 items-center gap-0.5">
        {KINDS.map(({ kind: k, label, Icon }) => (
          <button
            key={k}
            type="button"
            title={`${label} (${count(k)})`}
            aria-label={`${label} (${count(k)})`}
            aria-pressed={kind === k}
            onClick={() => set({ kind: k })}
            className={cn(
              "flex size-7 items-center justify-center rounded-md [&_svg]:size-3.5",
              kind === k ? "bg-secondary text-foreground" : "text-muted-foreground hover:bg-accent hover:text-foreground",
            )}
          >
            <Icon />
          </button>
        ))}
      </div>
      <div className="relative flex min-w-0 flex-1 items-center">
        <Search className="pointer-events-none absolute left-2 size-3 text-muted-foreground" />
        <input
          type="text"
          value={query}
          onChange={(e) => set({ query: e.target.value })}
          placeholder="이름 검색"
          className="h-7 w-full rounded-md border border-border bg-accent pl-7 pr-6 text-xs text-foreground placeholder:text-muted-foreground"
        />
        {query && (
          <button
            type="button"
            aria-label="검색어 지우기"
            onClick={() => set({ query: "" })}
            className="absolute right-1.5 text-muted-foreground hover:text-foreground"
          >
            <X className="size-3" />
          </button>
        )}
      </div>
    </div>
  );
}

export function FlumaMediaFilterEmpty() {
  const { query, set } = useFlumaMediaFilter();
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-4 py-10 text-center">
      <p className="text-xs text-muted-foreground">
        {query ? `"${query}" 검색 결과가 없습니다` : "이 종류의 미디어가 없습니다"}
      </p>
      <button
        type="button"
        onClick={() => set({ kind: "all", query: "" })}
        className="h-7 rounded-md border border-border px-3 text-xs hover:bg-accent"
      >
        필터 초기화
      </button>
    </div>
  );
}
