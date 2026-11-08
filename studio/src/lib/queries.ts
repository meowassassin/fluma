/* 서버 데이터 = React Query 캐시 하나. 파일 감시 이벤트(/api/events)는 해당 키만 무효화한다
   (예전처럼 전역 tick 을 올려 앱 전체를 다시 그리지 않는다). 내가 쓴 파일의 메아리(client === CLIENT_ID)는 무시. */
import { QueryClient, useQuery } from "@tanstack/react-query";
import { useEffect, useSyncExternalStore } from "react";
import { api, CLIENT_ID } from "./api";
import type { FsEvent, LintItem } from "./types";

export const qc = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, gcTime: 5 * 60_000, retry: 1, refetchOnWindowFocus: false },
    mutations: { retry: 0 },
  },
});

export const qk = {
  agentActive: ["agent-active"] as const,
  projects: ["projects"] as const,
  storyboard: (id: string) => ["storyboard", id] as const,
  lint: (id: string) => ["lint", id] as const,
  overrides: (id: string) => ["overrides", id] as const,
  audio: (id: string) => ["audio", id] as const,
  elements: (id: string) => ["elements", id] as const,
  uploads: (id: string) => ["uploads", id] as const,
  jobs: (id: string) => ["jobs", id] as const,
  engines: ["engines"] as const, skills: ["skills"] as const,
  characters: ["characters"] as const, settings: ["settings"] as const,
  trends: ["trends"] as const, memory: ["memory"] as const, voices: ["voices"] as const, agents: ["agents"] as const,
};

/* ---------- 연결 상태 (서버가 죽었는지 화면에 보이게) ---------- */
type Conn = "connecting" | "open" | "down";
let conn: Conn = "connecting";
const connSubs = new Set<() => void>();
const setConn = (c: Conn) => { if (c !== conn) { conn = c; connSubs.forEach((f) => f()); } };
export const useConnection = () => useSyncExternalStore((f) => { connSubs.add(f); return () => connSubs.delete(f); }, () => conn);

/* ---------- 파일 감시 → 캐시 무효화 ---------- */
const fsSubs = new Set<(e: FsEvent) => void>();
export const onFsEvent = (f: (e: FsEvent) => void) => { fsSubs.add(f); return () => { fsSubs.delete(f); }; };

let started = false;
export function startEvents() {
  if (started) return; started = true;
  let es: EventSource | null = null;
  let wasDown = false;
  const open = () => {
    es = new EventSource("/api/events");
    es.onopen = () => { setConn("open"); if (wasDown) { wasDown = false; qc.invalidateQueries(); } };
    es.onerror = () => { setConn("down"); wasDown = true; /* EventSource 가 스스로 다시 붙는다 */ };
    es.onmessage = (m) => {
      let ev: FsEvent; try { ev = JSON.parse(m.data); } catch { return; }
      const mine = ev.client === CLIENT_ID;
      const id = ev.id;
      // 검사 결과는 콘티 · 화면 구성 · 음성 · 요소 어느 쪽이 바뀌어도 서버가 다시 계산해 함께 보낸다
      if (id && ev.lint) qc.setQueryData<{ lint: LintItem[] }>(qk.lint(id), { lint: ev.lint });
      switch (ev.kind) {
        case "storyboard":
          if (!mine) { if (id) qc.invalidateQueries({ queryKey: qk.storyboard(id) }); }
          qc.invalidateQueries({ queryKey: qk.projects });
          break;
        case "composition": if (id) qc.invalidateQueries({ queryKey: ["composition", id] }); break;
        case "overrides": if (id && !mine) qc.invalidateQueries({ queryKey: qk.overrides(id) }); break;
        case "graph": if (id && !mine) qc.invalidateQueries({ queryKey: ["graph", id] }); break;
        case "audio": if (id) { qc.invalidateQueries({ queryKey: qk.audio(id) }); qc.invalidateQueries({ queryKey: ["peaks", id] }); } break;
        case "elements": if (id) qc.invalidateQueries({ queryKey: qk.elements(id) }); break;
        case "uploads": if (id) qc.invalidateQueries({ queryKey: qk.uploads(id) }); break;
        case "renders": qc.invalidateQueries({ queryKey: qk.projects }); if (id) qc.invalidateQueries({ queryKey: qk.jobs(id) }); break;
        case "engines": qc.invalidateQueries({ queryKey: qk.engines }); break;
        case "skills": qc.invalidateQueries({ queryKey: qk.skills }); break;
        case "characters": qc.invalidateQueries({ queryKey: qk.characters }); break;
        case "trends": qc.invalidateQueries({ queryKey: qk.trends }); break;
        case "memory": qc.invalidateQueries({ queryKey: qk.memory }); break;
        case "settings": if (!mine) qc.invalidateQueries({ queryKey: qk.settings }); break;
        case "agent": qc.invalidateQueries({ queryKey: qk.agentActive }); qc.invalidateQueries({ queryKey: ["chats"] }); break;
        case "registry": { const n = (ev as { name?: string }).name; if (n) qc.invalidateQueries({ queryKey: [n] }); break; }
        case "job": { qc.invalidateQueries({ queryKey: ["renders-running"] }); qc.invalidateQueries({ queryKey: ["bgjobs"] }); const j = (ev as { job?: { project?: string } }).job; if (j?.project) qc.invalidateQueries({ queryKey: qk.jobs(j.project) }); break; }
      }
      fsSubs.forEach((f) => f(ev));
    };
  };
  open();
  window.addEventListener("beforeunload", () => es?.close());
}

/* ---------- 훅 ---------- */
export const useProjects = () => useQuery({ queryKey: qk.projects, queryFn: ({ signal }) => api.projects(signal), staleTime: 10_000 });
export const useStoryboard = (id: string | null) => useQuery({
  queryKey: qk.storyboard(id ?? "_"), enabled: !!id, staleTime: Infinity,
  queryFn: ({ signal }) => api.storyboard(id!, signal),
  retry: (n, e) => (e as { status?: number })?.status !== 404 && n < 1,
});
export const useLint = (id: string | null, enabled = true) => useQuery({
  queryKey: qk.lint(id ?? "_"), enabled: !!id && enabled, staleTime: Infinity, queryFn: ({ signal }) => api.lint(id!, signal),
});
export const useOverrides = (id: string | null) => useQuery({
  queryKey: qk.overrides(id ?? "_"), enabled: !!id, staleTime: Infinity,
  queryFn: async ({ signal }) => (await api.overrides(id!, signal).catch(() => ({}))) as Record<string, Ovr>,
});
export const useHasAudio = (id: string | null) => useQuery({
  queryKey: qk.audio(id ?? "_"), enabled: !!id, staleTime: Infinity,
  queryFn: async ({ signal }) => { const r = await fetch(`/api/public/audio/${id}.wav`, { method: "HEAD", signal }); return r.ok ? r.headers.get("last-modified") ?? "1" : null; },
});
export const useEngines = () => useQuery({ queryKey: qk.engines, queryFn: ({ signal }) => api.engines(signal), staleTime: 5 * 60_000 });
export const useSkills = () => useQuery({ queryKey: qk.skills, queryFn: ({ signal }) => api.skills(signal), staleTime: 5 * 60_000 });
export const useCharacters = () => useQuery({ queryKey: qk.characters, queryFn: ({ signal }) => api.characters(signal), staleTime: 5 * 60_000 });
export const useSettings = () => useQuery({ queryKey: qk.settings, queryFn: async ({ signal }) => (await api.settings(signal)).settings });
export const useElements = (id: string | null) => useQuery({ queryKey: qk.elements(id ?? "_"), enabled: !!id, queryFn: ({ signal }) => api.elements(id!, signal) });
export const useUploads = (id: string | null) => useQuery({ queryKey: qk.uploads(id ?? "_"), enabled: !!id, queryFn: ({ signal }) => api.uploads(id!, signal) });

/** 손 수정 값 (compositions/<id>/overrides.json) — 렌더에 그대로 들어간다 */
export type Kf = { t: number; dx?: number; dy?: number; scale?: number; rot?: number; opacity?: number };
export type Ovr = { dx?: number; dy?: number; scale?: number; rot?: number; opacity?: number; color?: string; fill?: string; text?: string; hidden?: boolean; kf?: Kf[] };

/** 마운트 동안 이벤트 연결을 보장 */
export const useEventsBoot = () => useEffect(() => { startEvents(); }, []);

/** 지금 일하는 에이전트 대화들(서버 기준). 시작 · 끝은 이벤트로 바로, 진행 중 도구 이름은 4초마다 */
export interface ActiveAgent { id: string; user: string; startedAt: number; tool: { name: string; input: string } | null; stopping: boolean; skill: string | null }
export const useActiveAgents = () => useQuery({
  queryKey: qk.agentActive, staleTime: Infinity,
  queryFn: async ({ signal }) => { const r = await fetch("/api/agent/active", { signal }); return r.ok ? (await r.json() as ActiveAgent[]) : []; },
  refetchInterval: (q) => ((q.state.data?.length ?? 0) > 0 ? 4000 : false),
});

/** 홈 대화 목록 (영상마다의 대화 · 기획 중인 것 포함) */
export interface ChatSummary { id: string; title: string; updated: number; count: number; storyboard: boolean; audio: boolean; composed: boolean; running: boolean }
export const useChats = () => useQuery({ queryKey: ["chats"], staleTime: 15_000, queryFn: async ({ signal }) => { const r = await fetch("/api/chats", { signal }); return r.ok ? (await r.json() as ChatSummary[]) : []; } });
/** 지금 돌아가는 렌더 (영상 아이콘 알림 숫자용) */
export const useRunningRenders = () => useQuery({
  queryKey: ["renders-running"], staleTime: Infinity,
  queryFn: async ({ signal }) => {
    const r = await fetch("/api/jobs", { signal }); const js = r.ok ? (await r.json() as { type: string; project: string | null; status: string }[]) : [];
    // 렌더 · 3D 렌더(백그라운드)
    return js.filter((j) => (j.type === "render" || j.type === "element") && (j.status === "running" || j.status === "queued")).map((j) => j.project).filter(Boolean) as string[];
  },
});
/** 제작 중인 영상 수 = 기획(plan)이 아닌 일을 하는 영상 에이전트 + 렌더 중 */
export const useProducing = () => {
  const { data: active = [] } = useActiveAgents();
  const { data: renders = [] } = useRunningRenders();
  return [...new Set([...active.filter((a) => !a.id.startsWith("_") && a.skill !== "plan").map((a) => a.id), ...renders])];
};

/** 영상의 백그라운드 작업(3D 렌더 등) — 진행률을 따로 보여 준다 */
export interface BgJob { id: string; type: string; label: string; status: string; progress: number | null; stage: string; error?: string }
export const useBgJobs = (project: string) => useQuery({
  queryKey: ["bgjobs", project], staleTime: Infinity,
  queryFn: async ({ signal }) => { const r = await fetch(`/api/jobs?project=${encodeURIComponent(project)}&type=element`, { signal }); return r.ok ? (await r.json() as BgJob[]) : []; },
  refetchInterval: (q) => ((q.state.data ?? []).some((j) => j.status === "running" || j.status === "queued") ? 1500 : false),
});
