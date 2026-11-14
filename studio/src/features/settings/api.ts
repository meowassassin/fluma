/* 설정 화면 전용 요청 — 오류는 서버 봉투({error:{code,message}})를 읽어 ApiError 로 */
import { ApiError, CLIENT_ID } from "../../lib/api";
import { t } from "../../lib/i18n";

async function call<T>(method: string, url: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const headers: Record<string, string> = { "x-fluma-client": CLIENT_ID };
  if (body !== undefined) headers["content-type"] = "application/json";
  let r: Response;
  try { r = await fetch(url, { method, headers, body: body === undefined ? undefined : JSON.stringify(body), signal }); }
  catch (e) { if ((e as Error)?.name === "AbortError") throw e; throw new ApiError(0, "network", t("서버에 연결할 수 없습니다")); }
  if (!r.ok) {
    let code = `http_${r.status}`, message = t("요청 실패 ({status})", { status: r.status });
    try { const d = await r.json(); if (d?.error && typeof d.error === "object") { code = d.error.code ?? code; message = d.error.message ?? message; } else if (typeof d?.error === "string") message = d.error; } catch { /* */ }
    throw new ApiError(r.status, code, message);
  }
  return r.json() as Promise<T>;
}

export interface AgentInfo { id: string; title: string; vendor: string; runs: boolean; tagline: string; installed: boolean | null; version: string | null; auth: string | null; path: string | null }
export interface AgentsResp { agents: AgentInfo[]; models: { claude: { id: string; label: string }[]; codex: { id: string; label: string; efforts?: string[] }[]; antigravity?: { id: string; label: string }[] }; active: string | null; problem: string | null }
export interface Voice {
  name: string; title: string; vendor: string; kind: "cloud" | "local" | "api"; runtime: string; status: string;
  license: { code: string; model: string; commercial: string; note: string; url: string };
  korean: boolean; words: boolean; speed: string; quality: string; size: string; voices?: { id: string; title: string; gender: string }[];
  install?: string; summary: string; available: boolean | null; icon: string | null;
}
/** 생성 · 음성 API 키(공급자 하나 = 키 하나) */
export interface GenKey { id: string; ready?: boolean; env: string; title: string; icon?: string | null; what: string; caps: string[]; keyHint: string; console: string; docs?: string; paid?: boolean; testable: boolean; hasKey: boolean; keyMasked: string; source: "env" | "saved" | "agent" | "env.local" | null }
export interface Mem { id: string; type: string; scope: string; title: string; body: string; status: string; created?: string; provenance?: { menu?: string }; stats?: { recallCount?: number } }

export const sapi = {
  agents: (s?: AbortSignal) => call<AgentsResp>("GET", "/api/agents", undefined, s),
  gflowStatus: (s?: AbortSignal) => call<{ available: boolean; msg?: string }>("GET", "/api/gflow/status", undefined, s),
  gflowLogin: () => call<{ ok: boolean; error?: string | null }>("POST", "/api/gflow/login"),
  voices: (s?: AbortSignal) => call<Voice[]>("GET", "/api/voices", undefined, s),
  previewVoice: (name: string, voice: string) => call<{ ok: boolean; url: string }>("POST", `/api/voices/${name}/preview`, { voice }),
  genKeys: (s?: AbortSignal) => call<GenKey[]>("GET", "/api/gen-keys", undefined, s),
  testGenKey: (id: string) => call<{ ok: boolean | null; status?: number; msg: string }>("POST", `/api/gen-keys/${id}/test`, {}),
  saveGenKey: (id: string, key: string) => call<{ ok: boolean; keyMasked: string }>("PUT", `/api/gen-keys/${id}`, { key }),
  memory: (s?: AbortSignal) => call<Mem[]>("GET", "/api/memory", undefined, s),
  forget: (id: string) => call<{ ok: boolean }>("DELETE", `/api/memory/${id}`),
  install: (kind: "engines" | "voices", name: string) => call<{ job: string; jobId: string }>("POST", `/api/install/${kind}/${name}`),
  installStatus: (job: string, s?: AbortSignal) => call<{ status: "run" | "done" | "fail"; lines: string[]; secs: number }>("GET", `/api/install/jobs/${job}`, undefined, s),
  refreshRegistry: () => call<{ ok: boolean }>("POST", "/api/registry/refresh"),
};
