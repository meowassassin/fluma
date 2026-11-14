/* 편집기 ↔ Craft 효과 모듈 연결.
   요소(글자 · 영상 · 그림) 하나의 모양을 서버로 보내 EffectCraft 로 효과 · 프리셋 · 레시피를 입혀 투명 층(webm)으로 렌더하고(engine/craft/fxlayer.py),
   그 층을 같은 시각 · 길이로 타임라인에 올린 뒤 원래 요소는 숨긴다(지우지 않음 — 다시 보이게 하면 되돌릴 수 있다). */
import {
  EditorCore,
  buildElementFromMedia,
  mediaTimeToSeconds,
  type EffectProvider,
  type EffectTarget,
  type ProvidedEffect,
  type TimelineElement,
} from "../../vendor/artcraft/video-editor/src";
import { processMediaAssets } from "../../vendor/artcraft/video-editor/src/lib/media/processing";
import { flumaMediaUrl, flumaToast, registerFlumaMedia } from "./adapters/fluma-adapters";

export type FxTarget = "text" | "video" | "image";
export interface FxParam { id: string; name: string; type: string; default?: unknown; min?: number; max?: number; options?: { label: string; value: unknown }[] }
export interface FxItem { kind: "effect" | "preset" | "textPreset" | "recipe"; id: string; label: string; group: string; summary: string; thumb?: string | null; params?: FxParam[] }

const lists = new Map<FxTarget, Promise<FxItem[]>>();
export function listCraftFx(target: FxTarget): Promise<FxItem[]> {
  if (!lists.has(target)) {
    lists.set(target, fetch(`/api/craft-fx?target=${target}`).then(async (r) => {
      if (!r.ok) { lists.delete(target); throw new Error("효과 목록을 불러오지 못했습니다"); }
      return r.json() as Promise<FxItem[]>;
    }));
  }
  return lists.get(target)!;
}

type P = Record<string, unknown>;
const num = (p: P, keys: string[], d = 0) => { for (const k of keys) if (typeof p[k] === "number") return p[k] as number; return d; };
const str = (p: P, keys: string[], d = "") => { for (const k of keys) if (typeof p[k] === "string" && p[k]) return p[k] as string; return d; };
const sec = (t: unknown) => mediaTimeToSeconds({ time: t as never });

export function findElement(elementId: string): { trackId: string; element: TimelineElement } | null {
  const sc = EditorCore.getInstance().scenes.getActiveScene();
  const tr = sc.tracks as unknown as { main: { id: string; elements: TimelineElement[] }; overlay: { id: string; elements: TimelineElement[] }[]; audio?: { id: string; elements: TimelineElement[] }[] };
  for (const t of [tr.main, ...tr.overlay, ...(tr.audio ?? [])]) {
    const e = t.elements.find((x) => x.id === elementId);
    if (e) return { trackId: t.id, element: e };
  }
  return null;
}

export const targetOf = (e: TimelineElement): FxTarget | null =>
  e.type === "text" ? "text" : e.type === "video" ? "video" : e.type === "image" ? "image" : null;

/** 편집기 요소 → fxlayer spec(위치는 캔버스 가운데 기준 px) */
export function elementSpec(e: TimelineElement) {
  const ed = EditorCore.getInstance();
  const st = ed.project.getActive()!.settings as unknown as { canvasSize: { width: number; height: number }; fps: { numerator: number; denominator: number } };
  const W = st.canvasSize.width, H = st.canvasSize.height;
  const p = ((e as unknown as { params?: P }).params ?? {}) as P;
  const base = { canvas: { w: W, h: H, fps: st.fps.numerator / (st.fps.denominator || 1) }, duration: Math.round(sec(e.duration) * 1000) / 1000 };
  const x = num(p, ["transform.positionX"]), y = num(p, ["transform.positionY"]);
  if (e.type === "text") {
    return { ...base, target: "text" as const, text: {
      content: str(p, ["content"]), fontFamily: str(p, ["fontFamily"], "Pretendard"),
      fontPx: num(p, ["fontSize"], 15) * H / 90,                       // 편집기 글자 크기 = 캔버스 높이/90 배율
      bold: ["bold", "700", "800", "900"].includes(String(p.fontWeight ?? "")), italic: p.fontStyle === "italic",
      color: str(p, ["color"], "#ffffff"), align: str(p, ["textAlign"], "center"),
      tracking: num(p, ["letterSpacing"]) * 10, leading: num(p, ["lineHeight"], 1.2),
      skew: num(p, ["skewX", "skew", "transform.skewX"]),
      ...(num(p, ["stroke.width", "strokeWidth"]) ? { stroke: { color: str(p, ["stroke.color", "strokeColor"], "#000000"), width: num(p, ["stroke.width", "strokeWidth"]) * H / 1920 } } : {}),
      x, y } };
  }
  const mediaId = (e as unknown as { mediaId?: string }).mediaId ?? "";
  const src = flumaMediaUrl(mediaId);
  if (!src) throw new Error("이 요소의 원본 파일 주소를 찾지 못했습니다");
  return { ...base, target: (e.type === "image" ? "image" : "video") as FxTarget, media: {
    src, trimStart: sec((e as unknown as { trimStart?: unknown }).trimStart ?? 0),
    x, y, scaleX: num(p, ["transform.scaleX", "transform.scale"], 1), scaleY: num(p, ["transform.scaleY", "transform.scale"], 1), rotate: num(p, ["transform.rotate"]) } };
}

/** 효과를 입힌 층을 만들어 타임라인에 올린다. 반환: 새 요소 이름 */
export async function applyCraftFx(projectId: string, elementId: string, item: FxItem, params: Record<string, unknown> = {}): Promise<string> {
  const hit = findElement(elementId); if (!hit) throw new Error("요소를 찾지 못했습니다");
  const { trackId, element } = hit;
  const spec = { ...elementSpec(element), effect: { kind: item.kind, id: item.id, params } };
  const r = await fetch(`/api/projects/${projectId}/editor/craft-fx`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(spec) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok || !j.url) throw new Error(j?.error?.message || "Craft 효과를 렌더하지 못했습니다");

  const ed = EditorCore.getInstance();
  const name = `${item.label} · ${element.name}`;
  const id = `craftfx:${String(j.url).split("/").pop()}`;
  registerFlumaMedia(id, j.url, "video/webm");
  const blob = await (await fetch(j.url)).blob();
  const [asset] = await processMediaAssets({
    files: [new File([blob], `${name}.webm`, { type: "video/webm" })], toast: flumaToast, mediaSource: ed.adapters.mediaSource,
    existingHandles: [{ id, kind: "video" }], existingResolved: [{ url: j.url, mime: "video/webm" }],
  });
  if (!asset) throw new Error("렌더한 층을 불러오지 못했습니다");
  await ed.media.addMediaAsset({ asset });
  const el = buildElementFromMedia({ mediaId: asset.id, mediaType: "video", name, duration: element.duration, startTime: element.startTime });
  ed.timeline.insertElement({ element: el, placement: { mode: "auto" } });
  ed.timeline.updateElements({ updates: [{ trackId, elementId, patch: { hidden: true } as Partial<TimelineElement> }] });
  return name;
}

/** VideoEditor effectProvider 어댑터 — 왼쪽 '효과' 탭 및 속성 패널의 '효과' 탭에 Craft 효과 · 프리셋 · 레시피 카탈로그를 공급 */
export function createCraftEffectProvider(projectId: string): EffectProvider {
  const itemByKey = new Map<string, FxItem>();
  return {
    async list(target: EffectTarget): Promise<ProvidedEffect[]> {
      const items = await listCraftFx(target);
      return items.map((item) => {
        const key = `${item.kind}:${item.id}`;
        itemByKey.set(key, item);
        itemByKey.set(item.id, item);
        return {
          id: key,
          label: item.label,
          group: item.group,
          thumb: item.thumb ?? undefined,
          description: item.summary,
        };
      });
    },
    async apply({ elementId, effectId, params }) {
      let item = itemByKey.get(effectId);
      if (!item) {
        const hit = findElement(elementId);
        const t = hit ? targetOf(hit.element) : null;
        if (t) {
          const all = await listCraftFx(t);
          for (const x of all) {
            itemByKey.set(`${x.kind}:${x.id}`, x);
            itemByKey.set(x.id, x);
          }
          item = itemByKey.get(effectId);
        }
      }
      if (!item) throw new Error(`효과를 찾지 못했습니다: ${effectId}`);
      const layerName = await applyCraftFx(projectId, elementId, item, params ?? {});
      flumaToast.success(`Craft 효과 층 추가됨: ${layerName}`);
    },
  };
}
