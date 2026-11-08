/* 트렌드 데이터 — 모은 쇼츠(index.json, trends.py 가 씀) · 내 판별(찜 · 보류 · 제외) · 엑스레이(분해 분석) */
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { qc, qk } from "../../lib/queries";
import { t as tt } from "../../lib/i18n";

export interface Analysis { analyzed_sec?: number; cuts?: number[]; avg_shot_sec: number | null; first_cut_sec: number | null; rhythm: string; text_zone: string; text_bands?: number[]; motion_level: string; brightness?: number; saturation?: number; palette: { hex: string; w?: number }[]; sheet?: string }
export interface Item { analysis?: Analysis; id: string; title: string; views: number | null; tag: string; via?: "search" | "hashtag"; category: string; label: string; request: string; hook: string; thumb: string | null; url: string; visual?: string; visual_p?: Record<string, number> }
export interface Req { id: string; text: string; label: string; tags: string[]; queries?: string[]; count: number; status: "running" | "done" | "failed" | "stopped"; at?: string; want?: string[] | null; error?: string }
export type Pick = "keep" | "maybe" | "skip";

export const VIS: Record<string, string> = { "2d": "2D", pixel: "픽셀", live: "실사", screen: "화면 · 게임", "3d": "3D" };
export const VIS_ORDER = ["2d", "pixel", "screen", "live", "3d"];
export const PICK: Record<Pick, { label: string; key: string; icon: string }> = {
  keep: { label: "찜", key: "1", icon: "check" },
  maybe: { label: "보류", key: "2", icon: "history" },
  skip: { label: "제외", key: "3", icon: "close" },
};
export const src = (x: { tag: string; via?: string }) => (x.via === "search" ? tt("검색 “{tag}”", { tag: x.tag }) : `#${x.tag}`);
/** 분석 스크립트가 보내는 진행 단계 문구 → 지금 언어. “레이어 분해 중 (3/8)” 처럼 뒤에 붙은 숫자는 그대로 둔다 */
export const stageT = (s?: string | null) => { if (!s) return ""; const m = s.match(/^(.*\S)\s*(\(?\d+\/\d+\)?)$/); return m ? `${tt(m[1])} ${m[2]}` : tt(s); };

export const useTrendIndex = () => useQuery({
  queryKey: qk.trends, staleTime: 30_000,
  queryFn: async ({ signal }) => {
    const r = await fetch("/api/public/trends/index.json", { signal });
    if (!r.ok) return { requests: [] as Req[], items: [] as Item[] };
    const d = await r.json(); return { requests: (d.requests ?? []) as Req[], items: (d.items ?? []) as Item[] };
  },
});

/* ---------- 판별 ---------- */
const PICKS = ["trend-picks"] as const;
export const usePicks = () => useQuery({
  queryKey: PICKS, staleTime: Infinity,
  queryFn: async ({ signal }) => { const r = await fetch("/api/trends/picks", { signal }); return r.ok ? (await r.json() as Record<string, { pick: Pick | null; note?: string; at: number }>) : {}; },
});
export async function setPick(vid: string, pick: Pick | null) {
  const prev = qc.getQueryData<Record<string, { pick: Pick | null; at: number }>>(PICKS) ?? {};
  const next = { ...prev }; if (pick) next[vid] = { ...(prev[vid] || {}), pick, at: Date.now() }; else delete next[vid];
  qc.setQueryData(PICKS, next);   // 바로 반영, 실패하면 되돌림
  try {
    const r = await fetch(`/api/trends/picks/${vid}`, { method: "PUT", headers: { "content-type": "application/json", "x-fluma-client": "trends" }, body: JSON.stringify({ pick }) });
    if (!r.ok) throw new Error(String(r.status));
  } catch { qc.setQueryData(PICKS, prev); toast.error(tt("판별을 저장하지 못했어요")); }
}

/* ---------- 엑스레이 ---------- */
export interface XShot { i: number; start: number; end: number; frame: string; camera?: { kind: string; pan: number[]; zoom: number; motion: number };
  subject: { area: number; parts: number; bbox: number[] | null; faces?: number; cut?: string; bg?: string; group?: string }; palette: { hex: string; w: number }[] }
export interface Xray {
  id: string; url: string; at: string; took_sec: number;
  video: { duration: number; w: number; h: number; fps: number; audio: boolean; src: string };
  shots: XShot[]; subjects: { id: string; shots: number[]; cover?: string }[];
  text: { start: number; end: number; band: string; box: number[] }[];
  speech: { start: number; end: number; text: string; words: { w: string; s: number; e: number }[] }[];
  sound: { has_audio: boolean; bpm?: number | null; beat_conf?: number; beats?: number[]; music?: number[]; sfx?: { t: number; kind: string; strength: number }[]; envelope?: number[]; envelope_hz?: number };
  recipe: string[];
  stems?: { vocals: string; music: string } | null;
}
const XLIST = ["xray-list"] as const;
export const useXrayList = () => useQuery({
  queryKey: XLIST, staleTime: 10_000,
  queryFn: async ({ signal }) => { const r = await fetch("/api/trends/xray", { signal }); return r.ok ? (await r.json() as { done: string[]; running: { id: string; jobId: string; progress: number | null; stage: string }[] }) : { done: [], running: [] }; },
  refetchInterval: (q) => ((q.state.data?.running.length ?? 0) > 0 ? 1500 : false),
});
export const useXray = (vid: string | null, enabled = true) => useQuery({
  queryKey: ["xray", vid], enabled: !!vid && enabled, staleTime: Infinity,
  queryFn: async ({ signal }) => { const r = await fetch(`/api/public/trends/xray/${vid}/xray.json?v=${Date.now()}`, { signal }); return r.ok ? (await r.json() as Xray) : null; },
});
export async function startXray(vid: string) {
  const r = await fetch(`/api/trends/xray/${vid}`, { method: "POST", headers: { "x-fluma-client": "trends" } });
  if (!r.ok) { toast.error(tt("분해 분석을 시작하지 못했어요")); return; }
  const { jobId } = await r.json();
  qc.invalidateQueries({ queryKey: XLIST });
  // 끝나면 목록 · 결과를 다시 읽는다
  const es = new EventSource(`/api/jobs/${jobId}/events`);
  es.onmessage = (m) => {
    const ev = JSON.parse(m.data);
    if (ev.type === "done" || ev.type === "failed" || ev.type === "canceled") {
      es.close(); qc.invalidateQueries({ queryKey: XLIST }); qc.invalidateQueries({ queryKey: ["xray", vid] });
      if (ev.type === "done") toast.success(tt("분해 분석이 끝났어요"));
      if (ev.type === "failed") toast.error(tt("분해 분석 실패"), { description: String(ev.detail || ev.error || "").slice(-200) });
    }
  };
  es.addEventListener("end", () => es.close());
}
export async function dropXray(vid: string) {
  await fetch(`/api/trends/xray/${vid}`, { method: "DELETE", headers: { "x-fluma-client": "trends" } });
  qc.invalidateQueries({ queryKey: XLIST }); qc.setQueryData(["xray", vid], null);
}

/* ---------- 개체 추적 누끼 ---------- */
export interface Track { id: string; vid: string; seed: { t: number; x: number; y: number }; from: number; to: number; fps: number; frames: number; w: number; h: number;
  path: [number, number, number, number][]; boxes: [number, number, number, number, number][]; preview: string; cover: string; at: string;
  motion?: { travel: number; scale: number; dx: number; dy: number } }
export const useTracks = (vid: string) => useQuery({
  queryKey: ["xray-tracks", vid], staleTime: 10_000,
  queryFn: async ({ signal }) => { const r = await fetch(`/api/trends/xray/${vid}/tracks`, { signal }); return r.ok ? (await r.json() as { tracks: Track[]; running: { jobId: string; progress: number | null; stage: string }[] }) : { tracks: [], running: [] }; },
  refetchInterval: (q) => ((q.state.data?.running.length ?? 0) > 0 ? 1500 : false),
});
export type Pt = [number, number];
/** 한 프레임 미리보기: 찍은 점(포함 · 빼기)으로 잘린 모양 → 투명 PNG 주소 (약 2~4초) */
export async function segmentPreview(vid: string, t: number, pos: Pt[], neg: Pt[]): Promise<{ url?: string; error?: string }> {
  const [x, y] = pos[0];
  const r = await fetch(`/api/trends/xray/${vid}/segment`, { method: "POST", headers: { "content-type": "application/json", "x-fluma-client": "trends" }, body: JSON.stringify({ t, x, y, pos: pos.slice(1), neg }) });
  const j = await r.json().catch(() => ({}));
  return r.ok ? { url: j.url } : { error: j?.error?.message || j?.message || tt("개체를 찾지 못했어요") };
}
export async function startTrack(vid: string, t: number, x: number, y: number, pos: Pt[] = [], neg: Pt[] = []) {
  const r = await fetch(`/api/trends/xray/${vid}/track`, { method: "POST", headers: { "content-type": "application/json", "x-fluma-client": "trends" }, body: JSON.stringify({ t, x, y, pos, neg }) });
  if (!r.ok) { toast.error(tt("개체 추적을 시작하지 못했어요")); return; }
  const { jobId } = await r.json();
  qc.invalidateQueries({ queryKey: ["xray-tracks", vid] });
  const es = new EventSource(`/api/jobs/${jobId}/events`);
  es.onmessage = (m) => {
    const ev = JSON.parse(m.data);
    if (ev.type === "done" || ev.type === "failed" || ev.type === "canceled") {
      es.close(); qc.invalidateQueries({ queryKey: ["xray-tracks", vid] });
      if (ev.type === "done") toast.success(tt("개체를 끝까지 따라갔어요"));
      if (ev.type === "failed") toast.error(tt("개체를 따라가지 못했어요"), { description: String(ev.detail || ev.error || "").split("\n").pop()?.slice(0, 200) });
    }
  };
  es.addEventListener("end", () => es.close());
}
export async function dropTrack(vid: string, tid: string) {
  await fetch(`/api/trends/xray/${vid}/track/${tid}`, { method: "DELETE", headers: { "x-fluma-client": "trends" } });
  qc.invalidateQueries({ queryKey: ["xray-tracks", vid] });
}
