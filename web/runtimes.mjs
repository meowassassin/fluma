// 에이전트 실행 환경 (open-design 의 '로컬 CLI / API 키(BYOK)' 구성을 따름)
//
// - 로컬 CLI: 이 컴퓨터에 설치된 에이전트 CLI 를 그대로 쓴다 (Claude Code · Codex 를 Fluma 가 직접 구동).
// - API 키(BYOK): 사용자가 키를 넣은 제공자로 같은 에이전트를 돌린다.
//     · Anthropic 호환 엔드포인트(Anthropic · OpenRouter · DeepSeek · MiniMax · Kimi · GLM · Ollama) → Claude Code 에
//       ANTHROPIC_BASE_URL / 토큰을 넣어 실행 → 파일 접근 제한(.env 등)이 그대로 지켜진다.
//     · OpenAI Responses 호환(OpenAI · xAI · Azure) → Codex CLI 에 model_providers 설정을 넣어 실행.
//       (Codex 0.159 는 wire_api="chat" 을 더는 지원하지 않는다 — Chat 전용 API 는 OpenRouter 를 거친다)
// 키는 workspace 가 아니라 ~/.shortsforge/byok.json(0600) 에 둔다 — 에이전트는 이 폴더를 읽을 수 없다(DENY).
import { execFile } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync, chmodSync, renameSync } from "node:fs";
import os from "node:os";
import { OS, which } from "./platform.mjs";
import path from "node:path";

export const KEY_FILE = path.join(os.homedir(), ".shortsforge", "byok.json");

/** 로컬 CLI 에이전트. runs = Fluma 가 직접 구동할 수 있는지 */
export const AGENTS = [
  { id: "claude", title: "Claude Code", vendor: "Anthropic", bin: "claude", runs: true, tagline: "파일 접근 제한 · 스킬 · 기억 연동이 가장 잘 됨 (기본)" },
  { id: "codex", title: "Codex", vendor: "OpenAI", bin: "codex", runs: true, tagline: "ChatGPT 계정 또는 OpenAI 키로 GPT 모델 사용" },
  { id: "opencode", title: "OpenCode", vendor: "SST", bin: "opencode", runs: false, tagline: "75개 이상 제공자 — 연결 준비 중" },
  { id: "gemini", title: "Gemini CLI", vendor: "Google", bin: "gemini", runs: false, tagline: "Gemini 모델 — 연결 준비 중" },
  { id: "qwen", title: "Qwen Code", vendor: "Alibaba", bin: "qwen", runs: false, tagline: "Qwen 모델 — 연결 준비 중" },
  { id: "cursor-agent", title: "Cursor Agent", vendor: "Cursor", bin: "cursor-agent", runs: false, tagline: "연결 준비 중" },
  { id: "copilot", title: "GitHub Copilot CLI", vendor: "GitHub", bin: "copilot", runs: false, tagline: "연결 준비 중" },
];

export const CLAUDE_MODELS = [
  { id: "", label: "기본 (Claude Code 설정)" }, { id: "claude-fable-5-1", label: "Fable 5.1" }, { id: "opus", label: "Opus (최신)" },
  { id: "sonnet", label: "Sonnet (최신)" }, { id: "haiku", label: "Haiku (최신)" },
];

/** API 키 제공자. protocol: anthropic → Claude Code, responses → Codex */
export const PROVIDERS = [
  { id: "anthropic", title: "Anthropic", protocol: "anthropic", baseUrl: "https://api.anthropic.com", auth: "x-api-key", models: ["claude-fable-5-1", "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"], keyHint: "sk-ant-…", console: "https://console.anthropic.com/settings/keys" },
  { id: "openrouter", title: "OpenRouter", protocol: "anthropic", baseUrl: "https://openrouter.ai/api", auth: "bearer", models: ["anthropic/claude-sonnet-5.5", "anthropic/claude-opus-5.5", "openai/gpt-6.1-sol", "google/gemini-3.5-pro", "deepseek/deepseek-v4-pro", "qwen/qwen3.7-plus"], keyHint: "sk-or-…", console: "https://openrouter.ai/keys", note: "Gemini · Mistral · Qwen 등 거의 모든 모델을 한 키로" },
  { id: "openai", title: "OpenAI", protocol: "responses", baseUrl: "https://api.openai.com/v1", auth: "bearer", models: ["gpt-6.1-sol", "gpt-6-astra", "gpt-5.6-sol", "gpt-6-luna"], keyHint: "sk-…", console: "https://platform.openai.com/api-keys" },
  { id: "deepseek", title: "DeepSeek", protocol: "anthropic", baseUrl: "https://api.deepseek.com/anthropic", auth: "bearer", models: ["deepseek-v4-pro", "deepseek-v4-flash"], keyHint: "sk-…", console: "https://platform.deepseek.com/api_keys" },
  { id: "xai", title: "xAI (Grok)", protocol: "responses", baseUrl: "https://api.x.ai/v1", auth: "bearer", models: ["grok-5", "grok-5-mini"], keyHint: "xai-…", console: "https://console.x.ai" },
  { id: "minimax", title: "MiniMax", protocol: "anthropic", baseUrl: "https://api.minimax.io/anthropic", auth: "bearer", models: ["MiniMax-M2.7", "MiniMax-M2.7-highspeed"], keyHint: "MiniMax 키", console: "https://www.minimax.io/platform" },
  { id: "moonshot", title: "Kimi (Moonshot)", protocol: "anthropic", baseUrl: "https://api.moonshot.ai/anthropic", auth: "bearer", models: ["kimi-k3", "kimi-k2.5"], keyHint: "sk-…", console: "https://platform.moonshot.ai" },
  { id: "zai", title: "Z.ai (GLM)", protocol: "anthropic", baseUrl: "https://api.z.ai/api/anthropic", auth: "bearer", models: ["glm-5", "glm-4.7"], keyHint: "Z.ai 키", console: "https://z.ai/manage-apikey" },
  { id: "azure", title: "Azure OpenAI", protocol: "responses", baseUrl: "", auth: "api-key", models: [], keyHint: "Azure 키", console: "https://portal.azure.com", note: "배포 주소 · 배포 이름을 직접 입력" },
  { id: "ollama", title: "Ollama (내 컴퓨터)", protocol: "anthropic", baseUrl: "http://localhost:11434", auth: "bearer", models: [], keyHint: "키 필요 없음", local: true, note: "로컬 LLM — 도구 사용을 지원하는 모델(qwen3-coder 등) 권장" },
  { id: "custom", title: "직접 입력", protocol: "anthropic", baseUrl: "", auth: "bearer", models: [], keyHint: "키", custom: true, note: "Anthropic 또는 OpenAI Responses 호환 주소" },
];

// ---------- 키 보관 ----------
export function readKeys() { try { return JSON.parse(readFileSync(KEY_FILE, "utf8")); } catch { return {}; } }
/** 0600 으로 만든 임시 파일에 쓰고 rename — 권한이 열린 순간이 없게 */
export function writeKey(id, key) {
  const all = readKeys();
  if (key) all[id] = key; else delete all[id];
  mkdirSync(path.dirname(KEY_FILE), { recursive: true, mode: 0o700 });
  const tmp = `${KEY_FILE}.${process.pid}.tmp`;
  writeFileSync(tmp, JSON.stringify(all, null, 1), { mode: 0o600 });
  try { chmodSync(tmp, 0o600); } catch { /* 윈도우 */ }
  renameSync(tmp, KEY_FILE);
}
export const mask = (k) => (k ? `${k.slice(0, 3)}…${k.slice(-2)}` : "");

// ---------- 감지 (비동기 — 이벤트 루프를 막지 않는다. 결과는 캐시, 10분마다 · 요청 시 새로) ----------
const sh = (where) => OS === "windows" && /\.(cmd|bat)$/i.test(where || "");
function exec(bin, args, timeout) {
  return new Promise((resolve) => {
    execFile(bin, args, { encoding: "utf8", timeout, shell: sh(bin), windowsHide: true }, (err, stdout, stderr) => resolve({ ok: !err, out: String(stdout || stderr || "") }));
  });
}
let detected = null, detectedAt = 0, detecting = null;
let codexModelCache = null;
async function probeAll() {
  const list = await Promise.all(AGENTS.map(async (a) => {
    const where = which(a.bin);
    let version = null, auth = null;
    if (where) version = (await exec(where, ["--version"], 8000)).out.trim().split("\n")[0].slice(0, 60) || null;
    if (where && a.id === "codex") auth = (await exec(where, ["login", "status"], 8000)).out.trim().split("\n")[0] || null;
    return { ...a, installed: !!where, path: where, version, auth };
  }));
  const cx = list.find((a) => a.id === "codex");
  const base = [{ id: "", label: "기본 (Codex 설정)", efforts: [] }];
  if (cx?.installed) {
    const r = await exec(cx.path, ["debug", "models"], 20000);
    try {
      const d = JSON.parse(r.out);
      codexModelCache = [...base, ...d.models.filter((m) => m.visibility !== "hide")
        .map((m) => ({ id: m.slug, label: m.display_name || m.slug, efforts: (m.supported_reasoning_levels || []).map((x) => x.effort) }))];
    } catch { codexModelCache = base; }
  } else codexModelCache = [];
  detected = list; detectedAt = Date.now();
  return list;
}
/** 감지를 (다시) 시작. 진행 중이면 그 약속을 돌려준다 */
export function refreshAgents() {
  if (!detecting) detecting = probeAll().catch(() => detected || []).finally(() => { detecting = null; });
  return detecting;
}
/** 캐시된 감지 결과. 처음이거나 10분 지났으면 뒤에서 새로 고친다. 아직 없으면 installed:null */
export function detectAgents() {
  if (!detected || Date.now() - detectedAt > 10 * 60e3) refreshAgents();
  return detected || AGENTS.map((a) => ({ ...a, installed: null, path: null, version: null, auth: null }));
}
export function codexModels() { return codexModelCache || []; }

// ---------- 실행 구성 ----------
/** 설정 → { runtime: "claude"|"codex", model, effort, env, codexConfig[], label } */
export function resolveRuntime(cfg = {}) {
  const a = cfg.agent || {};
  const effort = a.effort ?? cfg.effort ?? "";
  if (a.mode === "api") {
    const p = PROVIDERS.find((x) => x.id === a.provider) || PROVIDERS[0];
    const baseUrl = (a.baseUrl || p.baseUrl || "").replace(/\/+$/, "");
    const key = readKeys()[p.id] || (p.local ? "ollama" : "");
    const model = a.apiModel || p.models[0] || "";
    const protocol = p.custom ? (a.protocol === "responses" ? "responses" : "anthropic") : p.protocol;
    if (!baseUrl) throw new Error(`${p.title}: 주소(Base URL)를 설정에서 입력하세요`);
    if (!key) throw new Error(`${p.title}: API 키가 없습니다 — 설정 → 에이전트 → API 키에서 넣으세요`);
    if (!model) throw new Error(`${p.title}: 모델 이름을 설정에서 입력하세요`);
    if (protocol === "anthropic") {
      const env = { ANTHROPIC_BASE_URL: baseUrl, ANTHROPIC_MODEL: model, ANTHROPIC_SMALL_FAST_MODEL: model, CLAUDE_CODE_SUBAGENT_MODEL: model };
      if (p.auth === "x-api-key") { env.ANTHROPIC_API_KEY = key; env.ANTHROPIC_AUTH_TOKEN = ""; } else { env.ANTHROPIC_AUTH_TOKEN = key; env.ANTHROPIC_API_KEY = ""; }
      return { runtime: "claude", model, effort, env, label: `${p.title} · ${model}`, provider: p.id };
    }
    const codexConfig = [
      `model_provider="fluma"`, `model_providers.fluma.name="${p.title}"`, `model_providers.fluma.base_url="${baseUrl}"`,
      `model_providers.fluma.env_key="FLUMA_BYOK_KEY"`, `model_providers.fluma.wire_api="responses"`,
    ];
    if (p.id === "azure") codexConfig.push(`model_providers.fluma.query_params={"api-version"="2025-04-01-preview"}`);
    return { runtime: "codex", model, effort, env: { FLUMA_BYOK_KEY: key }, codexConfig, label: `${p.title} · ${model}`, provider: p.id };
  }
  const cli = a.cli || "claude";
  if (cli === "codex") return { runtime: "codex", model: a.codexModel ?? "", effort, env: {}, codexConfig: [], label: `Codex${a.codexModel ? ` · ${a.codexModel}` : ""}` };
  return { runtime: "claude", model: a.claudeModel ?? cfg.model ?? "", effort, env: {}, label: `Claude Code${(a.claudeModel ?? cfg.model) ? ` · ${a.claudeModel ?? cfg.model}` : ""}` };
}

/** codex exec 인자. 처음엔 시스템 지시를 프롬프트 앞에 붙이고, 이후엔 같은 스레드를 이어간다 */
export function codexArgs({ cwd, threadId, model, effort, codexConfig = [], prompt }) {
  const args = ["exec"];
  if (threadId) args.push("resume");
  args.push("--json", "--skip-git-repo-check");
  // resume 는 --sandbox 를 받지 않으므로 설정 키로 준다 (작업 폴더만 쓰기, 네트워크 허용: 조사 · yt-dlp)
  // Docker 안에서는 bubblewrap 이 namespace 를 못 만든다 → 컨테이너가 샌드박스(이미지가 FLUMA_CODEX_SANDBOX=danger-full-access 를 준다)
  const mode = process.env.FLUMA_CODEX_SANDBOX || "workspace-write";
  args.push("-c", `sandbox_mode="${mode}"`);
  if (mode === "workspace-write") args.push("-c", "sandbox_workspace_write.network_access=true");
  if (!threadId) args.push("-C", cwd);
  for (const c of codexConfig) args.push("-c", c);
  if (model) args.push("--model", model);
  if (effort) args.push("-c", `model_reasoning_effort="${effort === "max" ? "xhigh" : effort}"`);
  if (threadId) args.push(threadId);
  args.push(prompt);
  return args;
}

/** codex --json 이벤트 → Fluma 공통 이벤트 (claude 파서와 같은 모양) */
export function makeCodexParser(emit, { onThread, rel }) {
  let said = false;
  const shell = (c) => String(c || "").replace(/^\/\S+\/(?:ba|z)?sh\s+-lc\s+/, "").replace(/^(['"])([\s\S]*)\1$/, "$2");
  return (line) => {
    let e; try { e = JSON.parse(line); } catch { return; }
    const it = e.item || {};
    if (e.type === "thread.started") { onThread?.(e.thread_id); emit({ type: "status", label: "시작" }); return; }
    if (e.type === "item.started" && it.type === "command_execution") { emit({ type: "tool_start", id: it.id, name: "Bash" }); emit({ type: "tool_use", id: it.id, name: "Bash", input: shell(it.command).slice(0, 160) }); return; }
    if (e.type === "item.started" && it.type === "reasoning") { emit({ type: "status", label: "생각 중" }); return; }
    if (e.type !== "item.completed") {
      if (e.type === "turn.completed") emit({ type: "result", ok: true, cost: null, durationMs: null, denials: [] });
      if (e.type === "turn.failed" || e.type === "error") emit({ type: "result", ok: false, cost: null, durationMs: null, denials: [], error: e.error?.message || e.message || "Codex 실패" });
      return;
    }
    if (it.type === "agent_message" && it.text) { emit({ type: "text", text: (said ? "\n\n" : "") + it.text }); said = true; }
    else if (it.type === "command_execution") emit({ type: "tool_result", id: it.id, error: it.exit_code !== 0, preview: String(it.aggregated_output || "").slice(0, 400) });
    else if (it.type === "file_change") for (const ch of it.changes || []) { const id = `${it.id}:${ch.path}`; emit({ type: "tool_start", id, name: "Edit" }); emit({ type: "tool_use", id, name: ch.kind === "add" ? "Write" : "Edit", input: rel(ch.path) }); emit({ type: "tool_result", id, error: it.status === "failed", preview: "" }); }
    else if (it.type === "web_search") { emit({ type: "tool_start", id: it.id, name: "WebSearch" }); emit({ type: "tool_use", id: it.id, name: "WebSearch", input: String(it.query || "") }); emit({ type: "tool_result", id: it.id, error: false, preview: "" }); }
    else if (it.type === "todo_list" && Array.isArray(it.items)) emit({ type: "todos", todos: it.items.map((x) => ({ content: x.text, status: x.completed ? "completed" : "pending" })) });
    else if (it.type === "error" && it.message && !/metadata/i.test(it.message)) emit({ type: "status", label: it.message.slice(0, 60) });
  };
}

export function codexPrompt(systemPrompt, message) {
  return `<FLUMA_SYSTEM>\n${systemPrompt}\n\n## 접근 제한 (반드시 지킴)\n- .env · .env.* · ~/.shortsforge/** · ~/.claude/** 는 읽지도 쓰지도 않는다.\n- 쓰기는 storyboards/ compositions/ research/ captures/ public/ audio/ characters/ workspace/tmp/ 안에서만.\n</FLUMA_SYSTEM>\n\n${message}`;
}
