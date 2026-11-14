"use client";

// fluma: host-provided effects (Craft effects in Fluma — ON HOLD: wiring kept,
// not expanded). Mounted via <VideoEditor effectProvider>, shown in the Effects
// tab (effects/components/assets-view.tsx) when present.
// Original note: host-provided effects. Heavy effects come from outside the browser
// (Fluma renders them with its Craft apps on the server), so the editor only
// lists what the provider offers and asks it to apply one to an element.
// Without a provider the editor falls back to the built-in effect registry
// (Gaussian blur), applied in-browser.
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { Search, Loader2 } from "lucide-react";
import { cn } from "../utils/ui";
import { useEditor } from "../editor/use-editor";

export type EffectTarget = "video" | "image" | "text";

export interface ProvidedEffect {
  id: string;
  /** Korean label shown on the card */
  label: string;
  /** group / category title */
  group: string;
  /** thumbnail URL (image or short looping video) */
  thumb?: string;
  description?: string;
}

export interface EffectProvider {
  list(target: EffectTarget): Promise<ProvidedEffect[]>;
  apply(args: {
    elementId: string;
    effectId: string;
    params?: Record<string, unknown>;
  }): Promise<void>;
}

const EffectProviderCtx = createContext<EffectProvider | null>(null);

export function EffectProviderScope({
  provider,
  children,
}: {
  provider: EffectProvider | null | undefined;
  children: ReactNode;
}) {
  return (
    <EffectProviderCtx.Provider value={provider ?? null}>
      {children}
    </EffectProviderCtx.Provider>
  );
}

export function useEffectProvider(): EffectProvider | null {
  return useContext(EffectProviderCtx);
}

/** Maps any timeline element type to the provider's target vocabulary. */
export function effectTargetFor(elementType: string | undefined): EffectTarget | null {
  if (elementType === "video") return "video";
  if (elementType === "text") return "text";
  if (elementType === "image" || elementType === "sticker" || elementType === "graphic") {
    return "image";
  }
  return null;
}

export const EFFECT_TARGET_LABELS: Record<EffectTarget, string> = {
  video: "영상",
  image: "이미지",
  text: "텍스트",
};

const listCache = new WeakMap<EffectProvider, Map<EffectTarget, Promise<ProvidedEffect[]>>>();

function useProvidedEffects(provider: EffectProvider, target: EffectTarget) {
  const [state, setState] = useState<{
    status: "loading" | "ready" | "error";
    effects: ProvidedEffect[];
    error?: string;
  }>({ status: "loading", effects: [] });

  useEffect(() => {
    let alive = true;
    let perProvider = listCache.get(provider);
    if (!perProvider) {
      perProvider = new Map();
      listCache.set(provider, perProvider);
    }
    let promise = perProvider.get(target);
    if (!promise) {
      promise = provider.list(target);
      perProvider.set(target, promise);
      promise.catch(() => perProvider?.delete(target));
    }
    setState({ status: "loading", effects: [] });
    promise
      .then((effects) => alive && setState({ status: "ready", effects }))
      .catch((error: unknown) =>
        alive &&
        setState({
          status: "error",
          effects: [],
          error: error instanceof Error ? error.message : String(error),
        }),
      );
    return () => {
      alive = false;
    };
  }, [provider, target]);

  return state;
}

/**
 * Searchable, grouped grid of provider effects. Clicking a card applies the
 * effect to `elementId` (disabled with a hint when nothing is selected).
 */
export function ProvidedEffectBrowser({
  provider,
  target,
  elementId,
  compact = false,
}: {
  provider: EffectProvider;
  target: EffectTarget;
  elementId: string | null;
  compact?: boolean;
}) {
  const { status, effects, error } = useProvidedEffects(provider, target);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ kind: "ok" | "error"; text: string } | null>(null);

  const groups = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filtered = q
      ? effects.filter(
          (e) =>
            e.label.toLowerCase().includes(q) ||
            e.id.toLowerCase().includes(q) ||
            e.group.toLowerCase().includes(q) ||
            (e.description ?? "").toLowerCase().includes(q),
        )
      : effects;
    const map = new Map<string, ProvidedEffect[]>();
    for (const effect of filtered) {
      const list = map.get(effect.group) ?? [];
      list.push(effect);
      map.set(effect.group, list);
    }
    return [...map.entries()];
  }, [effects, query]);

  const apply = useCallback(
    async (effect: ProvidedEffect) => {
      if (!elementId || busy) return;
      setBusy(effect.id);
      setMessage(null);
      try {
        await provider.apply({ elementId, effectId: effect.id });
        setMessage({ kind: "ok", text: `'${effect.label}' 적용됨` });
      } catch (err) {
        setMessage({
          kind: "error",
          text: `적용 실패: ${err instanceof Error ? err.message : String(err)}`,
        });
      } finally {
        setBusy(null);
      }
    },
    [busy, elementId, provider],
  );

  return (
    <div className="flex flex-col gap-2">
      <div className="border-input bg-accent flex h-8 items-center gap-2 rounded-md border px-2.5">
        <Search className="size-3.5 shrink-0 opacity-60" />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={
            status === "ready" ? `효과 검색 (${effects.length}개)` : "효과 검색"
          }
          className="h-full min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
        />
      </div>
      {!elementId && (
        <p className="rounded-md bg-accent/60 px-2.5 py-2 text-xs text-muted-foreground">
          타임라인에서 {EFFECT_TARGET_LABELS[target]} 항목을 선택하면 눌러서 바로 적용할 수 있어요.
        </p>
      )}
      {message && (
        <p
          className={cn(
            "rounded-md px-2.5 py-1.5 text-xs",
            message.kind === "ok" ? "bg-constructive/15 text-constructive" : "bg-destructive/15 text-destructive",
          )}
        >
          {message.text}
        </p>
      )}
      {status === "loading" && (
        <div className="flex items-center justify-center gap-2 py-8 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" /> 효과 목록을 불러오는 중…
        </div>
      )}
      {status === "error" && (
        <p className="py-6 text-center text-sm text-destructive">효과 목록을 불러오지 못했습니다{error ? ` — ${error}` : ""}</p>
      )}
      {status === "ready" && groups.length === 0 && (
        <p className="py-6 text-center text-sm text-muted-foreground">찾는 효과가 없습니다</p>
      )}
      {groups.map(([group, list]) => (
        <section key={group} className="flex flex-col gap-1.5">
          <h4 className="px-0.5 pt-1 text-[11px] font-medium text-muted-foreground">
            {group} <span className="opacity-60">{list.length}</span>
          </h4>
          <div
            className="grid gap-1.5"
            style={{ gridTemplateColumns: `repeat(auto-fill, minmax(${compact ? 76 : 92}px, 1fr))` }}
          >
            {list.map((effect) => (
              <button
                key={effect.id}
                type="button"
                disabled={!elementId || Boolean(busy)}
                onClick={() => void apply(effect)}
                title={effect.description ?? effect.label}
                className={cn(
                  "group flex flex-col gap-1 rounded-md p-1 text-left enabled:hover:bg-accent disabled:cursor-not-allowed",
                  !elementId && "opacity-70",
                )}
              >
                <span className="relative block aspect-square w-full overflow-hidden rounded-md bg-accent">
                  {effect.thumb ? (
                    /\.(mp4|webm)(\?|$)/i.test(effect.thumb) ? (
                      <video src={effect.thumb} muted loop autoPlay playsInline className="size-full object-cover" />
                    ) : (
                      <img src={effect.thumb} alt="" loading="lazy" className="size-full object-cover" />
                    )
                  ) : (
                    <span className="flex size-full items-center justify-center px-1 text-center text-[11px] text-muted-foreground">
                      {effect.label}
                    </span>
                  )}
                  {busy === effect.id && (
                    <span className="absolute inset-0 flex items-center justify-center bg-black/50">
                      <Loader2 className="size-5 animate-spin text-white" />
                    </span>
                  )}
                </span>
                <span className="line-clamp-2 text-[11px] leading-tight text-foreground/90">{effect.label}</span>
              </button>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

// ── Effects tab body when a provider is present (effects/components/assets-view.tsx hook)

function useSelectedSingleElement() {
  const editor = useEditor();
  const selected = useEditor((e) => e.selection.getSelectedElements());
  useEditor((e) => e.scenes.getActiveSceneOrNull());
  if (selected.length !== 1) return null;
  const [withTrack] = editor.timeline.getElementsWithTracks({ elements: selected });
  return withTrack ?? null;
}

export function ProviderEffects({ provider }: { provider: EffectProvider }) {
  const selection = useSelectedSingleElement();
  const selectedTarget = effectTargetFor(selection?.element.type);
  const [target, setTarget] = useState<EffectTarget>(selectedTarget ?? "video");

  useEffect(() => {
    if (selectedTarget) setTarget(selectedTarget);
  }, [selectedTarget]);

  const elementId = selection && selectedTarget === target ? selection.element.id : null;

  return (
    <div className="flex flex-col gap-2.5 pb-3">
      <div className="flex gap-1 rounded-md bg-accent/50 p-0.5">
        {(Object.keys(EFFECT_TARGET_LABELS) as EffectTarget[]).map((key) => (
          <button
            key={key}
            type="button"
            onClick={() => setTarget(key)}
            className={cn(
              "h-7 flex-1 rounded text-xs",
              key === target ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {EFFECT_TARGET_LABELS[key]}
          </button>
        ))}
      </div>
      {selection && elementId && (
        <p className="truncate px-0.5 text-xs text-muted-foreground">
          적용 대상: <span className="text-foreground">{selection.element.name}</span>
        </p>
      )}
      <ProvidedEffectBrowser provider={provider} target={target} elementId={elementId} />
    </div>
  );
}
