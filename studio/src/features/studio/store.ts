/* 영상 화면 상태 — 고른 장면 · 미리보기에서 짚은 자리(에이전트에게 넘길 맥락) · 미리보기 iframe.
   편집은 채팅으로만 한다(손 편집 도구 없음 — 2026-11-02). 재생 위치는 여기 없다(lib/clock). */
import { create } from "zustand";
import { toast } from "sonner";
import { api, errMsg, uploadFile } from "../../lib/api";
import { qc, qk } from "../../lib/queries";
import type { Storyboard } from "../../lib/types";
import { t } from "../../lib/i18n";

/** 미리보기에서 짚은 자리: 에이전트에게 "여기를 이렇게" 를 말할 때 맥락으로 붙는다 */
export interface Pick { t: number; scene: number; x: number; y: number; label: string }

interface StudioState {
  id: string | null;
  scene: number | null;   // 고른 장면(타임라인 · 검사 목록)
  pick: Pick | null;
  guide: boolean;         // 쇼츠 안전 영역 표시
  set: (p: Partial<StudioState>) => void;
  reset: (id: string) => void;
}
export const useStudio = create<StudioState>((set) => ({
  id: null, scene: null, pick: null, guide: false,
  set: (p) => set(p),
  reset: (id) => set({ id, scene: null, pick: null }),
}));

/* ---------- 미리보기 iframe 접근 ---------- */
type FrameWin = Window & { __sfSeek?: (t: number) => void };
let frameEl: HTMLIFrameElement | null = null;
export const setFrame = (f: HTMLIFrameElement | null) => { frameEl = f; };
export const frameDoc = () => { try { return frameEl?.contentDocument ?? null; } catch { return null; } };
const frameWin = () => { try { return (frameEl?.contentWindow as FrameWin | null) ?? null; } catch { return null; } };
export const seekFrame = (t: number) => { try { frameWin()?.__sfSeek?.(t); } catch { /* 로딩 중 */ } };

const PART_KO: Record<string, string> = { bg: "배경", text: "글자", counter: "숫자 카운터", shape: "도형", pixel: "픽셀 그림", draw: "선 그리기", bars: "막대 그래프", frame: "창", image: "이미지", particles: "입자", ring: "링 게이지", versus: "대결", list: "목록", actor: "캐릭터", stage: "무대 조명", type: "제목", rule: "구분선", label: "라벨", card: "원근 카드", big: "큰 글자", seq: "레이어 요소" };
const words = (e: HTMLElement) => { const out: string[] = []; const w = e.ownerDocument.createTreeWalker(e, 4); let n; while ((n = w.nextNode())) { const v = (n.textContent || "").trim(); if (v) out.push(v); } return out.join(" ").replace(/\s+/g, " "); };
/** 화면 요소의 사람이 읽는 이름(부품 이름 · 짤 이름 · 글자) */
export function describe(e: HTMLElement): string {
  const named = e.closest<HTMLElement>("[data-name]");
  if (named?.dataset.name) return named.dataset.name;
  if (e.dataset.seq) return e.dataset.seq.split("/").pop() || t("레이어 요소");
  const part = e.closest<HTMLElement>("[data-part]")?.dataset.part, txt = words(e);
  if (part && PART_KO[part]) return txt ? `${t(PART_KO[part])} · ${txt.slice(0, 18)}` : t(PART_KO[part]);
  if (txt) return txt.slice(0, 26);
  return e.tagName === "IMG" || e.tagName === "CANVAS" ? t("그림") : "";
}

/* ---------- 콘티 저장(제목 바꾸기 등 작은 것만 — 내용 편집은 에이전트) ---------- */
let sbQueue: Promise<unknown> = Promise.resolve();
export function patchStoryboard(p: Partial<Storyboard>) {
  const { id } = useStudio.getState(); if (!id) return;
  const sb = qc.getQueryData<Storyboard>(qk.storyboard(id)); if (!sb) return;
  const next = { ...sb, ...p } as Storyboard;
  qc.setQueryData(qk.storyboard(id), next);
  sbQueue = sbQueue.then(() => api.saveStoryboard(id, next)
    .then((r) => qc.setQueryData(qk.lint(id), { lint: r.lint }))
    .catch((e) => { toast.error(t("콘티를 저장하지 못했어요"), { description: errMsg(e) }); qc.invalidateQueries({ queryKey: qk.storyboard(id) }); }));
}

/** 끌어다 놓은 사진 · 영상을 이 영상의 에셋으로 올린다(에이전트가 쓸 재료) */
export async function uploadAll(projectId: string, files: File[]) {
  const id = toast.loading(t("올리는 중 {k}/{n}", { k: 0, n: files.length }));
  try {
    for (const [k, f] of files.entries()) { toast.loading(t("올리는 중 {k}/{n} · {name}", { k: k + 1, n: files.length, name: f.name }), { id }); await uploadFile(projectId, f); }
    toast.success(t("{n}개 올렸어요", { n: files.length }), { id, description: t("에이전트에게 \"올린 사진을 장면 3에 넣어 줘\"처럼 말하면 씁니다") });
    qc.invalidateQueries({ queryKey: qk.uploads(projectId) });
  } catch (e) { toast.error(t("올리지 못했어요"), { id, description: errMsg(e) }); }
}

export const startsOf = (sb: Storyboard | undefined | null) => { let a = 0; return (sb?.scenes ?? []).map((s) => { const x = a; a += s.sec; return x; }); };
export const totalOf = (sb: Storyboard | undefined | null) => (sb?.scenes ?? []).reduce((a, s) => a + s.sec, 0);
export const sceneAt = (starts: number[], sb: Storyboard | undefined | null, t: number) => {
  if (!sb?.scenes.length) return 0;
  for (let i = starts.length - 1; i >= 0; i--) if (t >= starts[i] - 1e-6) return i;
  return 0;
};
export const ROLE_KO: Record<string, string> = { hook: "훅", setup: "설정", item: "항목", contrast: "대비", step: "단계", reveal: "공개", verdict: "결론", outro: "맺음", benefit: "이점", proof: "증거", mood: "분위기", price: "가격", cta: "행동" };
/** 장면 역할 → 지금 언어 이름(모르는 역할은 원래 값) */
export const roleName = (role: string | undefined | null) => {
  if (!role) return "";
  const ko = ROLE_KO[role]; if (!ko) return role;
  // 사전 키에 "장면 역할 · " 를 붙여 같은 글자의 다른 뜻(예: 설정 = 메뉴)과 겹치지 않게
  const k = `장면 역할 · ${ko}`, v = t(k);
  return v === k ? ko : v;
};
export const isHard = (l: { code: string; message: string }) => !!l.code && !l.code.startsWith("T") && l.message !== "통과";
