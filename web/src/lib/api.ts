/* API 클라이언트 — 모든 요청이 여기를 지난다.
   · 실패는 언제나 ApiError(사람이 읽을 한국어 message) 로 던진다 — 화면은 조용히 삼키지 않고 토스트로 알린다.
   · 쓰기 요청에는 x-fluma-client 를 붙인다 → 서버가 파일 감시 이벤트에 같은 값을 실어 보내므로, 내가 쓴 것의 메아리를 무시할 수 있다. */
import type {
  CharMeta, ChatContext, ChatFile, ChatHistory, EngineMeta, Job, LintItem, ProjectSummary, Settings, SkillMeta, Storyboard,
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
/** 렌더 결과 파일 하나(out/<id>…mp4) */
export interface RenderFile { name: string; bytes: number; mtime: number; draft: boolean; variant: boolean; aspect: "9:16" | "16:9" | "1:1"; size: string | null; scenes: string | null; url: string; download: string }

/** 제작 관문(scripts/gate.py): 의도 카드 확인 · 시안(장면 1~3) 승인 */
export interface GateStatus { intent: boolean; draft: boolean; why: string[] }

export const api = {
  // 프로젝트 · 콘티
  projects: (s?: AbortSignal) => get<ProjectSummary[]>("/api/storyboards", s),
  storyboard: (id: string, s?: AbortSignal) => get<Storyboard>(`/api/storyboards/${id}`, s),
  saveStoryboard: (id: string, sb: Storyboard) => req<{ ok: boolean; lint: LintItem[] }>("PUT", `/api/storyboards/${id}`, sb),
  lint: (id: string, s?: AbortSignal) => get<{ lint: LintItem[] }>(`/api/storyboards/${id}/lint`, s),
  overrides: (id: string, s?: AbortSignal) => get<Record<string, unknown>>(`/api/compositions/${id}/overrides`, s),
  saveOverrides: (id: string, o: Record<string, unknown>) => req<{ ok: boolean }>("PUT", `/api/compositions/${id}/overrides`, o),
  deleteProject: (id: string) => req<{ ok: boolean; trash: string }>("DELETE", `/api/projects/${id}`),
  trash: () => get<{ name: string; id: string; title: string; deletedAt: string; files: string[] }[]>("/api/trash"),
  restore: (name: string) => req<{ ok: boolean }>("POST", `/api/trash/${encodeURIComponent(name)}/restore`),
  purge: (name: string) => req<{ ok: boolean }>("DELETE", `/api/trash/${encodeURIComponent(name)}`),

  // 미리보기 · 렌더
  build: (id: string, engine?: string | null, template?: string | null, s?: AbortSignal) =>
    req<{ ok: boolean; url: string; engine: string; template: string }>("POST", `/api/projects/${id}/build`, { engine, template }, s),
  still: (id: string, seconds: number[], engine?: string | null, template?: string | null, s?: AbortSignal) =>
    req<{ stills: { seconds: number; url: string }[] }>("POST", `/api/projects/${id}/still`, { seconds, engine, template }, s),
  render: (id: string, opts: RenderOpts = {}) => req<{ jobId: string }>("POST", "/api/render", { id, ...opts }),
  gate: (id: string, s?: AbortSignal) => get<GateStatus>(`/api/projects/${id}/gate`, s),
  /** 이 영상의 렌더 결과(최신순) — 편집기 '내려받기' */
  renders: (id: string, s?: AbortSignal) => get<RenderFile[]>(`/api/projects/${id}/renders`, s),
  gateConfirm: (id: string, kind: "intent" | "draft") => req<{ ok: boolean }>("POST", `/api/projects/${id}/gate/${kind}`, {}),
  jobs: (project?: string) => get<Job[]>(`/api/jobs${project ? `?project=${encodeURIComponent(project)}` : ""}`),
  cancelJob: (jobId: string) => req<{ ok: boolean }>("DELETE", `/api/jobs/${jobId}`),
  voice: (id: string) => req<{ ok: boolean; lint?: LintItem[] }>("POST", `/api/projects/${id}/voice`),

  // 카탈로그
  engines: (s?: AbortSignal) => get<EngineMeta[]>("/api/engines", s),
  skills: (s?: AbortSignal) => get<SkillMeta[]>("/api/skills", s),
  characters: (s?: AbortSignal) => get<CharMeta[]>("/api/characters", s),
  staticFiles: (s?: AbortSignal) => get<string[]>("/api/static-files", s),
  settings: (s?: AbortSignal) => get<{ settings: Settings }>("/api/settings", s),
  saveSettings: (st: Settings) => req<{ ok: boolean }>("PUT", "/api/settings", st),
  elements: (id: string, s?: AbortSignal) => get<{ name: string; rel: string; poster: string; frames: number; fps: number; engine?: string; kind?: string; role?: string; model?: string; commercial?: string }[]>(`/api/projects/${id}/elements`, s),
  uploads: (id: string, s?: AbortSignal) => get<{ name: string; kind: "image" | "video"; url: string; rel: string; seq?: string; poster?: string | null; duration?: number; width?: number; height?: number; size: number }[]>(`/api/projects/${id}/uploads`, s),
  deleteUpload: (id: string, name: string) => req<{ files: unknown[] }>("DELETE", `/api/projects/${id}/uploads/${encodeURIComponent(name)}`),

  // 에이전트
  chat: (id: string, s?: AbortSignal) => get<ChatHistory>(`/api/projects/${id}/chat`, s),
  send: (id: string, body: { message: string; skill?: string | null; scene?: number | null; steer?: boolean; interrupt?: boolean; context?: ChatContext }) =>
    req<{ ok: boolean; mode: "start" | "steer" | "queued" | "interrupt" }>("POST", `/api/projects/${id}/chat`, body),
  unqueue: (id: string, index: number) => req<{ ok: boolean }>("DELETE", `/api/projects/${id}/chat/queued/${index}`),
  stop: (id: string) => req<{ ok: boolean }>("POST", `/api/projects/${id}/chat/stop`),
  resetChat: (id: string) => req<{ ok: boolean }>("DELETE", `/api/projects/${id}/chat`),
  revert: (id: string, paths?: string[]) => req<{ ok: boolean; files: ChatFile[]; conflicts?: string[] }>("POST", `/api/projects/${id}/revert`, { paths }),
};

/** 업로드: 파일 본문을 그대로 보낸다(서버가 디스크로 흘려 씀) */
export async function uploadFile(projectId: string, f: File) {
  const r = await fetch(`/api/projects/${projectId}/uploads?name=${encodeURIComponent(f.name)}`, {
    method: "POST", headers: { "content-type": "application/octet-stream", "x-fluma-client": CLIENT_ID }, body: f,
  }).catch(() => { throw new ApiError(0, "network", t("서버에 연결할 수 없습니다")); });
  return parse<{ files: unknown[] }>(r);
}

/** 화면에 보일 오류 글 — 서버가 보낸 한국어 문장도 사전에 있으면 지금 언어로 */
export const errMsg = (e: unknown) => t(e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e));
