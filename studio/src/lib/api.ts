/* API 클라이언트 — 모든 요청이 여기를 지난다.
   · 실패는 언제나 ApiError(사람이 읽을 한국어 message) 로 던진다 — 화면은 조용히 삼키지 않고 토스트로 알린다.
   · 쓰기 요청에는 x-fluma-client 를 붙인다 → 서버가 파일 감시 이벤트에 같은 값을 실어 보내므로, 내가 쓴 것의 메아리를 무시할 수 있다. */
import type {
  ChatContext, ChatFile, ChatHistory, EngineMeta, Job, LintItem, ProjectSummary, Settings, SkillMeta, Storyboard,
} from "./types";
import { t } from "./i18n";

export const CLIENT_ID = (() => { try { return crypto.randomUUID().slice(0, 8); } catch { return Math.random().toString(36).slice(2, 10); } })();

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) { super(message); }
}

async function parse<T>(r: Response): Promise<T> {
  if (r.ok) return (r.status === 204 ? undefined : r.json()) as Promise<T>;
  let code = `http_${r.status}`, message = t("요청 실패 ({status})", { status: r.status });
  try {
    const d = await r.json();
    if (d?.error && typeof d.error === "object") { code = d.error.code ?? code; message = d.error.message ?? message; }
    else if (typeof d?.error === "string") message = d.error;
  } catch { /* 본문 없음 */ }
  if (r.status === 502 || r.status === 503 || r.status === 504) message = t("서버에 연결할 수 없습니다 — 잠시 뒤 다시 시도하세요");
  throw new ApiError(r.status, code, message);
}

function req<T>(method: string, url: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const headers: Record<string, string> = { "x-fluma-client": CLIENT_ID };
  if (body !== undefined) headers["content-type"] = "application/json";
  return fetch(url, { method, headers, body: body === undefined ? undefined : JSON.stringify(body), signal })
    .catch((e) => { if (e?.name === "AbortError") throw e; throw new ApiError(0, "network", t("서버에 연결할 수 없습니다 — 개발 서버가 켜져 있는지 확인하세요")); })
    .then((r) => parse<T>(r));
}
const get = <T,>(url: string, signal?: AbortSignal) => req<T>("GET", url, undefined, signal);

/** 렌더 출력: 세로 해상도(9:16) · 화질 · 초당 프레임 */
export interface RenderOpts { size?: "720" | "1080" | "1440" | "2160"; quality?: "standard" | "high" | "max"; fps?: 30 | 60; draft13?: boolean }

export const api = {
  // 프로젝트 · 콘티
  projects: (s?: AbortSignal) => get<ProjectSummary[]>("/api/storyboards", s),
  storyboard: (id: string, s?: AbortSignal) => get<Storyboard>(`/api/storyboards/${id}`, s),
  saveStoryboard: (id: string, sb: Storyboard) => req<{ ok: boolean; lint: LintItem[] }>("PUT", `/api/storyboards/${id}`, sb),
  deleteProject: (id: string) => req<{ ok: boolean; trash: string }>("DELETE", `/api/projects/${id}`),
  trash: () => get<{ name: string; id: string; title: string; deletedAt: string; files: string[] }[]>("/api/trash"),
  restore: (name: string) => req<{ ok: boolean }>("POST", `/api/trash/${encodeURIComponent(name)}/restore`),
  purge: (name: string) => req<{ ok: boolean }>("DELETE", `/api/trash/${encodeURIComponent(name)}`),

  // 작업
  jobs: (project?: string) => get<Job[]>(`/api/jobs${project ? `?project=${encodeURIComponent(project)}` : ""}`),
  cancelJob: (jobId: string) => req<{ ok: boolean }>("DELETE", `/api/jobs/${jobId}`),

  // 카탈로그
  engines: (s?: AbortSignal) => get<EngineMeta[]>("/api/engines", s),
  skills: (s?: AbortSignal) => get<SkillMeta[]>("/api/skills", s),
  settings: (s?: AbortSignal) => get<{ settings: Settings }>("/api/settings", s),
  saveSettings: (st: Settings) => req<{ ok: boolean }>("PUT", "/api/settings", st),

  // 에이전트
  chat: (id: string, s?: AbortSignal) => get<ChatHistory>(`/api/projects/${id}/chat`, s),
  send: (id: string, body: { message: string; skill?: string | null; scene?: number | null; steer?: boolean; interrupt?: boolean; context?: ChatContext }) =>
    req<{ ok: boolean; mode: "start" | "steer" | "queued" | "interrupt" }>("POST", `/api/projects/${id}/chat`, body),
  unqueue: (id: string, index: number) => req<{ ok: boolean }>("DELETE", `/api/projects/${id}/chat/queued/${index}`),
  stop: (id: string) => req<{ ok: boolean }>("POST", `/api/projects/${id}/chat/stop`),
  resetChat: (id: string) => req<{ ok: boolean }>("DELETE", `/api/projects/${id}/chat`),
  revert: (id: string, paths?: string[]) => req<{ ok: boolean; files: ChatFile[]; conflicts?: string[] }>("POST", `/api/projects/${id}/revert`, { paths }),
  // 영상 편집기(VEditor — engine/gen/editor_bridge.py)
  editorGet: (id: string, s?: AbortSignal) => get<unknown>(`/api/projects/${id}/editor`, s),
  editorSave: (id: string, doc: unknown) => req<{ ok: boolean; file: string }>("PUT", `/api/projects/${id}/editor`, doc),
  // 제작 파이프라인 상태(engine/gen/status.py) — 초안 · 최종 렌더
  pipelines: (s?: AbortSignal) => get<{ id: string; topic: string; shots: number; updated: number; thumb?: string | null; style?: string; route?: string }[]>("/api/pipeline", s),
  pipeline: (id: string, s?: AbortSignal) => get<Pipeline>(`/api/pipeline/${id}`, s),
  pipelineLive: (id: string, s?: AbortSignal) => get<PipelineLive>(`/api/pipeline/${id}/live`, s),
  pipelineAct: (id: string, step: string, action: string, body: Record<string, unknown> = {}) =>
    req<{ ok?: boolean; job?: string }>("POST", `/api/pipeline/${id}/${step}/${action}`, body),
};

export interface PipeShot { n: number; purpose: string; beat?: string; final_sec: number; shot_size?: string; camera_move?: string }
/** 파이프라인 뷰 실시간 상태(/api/pipeline/:id/live) */
export interface PipelineLive {
  at: number;
  jobs: { id: string; type: string; label?: string; status: string; progress: number | null; stage?: string; started?: number | null; ended?: number | null; error?: string | null }[];
  agent: { busy: boolean; waiting?: number | null; tool: string | null; skill: string | null; runtime: "claude" | "codex" | "antigravity" | "cursor" | null; model: string | null; label: string | null };
  models: { voice: string };
  editor: { project: number; exported: number };
  /** produce.py 진행 기록 — 프로세스가 살아 있을 때만 running · stage */
  produce?: { running: boolean; stage: string | null; stageStarted: number | null; done: Record<string, number>; error: string | null; updated: number } | null;
}
export interface Pipeline {
  id: string; next: string; route?: "clip" | "material";
  plan: { topic: string; logline?: string; aspect?: string; style: string; route_why?: string; route_by?: "user" | "default"; handoff?: string; narration?: string; shots?: PipeShot[] };
  check: { errors: string[]; warnings: string[] };
  edit: { storyboard: boolean; draft: string | null; final: string | null };
  /** 단계마다 실제로 만든 기록(status.py provenance) — 지금 설정과 무관 */
  provenance?: {
    plan?: { runtime: string | null; model: string | null; at?: string };
    voice?: { engine: string | null; voice?: string | null; at?: string };
    draft?: string[];
    materials?: string[];
  };
  /** 아직 안 한 단계에 쓸 도구(이 영상 콘티의 재료에서) — 실제 자료 경로 */
  planned?: { materials?: string[]; draft?: string[] };
  /** 결과 파일이 실제로 있나 — 실제 자료 경로 */
  artifacts?: { research: boolean; audio: boolean; materials: [number, number] };
}

/** 업로드: 파일 본문을 그대로 보낸다(서버가 디스크로 흘려 씀) */
export async function uploadFile(projectId: string, f: File, opts: { frames?: boolean } = {}) {
  const r = await fetch(`/api/projects/${projectId}/uploads?name=${encodeURIComponent(f.name)}${opts.frames === false ? "&frames=0" : ""}`, {
    method: "POST", headers: { "content-type": "application/octet-stream", "x-fluma-client": CLIENT_ID }, body: f,
  }).catch(() => { throw new ApiError(0, "network", t("서버에 연결할 수 없습니다")); });
  return parse<{ files: unknown[] }>(r);
}

/** 편집기 내보내기 영상 업로드: 최종본 data/compositions/<id>/editor/exported.mp4 및 data/out/<id>-editor.mp4 */
export async function uploadExportedVideo(projectId: string, blob: Blob) {
  const r = await fetch(`/api/projects/${projectId}/editor/export`, {
    method: "POST", headers: { "content-type": "video/mp4", "x-fluma-client": CLIENT_ID }, body: blob,
  }).catch(() => { throw new ApiError(0, "network", t("서버에 연결할 수 없습니다")); });
  return parse<{ ok: boolean; file: string; out: string }>(r);
}

/** 화면에 보일 오류 글 — 서버가 보낸 한국어 문장도 사전에 있으면 지금 언어로 */
export const errMsg = (e: unknown) => t(e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e));
