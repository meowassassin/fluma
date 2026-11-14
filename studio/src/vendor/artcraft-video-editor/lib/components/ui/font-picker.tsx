"use client";

// fluma: searchable, grouped font picker. Every row is drawn in its own face
// (a tiny glyph subset is fetched lazily when the row scrolls into view), the
// list comes from fonts/catalog.ts, and recently used fonts float to the top.
// Replaces the upstream atlas/sprite picker whose assets are not shipped.
import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, Search, Check } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "./popover";
import { cn } from "../../utils/ui";
import {
  FONT_CATALOG,
  FONT_CATEGORY_LABELS,
  getFontLabel,
  type CatalogFont,
  type FontCategoryKey,
} from "../../fonts/catalog";
import {
  ensureFontStylesheet,
  loadPreviewFont,
  previewSampleFor,
} from "../../fonts/google-fonts";

const RECENT_KEY = "fluma-veditor-recent-fonts";

function readRecent(): string[] {
  try {
    const raw = localStorage.getItem(RECENT_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((v) => typeof v === "string").slice(0, 6) : [];
  } catch {
    return [];
  }
}

function pushRecent(family: string) {
  try {
    const next = [family, ...readRecent().filter((f) => f !== family)].slice(0, 6);
    localStorage.setItem(RECENT_KEY, JSON.stringify(next));
  } catch {
    // storage unavailable — recents are a convenience only
  }
}

interface FontPickerProps {
  value?: string;
  /** upstream prop name, kept for the masks tab */
  defaultValue?: string;
  onValueChange?: (value: string) => void;
  className?: string;
}

export function FontPicker({ value, defaultValue, onValueChange, className }: FontPickerProps) {
  const current = value ?? defaultValue ?? "Pretendard";
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [recent, setRecent] = useState<string[]>([]);
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) setRecent(readRecent());
    else setSearch("");
  }, [open]);

  // Make sure the trigger itself shows the selected font in its face.
  useEffect(() => {
    void ensureFontStylesheet(current);
  }, [current]);

  const groups = useMemo(() => {
    const q = search.trim().toLowerCase();
    const match = (font: CatalogFont) =>
      !q ||
      font.family.toLowerCase().includes(q) ||
      (font.label ?? "").toLowerCase().includes(q) ||
      FONT_CATEGORY_LABELS[font.category].includes(q);
    const result: Array<{ key: string; title: string; fonts: CatalogFont[] }> = [];
    if (!q && recent.length > 0) {
      const fonts = recent
        .map((family) => FONT_CATALOG.find((f) => f.family === family))
        .filter((f): f is CatalogFont => Boolean(f));
      if (fonts.length) result.push({ key: "recent", title: "최근 사용", fonts });
    }
    for (const category of Object.keys(FONT_CATEGORY_LABELS) as FontCategoryKey[]) {
      const fonts = FONT_CATALOG.filter((f) => f.category === category && match(f));
      if (fonts.length) result.push({ key: category, title: FONT_CATEGORY_LABELS[category], fonts });
    }
    // Free-form family typed by the user (any Google Fonts family works).
    if (q && !FONT_CATALOG.some((f) => f.family.toLowerCase() === q)) {
      result.push({
        key: "custom",
        title: "직접 입력",
        fonts: [{ family: search.trim(), label: `"${search.trim()}" 직접 사용 (Google Fonts 이름)`, category: "en-sans", source: "google", weights: [400, 700] }],
      });
    }
    return result;
  }, [search, recent]);

  const select = (family: string) => {
    pushRecent(family);
    void ensureFontStylesheet(family);
    onValueChange?.(family);
    setOpen(false);
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        className={cn(
          "border-input bg-accent flex h-8 w-full items-center justify-between gap-2 rounded-md border px-2.5 text-sm hover:border-foreground/30",
          className,
        )}
      >
        <span className="truncate" style={{ fontFamily: `"${current}", Pretendard, sans-serif` }}>
          {getFontLabel(current)}
        </span>
        <ChevronDown className="size-3.5 shrink-0 opacity-60" />
      </PopoverTrigger>
      <PopoverContent
        className="w-80 p-0 overflow-hidden"
        align="start"
        side="left"
        sideOffset={8}
        onOpenAutoFocus={(event) => {
          event.preventDefault();
          searchRef.current?.focus();
        }}
      >
        <div className="flex items-center gap-2 border-b border-border px-3 h-10">
          <Search className="size-3.5 shrink-0 opacity-60" />
          <input
            ref={searchRef}
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder={`글꼴 검색 (${FONT_CATALOG.length}종)`}
            className="h-full flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          />
        </div>
        <div className="max-h-[22rem] overflow-y-auto py-1" data-font-list>
          {groups.length === 0 && (
            <div className="py-6 text-center text-sm text-muted-foreground">찾는 글꼴이 없습니다</div>
          )}
          {groups.map((group) => (
            <div key={group.key}>
              <div className="sticky top-0 z-10 bg-popover px-3 pt-2 pb-1 text-[11px] font-medium text-muted-foreground">
                {group.title}
              </div>
              {group.fonts.map((font) => (
                <FontRow
                  key={`${group.key}:${font.family}`}
                  font={font}
                  selected={font.family === current}
                  onSelect={select}
                />
              ))}
            </div>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
}

function FontRow({
  font,
  selected,
  onSelect,
}: {
  font: CatalogFont;
  selected: boolean;
  onSelect: (family: string) => void;
}) {
  const ref = useRef<HTMLButtonElement>(null);
  // Only catalog Google fonts get a glyph-subset preview; free-typed names
  // (possibly not real families) render in the UI font.
  const inCatalog = FONT_CATALOG.some((f) => f.family === font.family);
  const [face, setFace] = useState<string | null>(
    font.source === "google" && inCatalog ? null : inCatalog ? font.family : "Pretendard",
  );
  const label = font.label ?? font.family;

  useEffect(() => {
    if (face) return;
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        observer.disconnect();
        void loadPreviewFont(font.family, previewSampleFor(font.family)).then(setFace);
      }
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [face, font.family]);

  return (
    <button
      ref={ref}
      type="button"
      onClick={() => onSelect(font.family)}
      className={cn(
        "flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-accent",
        selected && "bg-accent",
      )}
      title={font.family}
    >
      <span className="min-w-0 flex-1">
        <span
          className="block truncate text-[17px] leading-6 text-foreground"
          style={{ fontFamily: face ? `"${face}"` : "Pretendard", opacity: face ? 1 : 0.45 }}
        >
          {label}
          <span className="ml-2 text-[13px] opacity-60">가나다 Aa</span>
        </span>
        {font.label && font.label !== font.family && (
          <span className="block truncate text-[10.5px] text-muted-foreground">{font.family}</span>
        )}
      </span>
      {selected && <Check className="size-3.5 shrink-0 text-primary" />}
    </button>
  );
}
