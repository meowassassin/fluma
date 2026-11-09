// 콘티(engine/spec/schema/storyboard.schema.json)와 서버 응답 타입 — 화면 전체가 이것만 쓴다.

export type Format = "concept" | "mythbust" | "compare" | "countdown" | "fix" | "series" | "ad" | "emotional" | "daily";
export interface Visual {
  kind: string; primary?: string; secondary?: string; items?: string[]; before?: string; after?: string;
  asset?: string; emphasis?: "good" | "bad" | "neutral"; motion?: string; clip_start?: number;
}
export interface Scene {
  role: string; sec: number; caption: string; narration: string; visual: Visual;
  sfx?: string; music_cue?: string; engine?: string; template?: string;
  beat?: string; screen?: string; elements?: unknown[];
}
export interface Storyboard {
  id: string; version: number; title: string; topic?: string; format: Format | string;
  audience?: string | null; brand?: string | null; badge?: string | null; character?: string | null;
  engine?: string | null; template?: string | null; duration_sec: number;
  hook_number?: string | null; scenes: Scene[]; cta: string; caption?: string; hashtags?: string[]; sources?: string[];
  constraints?: string[]; reference?: string[]; voice?: { engine?: string; id?: string | null } | null;
  direction?: Record<string, string>;
  /** 의도 카드 — 사용자가 원하는 것(이 영상의 규칙). 확인 전엔 최종 렌더 · 유료 생성이 막힌다(engine/checks/gate.py) */
  intent?: { summary?: string; reference_use?: string; must?: string[]; must_not?: string[]; locked?: string[]; confirmed?: boolean };
}

export interface ProjectSummary {
  id: string; title: string; format: string; audience?: string | null; brand: string | null;
  duration_sec: number; template: boolean | string; updated: string; draft?: boolean;
  cast?: { e: string; sec: number }[]; renders?: { final: number; draft: number }; composed?: boolean; reference?: string[];
}
export interface LintItem { code: string; scene: number | null; message: string }

export interface TemplateMeta { name: string; engine: string; mood?: string; formats?: string[]; captions?: "self" | "finish"; primary?: boolean }
export interface EngineMeta {
  name: string; title?: string; license?: string; kind?: string; preview?: "html" | "draft"; summary?: string; install?: string;
  available: boolean | null; templates: TemplateMeta[]; icon?: string | null;
}
export interface SkillMeta { name: string; description: string; when?: string }
export interface CharMeta { name: string; title: string; base: string; [k: string]: unknown }

export interface Settings {
  model: string; effort: string; language: string; voice_engine: string; voice_id: string; voice_auto?: boolean; music_any_license?: boolean;
  agent?: Record<string, unknown>;
}

// ---------- 에이전트 ----------
export interface ChatContext { menu?: "trends" | "character" | "studio" | "plan"; selection?: string; note?: string }
export interface MemoryRef { id: string; title: string; scope: string; type: string }
export interface ChatTool { name: string; input: string; error?: boolean }
export interface Todo { content: string; status: "pending" | "in_progress" | "completed"; activeForm?: string }
export interface ChatFile { path: string; kind: "added" | "modified" | "deleted" }
export interface ChatMessage {
  role: "user" | "assistant"; text: string; ts: number;
  tools?: ChatTool[]; files?: ChatFile[]; ok?: boolean; cost?: number | null; error?: string | null; stopped?: boolean;
  skill?: string | null; scene?: number | null; steer?: boolean; todos?: Todo[] | null; durationMs?: number;
}
export interface ChatHistory { sessionId: string | null; messages: ChatMessage[]; running: boolean; queued?: string[] }
export type AgentEvent =
  | { type: "start"; user: string; skill: string | null; scene: number | null; memories?: MemoryRef[]; at?: number }
  | { type: "status"; label: string }
  | { type: "text"; text: string }
  | { type: "thinking"; text: string }
  | { type: "tool_start"; id: string; name: string }
  | { type: "tool_use"; id: string; name: string; input: string }
  | { type: "tool_result"; id: string; error: boolean; preview: string }
  | { type: "denied" }
  | { type: "steer"; text: string } | { type: "queued"; text: string } | { type: "unqueued"; index: number }
  | { type: "todos"; todos: Todo[] }
  | { type: "result"; ok: boolean; cost: number | null; durationMs: number | null; denials: string[] }
  | { type: "end"; ok: boolean; files: ChatFile[]; stopped: boolean; error: string | null; durationMs?: number; cost?: number | null };

// ---------- 작업(렌더 등) ----------
export type JobStatus = "queued" | "running" | "done" | "failed" | "canceled";
export interface Job {
  id: string; type: string; project: string | null; status: JobStatus; progress: number | null; stage?: string;
  started?: number | string | null; ended?: number | string | null; result?: { url?: string } | null; error?: string | null;
}
export type JobEvent =
  | { type: "log"; line: string }
  | { type: "progress"; progress: number | null; stage: string }
  | { type: "done"; url?: string }
  | { type: "failed"; error?: string }
  | { type: "canceled" };

// ---------- 파일 감시 ----------
export interface FsEvent {
  kind: "storyboard" | "composition" | "overrides" | "audio" | "elements" | "uploads" | "renders" | "engines" | "skills"
    | "trends" | "characters" | "memory" | "settings" | "job" | "registry" | string;
  id?: string; lint?: LintItem[]; client?: string; path?: string;
}
