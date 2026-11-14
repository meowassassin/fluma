// 에이전트 실행 환경: 로컬 CLI (Claude Code · Antigravity · Codex) 직접 구동
import { execFile } from "node:child_process";
import { OS, which } from "./platform.mjs";

/** 로컬 CLI 에이전트. runs = Fluma 가 직접 구동할 수 있는지 */
export const AGENTS = [
  { id: "claude", title: "Claude Code", vendor: "Anthropic", bin: "claude", runs: true, tagline: "파일 접근 제한 · 스킬 · 기억 연동이 가장 잘 됨 (기본)" },
  { id: "antigravity", title: "Antigravity", vendor: "Google", bin: "agy", runs: true, tagline: "Google 계정 로그인 · Gemini 모델 (숏폼 생성 파이프라인 오케스트레이터)" },
  { id: "codex", title: "Codex", vendor: "OpenAI", bin: "codex", runs: true, tagline: "ChatGPT 계정 또는 OpenAI 키로 GPT 모델 사용" },
];

/** agy models 출력(2026-11-12 확인) — 기본은 agy 설정을 따른다 */
export const AGY_MODELS = [
  { id: "", label: "기본 (Antigravity 설정)" },
  { id: "gemini-4-argon-high", label: "Gemini 4 Argon (High)" }, { id: "gemini-4-argon-medium", label: "Gemini 4 Argon (Medium)" },
  { id: "gemini-3.8-flash-high", label: "Gemini 3.8 Flash (High)" }, { id: "gemini-3.8-flash-medium", label: "Gemini 3.8 Flash (Medium)" },
  { id: "claude-opus-5-5-high", label: "Claude Opus 5.5 (High)" }, { id: "claude-sonnet-5-5-high", label: "Claude Sonnet 5.5 (High)" },
];

export const CLAUDE_MODELS = [
  { id: "", label: "기본 (Claude Code 설정)" }, { id: "claude-fable-5-1", label: "Fable 5.1" }, { id: "opus", label: "Opus (최신)" },
  { id: "sonnet", label: "Sonnet (최신)" }, { id: "haiku", label: "Haiku (최신)" },
];

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
/** 설정 → { runtime: "claude"|"antigravity"|"codex", model, effort, env, codexConfig[], label } */
export function resolveRuntime(cfg = {}) {
  const a = cfg.agent || {};
  const effort = a.effort ?? cfg.effort ?? "";
  const cli = a.cli || "claude";
  if (cli === "antigravity") return { runtime: "antigravity", model: a.agyModel ?? "", effort, env: {}, label: `Antigravity${a.agyModel ? ` · ${a.agyModel}` : ""}` };
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

/** agy(Antigravity CLI) 인자 — 한 번 실행(-p), 대화는 --conversation 으로 이어 간다. 오케스트레이터 역할 전용(영상 생성 경로 A 는 engine/gen/video.py 가 따로 부른다).
 *  도구 허용: 파일 읽기 · 쓰기 · 고치기 · 셸 · 웹 검색. 접근 제한(.env · 키 폴더 금지, 쓰기 경로)은 지시문(codexPrompt 와 같은 블록)으로 준다 */
export function agyArgs({ cwd, conversation, model, effort, prompt }) {
  // 규칙은 "이름(대상)" 꼴이어야 한다 — 이름만 쓰면 무시되고 headless 에서 자동 거부된다(2026-11-12 실측: run_command 는 없는 이름, 셸은 command).
  // 비대화형(-p)에서는 --sandbox 를 켜면 네트워크·이미지/영상 생성 스크립트가 막히고 승인 프롬프트도 띄울 수 없으므로 지시문으로만 경로를 제한한다(claude 와 동일).
  const allow = ["read_file(*)", "write_file(*)", "edit_file(*)", "command(*)", "search_web(*)", "manage_task(*)", "invoke_subagent(*)"];
  const args = ["-p", prompt, "--output-format", "stream-json", "--dangerously-skip-permissions", "--settings", JSON.stringify({ permissions: { allow } }), "--add-dir", cwd];
  if (conversation) args.push("--conversation", conversation);
  if (model) args.push("--model", model);
  if (effort) args.push("--effort", effort === "max" ? "max" : effort);
  return args;
}

/** agy 응답 앞부분에 도구 호출마다 누적된 한 줄짜리 진행 독백('~하고 있습니다.', '~다시 실행합니다.' 등)을 정리 */
function cleanAgyResponse(raw) {
  const lines = String(raw || "").split("\n");
  const isNarration = (ln) => {
    const t = ln.trim();
    if (!t || t.startsWith("#") || t.startsWith("-") || t.startsWith("*") || t.startsWith("|") || t.startsWith("```") || t.startsWith("[")) return false;
    return /(확인하고 있습니다|설정하고 있습니다|실행하고 있습니다|수정하고 있습니다|생성합니다(\([^)]*\))?|다시 실행합니다|안내드리겠습니다|보여 드리겠습니다|진행 중입니다)\.?$/.test(t);
  };
  let idx = 0;
  while (idx < lines.length - 1 && isNarration(lines[idx])) idx++;
  return lines.slice(idx).join("\n").trimStart() || String(raw || "");
}

/** agy stream-json → Fluma 공통 이벤트. 2026-11-12: 마지막 줄 {"event":"result","result":{conversation_id,status,response,error}} 만 확인됨 —
 *  중간 이벤트는 모양을 확인하기 전이라 흔한 모양(text · delta · tool)을 너그럽게 받고, 모르는 것은 무시한다 */
export function makeAgyParser(emit, { onConversation }) {
  let said = "";
  return (line) => {
    let e; try { e = JSON.parse(line); } catch { return; }
    const kind = e.event || e.type;
    if (kind === "result") {
      const r = e.result || {};
      if (r.conversation_id) onConversation?.(r.conversation_id);
      if (r.response && !said) emit({ type: "text", text: cleanAgyResponse(r.response) });
      emit({ type: "result", ok: r.status === "SUCCESS", cost: null, durationMs: r.duration_seconds ? r.duration_seconds * 1000 : null, denials: (r.denied_actions || []).map((d) => d.display_name || d.action),
        ...(r.status === "SUCCESS" ? {} : { error: r.error || "Antigravity 실패" }) });
      return;
    }
    const txt = e.text ?? e.delta ?? e.content ?? e.message?.text;
    if (/message|text|delta|assistant/i.test(String(kind)) && typeof txt === "string" && txt) { emit({ type: "text", text: txt }); said += txt; return; }
    if (/tool/i.test(String(kind)) && (e.name || e.tool)) {
      const id = String(e.id || e.call_id || `${e.name || e.tool}-${Date.now()}`);
      if (/result|end|done/i.test(String(kind))) emit({ type: "tool_result", id, error: !!e.error, preview: String(e.output || e.result || "").slice(0, 400) });
      else { emit({ type: "tool_start", id, name: String(e.name || e.tool) }); emit({ type: "tool_use", id, name: String(e.name || e.tool), input: JSON.stringify(e.input || e.args || e.params || "").slice(0, 160) }); }
      return;
    }
    if (/status|progress|thinking/i.test(String(kind))) emit({ type: "status", label: String(e.label || e.status || "생각 중").slice(0, 60) });
  };
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
  return `<FLUMA_SYSTEM>\n${systemPrompt}\n\n## 접근 제한 (반드시 지킴)\n- .env · .env.* · ~/.shortsforge/** · ~/.claude/** 는 읽지도 쓰지도 않는다.\n- 쓰기는 data/storyboards/ data/shotplans/ data/compositions/ data/research/ data/captures/ data/public/ data/audio/ data/characters/ data/workspace/tmp/ data/workspace/feel/ data/workspace/concepts/ 안에서만.\n</FLUMA_SYSTEM>\n\n${message}`;
}

// 과금 안전: '로그인으로 쓰기'(Claude Code · Codex 계정 로그인) 모드에서는 결제 경로를 바꾸는 환경 변수를 지운다.
// 서버를 띄운 셸 · systemd · Docker 에 ANTHROPIC_API_KEY 같은 값이 있으면 CLI 가 구독 대신 API 키 · 다른 공급자(Bedrock · Vertex · 게이트웨이)로
// 조용히 바뀌어 따로 청구된다. 로그인 위치를 가리키는 값(CLAUDE_CONFIG_DIR · CLAUDE_CODE_OAUTH_TOKEN …)은 남긴다 — 지우면 로그인이 풀린다.
const CLAUDE_DROP_PREFIX = ["ANTHROPIC_", "CLAUDE_CODE_USE_"];
const CLAUDE_DROP = ["AWS_BEARER_TOKEN_BEDROCK", "CLAUDE_CODE_GATEWAY_TOKEN_FILE_DESCRIPTOR"];
const CLAUDE_KEEP = ["CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CONFIG_DIR", "ANTHROPIC_CONFIG_DIR"];
const CODEX_DROP = ["OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_ORG_ID", "OPENAI_PROJECT_ID"];

/** 에이전트 프로세스에 넘길 환경 → { env, dropped: [지운 이름] } (값은 다루지 않는다) */
export function agentEnv(base, rt) {
  const env = { ...base };
  const dropped = [];
  for (const k of Object.keys(env)) {
    const drop = rt?.runtime === "codex"
      ? CODEX_DROP.includes(k)
      : !CLAUDE_KEEP.includes(k) && (CLAUDE_DROP.includes(k) || CLAUDE_DROP_PREFIX.some((p) => k.startsWith(p)) || /^CLAUDE_CODE_SKIP_.*_AUTH$/.test(k));
    if (drop) { delete env[k]; dropped.push(k); }
  }
  return { env, dropped: dropped.sort() };
}
