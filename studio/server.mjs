// Fluma 웹 API — engine/(파이썬 제작 엔진)을 부르는 서버 (127.0.0.1:4310)
//
// 원칙
//  - 이 컴퓨터의 Fluma 화면만 부를 수 있다 (Host · Origin 검사, CORS 없음). 에이전트가 파일을 쓰고 키를 가진 서버이기 때문.
//  - 어떤 오류도 서버를 죽이지 않는다: 모든 비동기 라우트는 ah() 로 감싸고, 오류는 {error:{code,message}} 한 모양으로.
//  - 목록(엔진 · 음성 · 기억 · 에이전트)은 메모리 캐시에서 바로. 느린 확인은 뒤에서, 끝나면 이벤트로 알린다.
//  - 오래 걸리는 일은 작업(jobs.mjs) — 대기열 · 진행률 · 취소 · 시간 제한.
//  - 파일 감시는 콘텐츠 폴더만, (종류, 영상) 단위로 모아 300ms 뒤 한 번.
import express from "express";
import { promises as fs, existsSync, readFileSync, statSync, watch, createWriteStream } from "node:fs";
import { pipeline } from "node:stream/promises";
import { Transform } from "node:stream";
import path from "node:path";
import os from "node:os";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import { createAgent } from "./agent.mjs";
import { NAME_RE as MCP_NAME, loadMcp, normalize as mcpNormalize, publicMcp, saveMcp, testMcp } from "./mcp.mjs";
import { createJobs } from "./jobs.mjs";
import { createCrafts } from "./crafts.mjs";
import { zip, unzip } from "./zipstore.mjs";
import { createYoutube } from "./youtube.mjs";
import { pythonCmd, venvBin } from "./platform.mjs";
import { AGENTS, PROVIDERS, CLAUDE_MODELS, detectAgents, refreshAgents, codexModels, readKeys, writeKey, mask, resolveRuntime } from "./runtimes.mjs";
import { HttpError, bad, notFound, conflict, ah, sendError, isId, checkId, within, atomicWrite, readJson, run, requestSignal, tail, logEffort } from "./lib.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const PY = pythonCmd(ROOT);
const STORY = path.join(ROOT, "data", "storyboards");
const ENGINES = path.join(ROOT, "engine");   // 렌더 엔진 = engine/<이름>/renderer/
const OUT = path.join(ROOT, "data", "out");
const PUBLIC = path.join(ROOT, "data", "public");
const RENDER_WORK = path.join(ROOT, "data", "workspace", "render");
const SESS = path.join(ROOT, "data", "workspace", "sessions");
const QUEUE = path.join(ROOT, "data", "queue.md");
const PORT = Number(process.env.PORT || 4310);

// 하위 프로세스(python3, claude)가 저장소 .venv 의 파이썬을 쓰도록
const VENV_BIN = venvBin(ROOT);
if (existsSync(VENV_BIN)) process.env.PATH = `${VENV_BIN}${path.delimiter}${process.env.PATH}`;

process.on("unhandledRejection", (e) => console.error("[api] 처리되지 않은 거부:", e));
process.on("uncaughtException", (e) => { console.error("[api] 처리되지 않은 예외 — 종료 (systemd 가 다시 띄움):", e); process.exit(1); });

const agent = createAgent({ ROOT, env: process.env, onState: (id, running) => publish({ kind: "agent", id, running }) });
const jobs = createJobs({ onChange: (j) => publish({ kind: "job", id: j.project ?? undefined, job: j }) });

const app = express();
app.disable("x-powered-by");

// ---------- 접근 제한: 이 컴퓨터의 Fluma 화면만 ----------
const PORTS = [String(PORT), "4311"];
const ORIGINS = new Set(PORTS.flatMap((p) => [`http://localhost:${p}`, `http://127.0.0.1:${p}`]));
app.use((req, res, next) => {
  const host = String(req.headers.host || "");
  const m = host.match(/^(localhost|127\.0\.0\.1)(?::(\d+))?$/);
  if (!m || (m[2] && !PORTS.includes(m[2]))) return sendError(res, 403, "bad_host", "이 컴퓨터의 Fluma 화면에서만 열 수 있습니다");
  const origin = req.headers.origin;
  if (origin && !ORIGINS.has(origin)) return sendError(res, 403, "bad_origin", "다른 사이트에서는 Fluma 서버를 부를 수 없습니다");
  next();
});
app.use(express.json({ limit: "5mb" }));

// ---------- 공용 ----------
const sbPath = (id) => path.join(STORY, `${checkId(id)}.json`);
const clientOf = (req) => { const c = String(req.headers["x-fluma-client"] || ""); return /^[A-Za-z0-9_-]{4,64}$/.test(c) ? c : null; };
const parseLint = (text) => String(text || "").split(/\r?\n/).filter(Boolean).map((l) => {
  const m = l.match(/^([A-Z]\d{2})\s+scene=(\S+)\s+(.*)$/);
  return m ? { code: m[1], scene: m[2] === "None" ? null : Number(m[2]), message: m[3] } : { code: "", scene: null, message: l };
});
const engArgs = (q = {}) => {
  const a = [];
  if (q.engine && /^[a-z0-9-]+$/.test(q.engine)) a.push("--engine", q.engine);
  if (q.template && /^[A-Za-z0-9_-]+$/.test(q.template)) a.push("--template", q.template);
  return a;
};
const iconUrl = (n) => existsSync(path.join(ROOT, "studio", "public", "engine-icons", `${n}.png`)) ? `/api/engine-icons/${n}.png`
  : existsSync(path.join(ROOT, "studio", "public", "engine-icons", `${n}.svg`)) ? `/api/engine-icons/${n}.svg` : null;
const py = (args, opts = {}) => run(PY, args, { cwd: ROOT, timeout: 60e3, ...opts });

// ---------- 영상(프로젝트) 소유: 접두어가 아니라 '가장 긴 일치 id' ----------
let idsCache = { at: 0, ids: [] };
async function knownIds() {
  if (Date.now() - idsCache.at < 2000) return idsCache.ids;
  const ids = new Set();
  for (const f of existsSync(STORY) ? await fs.readdir(STORY) : []) if (f.endsWith(".json") && isId(f.slice(0, -5))) ids.add(f.slice(0, -5));
  for (const f of existsSync(SESS) ? await fs.readdir(SESS) : []) if (f.endsWith(".json") && isId(f.slice(0, -5))) ids.add(f.slice(0, -5));
  const comp = path.join(ROOT, "data", "compositions");
  for (const f of existsSync(comp) ? await fs.readdir(comp) : []) if (isId(f)) ids.add(f);
  idsCache = { at: Date.now(), ids: [...ids] };
  return idsCache.ids;
}
function ownerOf(name, ids) {
  let best = null;
  for (const id of ids) if ((name === id || name.startsWith(id + ".") || name.startsWith(id + "-")) && (!best || id.length > best.length)) best = id;
  return best;
}
async function ownedBy(id, names) { const ids = [...new Set([...(await knownIds()), id])]; return names.filter((n) => ownerOf(n, ids) === id); }

// ---------- 캐시 (오래된 값을 바로 주고 뒤에서 새로) ----------
const cache = new Map();
function cached(key, loader, ttl = 10 * 60e3, onFresh) {
  let c = cache.get(key);
  if (!c) { c = { value: undefined, at: 0, loading: null, stale: false }; cache.set(key, c); }
  if (!c.loading && (!c.at || c.stale || Date.now() - c.at > ttl)) {
    c.stale = false;
    c.loading = loader().then((v) => { c.value = v; c.at = Date.now(); onFresh?.(v); })
      .catch((e) => console.error(`[api] ${key} 불러오기 실패`, e)).finally(() => { c.loading = null; });
  }
  return c;
}
const invalidate = (key) => { const c = cache.get(key); if (c) c.stale = true; };
/** 처음 계산이면 잠깐(최대 ms) 기다려 본다 — 서버가 막 뜬 직후 빈 목록을 덜 보이게 */
async function cachedValue(key, loader, { wait = 0, ttl, onFresh } = {}) {
  const c = cached(key, loader, ttl, onFresh);
  if (c.value === undefined && c.loading && wait) await Promise.race([c.loading, new Promise((r) => setTimeout(r, wait))]);
  return c.value;
}
const lastJson = (r) => { try { return JSON.parse(r.out.trim().split("\n").pop()); } catch { return null; } };
/** 스크립트 결과 규약(engine/core/result.py): 출력 끝의 FLUMA_RESULT · FLUMA_NEEDS_INPUT · FLUMA_ERROR 블록 → { head, status, 키: 값 | [값…] } */
const resultBlock = (out) => {
  const lines = String(out || "").trim().split("\n");
  const at = Math.max(lines.lastIndexOf("FLUMA_RESULT"), lines.lastIndexOf("FLUMA_NEEDS_INPUT"), lines.lastIndexOf("FLUMA_ERROR"));
  if (at < 0) return null;
  const b = { head: lines[at] };
  for (const ln of lines.slice(at + 1)) {
    const m = /^([a-z_]+)=(.*)$/.exec(ln); if (!m) continue;
    b[m[1]] = b[m[1]] === undefined ? m[2] : [].concat(b[m[1]], m[2]);
  }
  return b;
};
/** 렌더 결과 영상(절대 경로) — 결과 블록의 file, 없으면(예전 스크립트) 마지막 줄 */
const renderedFile = (r) => {
  const b = resultBlock(r.out);
  const f = b?.head === "FLUMA_RESULT" && typeof b.file === "string" ? (path.isAbsolute(b.file) ? b.file : path.join(ROOT, b.file)) : (r.out.trim().split("\n").pop() || "");
  return f.endsWith(".mp4") && existsSync(f) ? f : null;
};

// ---------- 콘티 ----------
app.get("/api/storyboards", ah(async (_req, res) => {
  const files = existsSync(STORY) ? (await fs.readdir(STORY)).filter((f) => f.endsWith(".json") && isId(f.slice(0, -5))) : [];
  const ids = await knownIds();
  const outs = new Map();
  for (const o of existsSync(OUT) ? await fs.readdir(OUT) : []) {
    if (!o.endsWith(".mp4")) continue;
    const id = ownerOf(o, ids); if (!id) continue;
    const e = outs.get(id) || { final: 0, draft: 0 }; e[o.includes("-draft") ? "draft" : "final"]++; outs.set(id, e);
  }
  const list = [];
  for (const f of files) {
    const p = path.join(STORY, f); const id = f.slice(0, -5);
    const sb = await readJson(p); if (!sb || typeof sb !== "object") continue;
    const st = await fs.stat(p).catch(() => null); if (!st) continue;
    list.push({ id, title: sb.title, format: sb.format, audience: sb.audience ?? null, brand: sb.brand ?? null,
      duration_sec: sb.duration_sec, template: JSON.stringify(sb).includes("{{"), updated: st.mtime.toISOString(),
      cast: (sb.scenes || []).map((x) => ({ e: x.engine || sb.engine || "craft", sec: x.sec || 0 })),
      renders: outs.get(id) || { final: 0, draft: 0 }, composed: existsSync(path.join(ROOT, "data", "compositions", id, "scene.js")) || existsSync(path.join(ROOT, "data", "compositions", id, "craft", "craft.json")), reference: sb.reference || [],
      running: agent.running(id) });
  }
  // 콘티 없이 대화만 있는 초안 프로젝트
  for (const f of existsSync(SESS) ? (await fs.readdir(SESS)).filter((x) => x.endsWith(".json")) : []) {
    const id = f.slice(0, -5);
    if (!isId(id) || list.some((x) => x.id === id)) continue;   // _trends 등 시스템 대화는 영상이 아님
    const st = await fs.stat(path.join(SESS, f)).catch(() => null); if (!st) continue;
    list.push({ id, title: id, format: "", audience: null, brand: null, duration_sec: 0, template: false, draft: true, updated: st.mtime.toISOString(), running: agent.running(id) });
  }
  list.sort((a, b) => (a.updated < b.updated ? 1 : -1));
  res.json(list);
}));

app.get("/api/storyboards/:id", ah(async (req, res) => {
  const p = sbPath(req.params.id);
  if (!existsSync(p)) throw notFound("콘티가 없습니다");
  const sb = await readJson(p); if (!sb) throw new HttpError(500, "broken_storyboard", "콘티 파일이 깨져 있습니다");
  res.json(sb);
}));

// 검사: 입력 파일이 그대로면 다시 돌리지 않는다 · 동시에 하나만.
// lint.py 는 콘티만이 아니라 음성 타이밍(L14) · 화면 구성(L15) · 레이어 요소(L17)도 본다 → 그 파일들의 시각도 열쇠에 넣는다
const lintCache = new Map();   // id -> { mtime, lint, p }
const mtimeOf = async (rel) => (await fs.stat(path.join(ROOT, rel)).catch(() => null))?.mtimeMs ?? 0;
async function lintOf(id) {
  const p = sbPath(id);
  const st = await fs.stat(p).catch(() => null); if (!st) return [];
  const stamp = [st.mtimeMs, ...(await Promise.all([`data/audio/${id}.timing.json`, `data/compositions/${id}/scene.js`, `data/compositions/${id}/graph.js`, `data/public/elements/${id}`].map(mtimeOf)))].join(":");
  const c = lintCache.get(id);
  if (c && c.mtime === stamp) return c.p ?? c.lint;
  const promise = py(["engine/checks/lint.py", `data/storyboards/${id}.json`], { timeout: 30e3 }).then((r) => parseLint(r.out + r.err));
  lintCache.set(id, { mtime: stamp, p: promise });
  const lint = await promise;
  lintCache.set(id, { mtime: stamp, lint });
  return lint;
}
const hardOf = (lint) => lint.filter((l) => l.code && !l.code.startsWith("T") && l.message !== "통과");

app.put("/api/storyboards/:id", ah(async (req, res) => {
  const p = sbPath(req.params.id);
  const b = req.body;
  if (!b || typeof b !== "object" || Array.isArray(b) || !Array.isArray(b.scenes)) throw bad("콘티 형식이 올바르지 않습니다 (scenes 가 필요)", "bad_storyboard");
  markEcho(p, clientOf(req));
  await atomicWrite(p, JSON.stringify(b, null, 2));
  logEffort(ROOT, req.params.id, "edit", "콘티 직접 수정");
  const lint = await lintOf(req.params.id);
  res.json({ ok: hardOf(lint).length === 0, lint });
}));
app.get("/api/storyboards/:id/lint", ah(async (req, res) => {
  if (!existsSync(sbPath(req.params.id))) throw notFound("콘티가 없습니다");
  res.json({ lint: await lintOf(req.params.id) });
}));


// ---------- 엔진 · 템플릿 ----------
async function readEngines() {
  const out = [];
  if (!existsSync(ENGINES)) return out;
  for (const name of (await fs.readdir(ENGINES)).sort()) {
    const meta = await readJson(path.join(ENGINES, name, "renderer", "engine.json")); if (!meta) continue;
    const tdir = path.join(ENGINES, name, "renderer", "templates");
    const templates = [];
    for (const t of existsSync(tdir) ? (await fs.readdir(tdir)).sort() : []) {
      const tm = await readJson(path.join(tdir, t, "meta.json"));
      if (tm) templates.push({ name: t, engine: name, ...tm });
    }
    templates.sort((a, b) => Number(!!b.primary) - Number(!!a.primary));
    out.push({ ...meta, name, templates });
  }
  out.sort((a, b) => (a.name === "craft" ? -1 : b.name === "craft" ? 1 : a.name.localeCompare(b.name)));   // 기본 엔진(Craft)이 맨 앞
  return out;
}
const loadEngineAvail = async () => {
  const r = await py(["-c", "import sys,json;sys.path.insert(0,'engine');import paths;import engines as e;print(json.dumps({n:bool(e.adapter(n).available()) for n in e.list_engines()}))"], { timeout: 120e3 });
  const v = lastJson(r); if (!v) throw new Error(tail(r.err)); return v;
};
const engineList = () => cachedValue("engines:list", readEngines, { wait: 3000, ttl: 3600e3 });
const engineAvail = (wait = 0) => cachedValue("engines:avail", loadEngineAvail, { wait, onFresh: () => publish({ kind: "engines" }) });
app.get("/api/engines", ah(async (_req, res) => {
  const [list, avail] = [await engineList() || [], await engineAvail(0)];
  res.json(list.map((e) => ({ ...e, available: avail ? !!avail[e.name] : null, icon: iconUrl(e.name) })));
}));
app.get("/api/templates", ah(async (_req, res) => res.json((await engineList() || []).flatMap((e) => e.templates))));
app.use("/api/engine-icons", express.static(path.join(ROOT, "studio", "public", "engine-icons"), { maxAge: "1d" }));

// ---------- 생성 · 음성 API 키 (에이전트의 OpenRouter 처럼 키만 넣으면 그 공급자의 모델 · 목소리를 쓴다) ----------
// 저장: ~/.shortsforge/api-keys.json (0600, 에이전트는 못 읽음). 스크립트는 engine/core/apikeys.py 로 환경 변수 → 이 파일 → .env.local 순서로 읽는다
const API_KEY_FILE = path.join(os.homedir(), ".shortsforge", "api-keys.json");
// 오픈라우터 하나(보기 · 만들기 · 말하기) + 무료 스톡 영상. 업체별 키(Typecast · ElevenLabs · Gemini)는 2026-11-09 에 없앴다
const GEN_KEYS = [
  { id: "openrouter", ready: true, env: "OPENROUTER_API_KEY", title: "OpenRouter", what: "키 하나로 보기(영상 이해) · 그리기 · 영상 생성 · 음성 · 받아쓰기 — 모델은 아래에서 능력마다 고른다. 쓴 만큼 크레딧에서 나간다", caps: ["모델"], keyHint: "sk-or-…", console: "https://openrouter.ai/settings/keys", docs: "https://openrouter.ai/docs", paid: true,
    test: { url: "https://openrouter.ai/api/v1/key", auth: "bearer" } },
  { id: "typecast", ready: true, env: "TYPECAST_API_KEY", title: "Typecast", what: "한국어 성우 음성 — 감정 · 단어 시각", caps: ["음성"], keyHint: "Typecast API 키", console: "https://typecast.ai/developers/api", docs: "https://typecast.ai/docs", paid: true,
    test: { url: "https://api.typecast.ai/v3/voices?model=ssfm-v31", auth: "x-api-key" } },
  { id: "elevenlabs", ready: true, env: "ELEVENLABS_API_KEY", title: "ElevenLabs", what: "다국어 음성 · 목소리 복제", caps: ["음성"], keyHint: "sk_…", console: "https://elevenlabs.io/app/settings/api-keys", docs: "https://elevenlabs.io/docs", paid: true,
    test: { url: "https://api.elevenlabs.io/v1/user", auth: "xi-api-key" } },
  { id: "pexels", ready: true, env: "PEXELS_API_KEY", title: "Pexels", what: "무료 스톡 영상 · 사진 — 일상 · 감성 · 광고 장면의 바탕(B-roll). 출처 표기 권장", caps: ["스톡 영상"], keyHint: "Pexels API 키", console: "https://www.pexels.com/api/new/", docs: "https://www.pexels.com/api/documentation/",
    test: { url: "https://api.pexels.com/videos/search?query=city&per_page=1", auth: "Authorization" } },
  { id: "youtube", ready: true, env: "YOUTUBE_API_KEY", title: "YouTube Data API", what: "요즘 인기 · 최신 곡 찾기(음악 인기 차트 KR · 최근 1년 조회수 순). 곡 정보만 받는다 — 영상에는 무료 곡만 넣고 상업 유행곡은 업로드 때 붙일 곡으로 알려 준다. 없으면 웹 검색으로 찾는다", caps: ["음악"], keyHint: "AIza…", console: "https://console.cloud.google.com/apis/library/youtube.googleapis.com", docs: "https://developers.google.com/youtube/v3/docs",
    test: { url: "https://www.googleapis.com/youtube/v3/videos?part=id&chart=mostPopular&maxResults=1", auth: "query:key" } },
  { id: "pixabay", ready: true, env: "PIXABAY_API_KEY", title: "Pixabay", what: "무료 스톡 영상 — Pexels 에 없을 때 두 번째로 찾는 곳", caps: ["스톡 영상"], keyHint: "Pixabay API 키", console: "https://pixabay.com/accounts/register/", docs: "https://pixabay.com/api/docs/",
    test: { url: "https://pixabay.com/api/videos/?q=city&per_page=3", auth: "query:key" } },
];

const genKeyValue = (k) => process.env[k.env] || readApiKeys()[k.env] || (k.id === "openrouter" ? readKeys().openrouter : "") || envLocalKeys()[k.env] || "";   // 오픈라우터는 에이전트 설정의 키도 같은 키로
const readApiKeys = () => { try { return JSON.parse(readFileSync(API_KEY_FILE, "utf8")); } catch { return {}; } };
/** .env.local 에 있는 키 이름만(값은 가리기만) — 예전 방식으로 넣은 키도 '있음'으로 보인다 */
const envLocalKeys = () => {
  try { const o = {}; for (const ln of readFileSync(path.join(ROOT, ".env.local"), "utf8").split("\n")) { const m = /^\s*([A-Z0-9_]+)\s*=\s*"?([^"\s#]+)/.exec(ln); if (m) o[m[1]] = m[2]; } return o; } catch { return {}; }
};
// 연결 시험: 공급자 공식 주소(GEN_KEYS.test.url)에만 키를 보낸다 — 요청이 주소를 정할 수 없다. 응답 내용은 돌려주지 않고 상태만
app.post("/api/gen-keys/:id/test", ah(async (req, res) => {
  const k = GEN_KEYS.find((x) => x.id === req.params.id); if (!k) throw notFound("공급자가 없습니다");
  const key = genKeyValue(k);
  if (!key) return res.json({ ok: false, msg: "키가 없습니다" });
  if (!k.test) return res.json({ ok: null, msg: "이 공급자는 연결 시험을 지원하지 않아요 — 실제 생성 때 확인됩니다" });
  const q = k.test.auth.startsWith("query:") ? k.test.auth.slice(6) : null;      // 키를 주소에 넣는 공급자(Pixabay)
  const h = q ? {} : k.test.auth === "bearer" ? { Authorization: `Bearer ${key}` } : { [k.test.auth]: key };
  const url = q ? `${k.test.url}${k.test.url.includes("?") ? "&" : "?"}${q}=${encodeURIComponent(key)}` : k.test.url;
  try {
    const r = await fetch(url, { headers: h, signal: AbortSignal.timeout(15000) });
    res.json({ ok: r.ok, status: r.status, msg: r.ok ? "연결됨" : r.status === 401 || r.status === 403 ? "키가 맞지 않아요" : `실패 ${r.status}` });
  } catch (e) { res.json({ ok: false, msg: `연결 실패: ${String(e.message || e).slice(0, 80)}` }); }
}));
app.get("/api/gen-keys", ah(async (_req, res) => {
  const saved = readApiKeys(), local = envLocalKeys();
  const ICON = { pexels: "pexels", pixabay: "pixabay", youtube: "youtube", openrouter: "prov-openrouter", typecast: "typecast", elevenlabs: "elevenlabs" };
  const byok = readKeys();
  res.json(GEN_KEYS.map(({ test, ...k }) => { const agentKey = k.id === "openrouter" ? byok.openrouter || "" : "";
    const v = process.env[k.env] || saved[k.env] || agentKey || local[k.env] || "";
    return { ...k, icon: iconUrl(ICON[k.id] || k.id), testable: !!test, hasKey: !!v, keyMasked: mask(v),
      source: process.env[k.env] ? "env" : saved[k.env] ? "saved" : agentKey ? "agent" : local[k.env] ? "env.local" : null }; }));
}));
app.put("/api/gen-keys/:id", ah(async (req, res) => {
  const k = GEN_KEYS.find((x) => x.id === req.params.id); if (!k) throw notFound("공급자가 없습니다");
  const key = String(req.body?.key ?? "").trim();
  if (key.length > 400 || /\s/.test(key)) throw bad("키 형식이 올바르지 않습니다", "bad_key");
  const all = readApiKeys(); if (key) all[k.env] = key; else delete all[k.env];
  await fs.mkdir(path.dirname(API_KEY_FILE), { recursive: true, mode: 0o700 });
  await atomicWrite(API_KEY_FILE, JSON.stringify(all, null, 1), { mode: 0o600 });
  // 키가 바뀌면 쓸 수 있는 음성 엔진이 달라진다
  invalidate("voices:avail");
  cached("voices:avail", loadVoiceAvail, undefined, () => publish({ kind: "registry", name: "voices" }));
  res.json({ ok: true, keyMasked: mask(key) });
}));

// ---------- 음성 엔진 (engine/voice/engines/<이름>/voice.json) ----------
const VOICES = path.join(ROOT, "engine", "voice", "engines");
const loadVoiceAvail = async () => {
  const r = await py(["-c", "import sys,json;sys.path.insert(0,'engine');import paths;import tts;a={n:tts.engine_available(n) for n in tts.list_voice_engines()}\nif a.get('typecast'):\n  try: tts.typecast_voices()\n  except Exception as e: print('[typecast]',e,file=sys.stderr)\nprint(json.dumps(a))"], { timeout: 60e3 });
  const v = lastJson(r); if (!v) throw new Error(tail(r.err)); return v;
};
app.get("/api/voices", ah(async (_req, res) => {
  const avail = await cachedValue("voices:avail", loadVoiceAvail, { onFresh: () => publish({ kind: "registry", name: "voices" }) });
  const list = [];
  for (const n of existsSync(VOICES) ? await fs.readdir(VOICES) : []) {
    const v = await readJson(path.join(VOICES, n, "voice.json")); if (!v) continue;
    // 목록을 API 로 받는 엔진(dynamic_voices): tts.py 가 받아 둔 data/workspace/cache/<이름>-voices.json
    if (v.dynamic_voices && avail?.[n]) v.voices = (await readJson(path.join(ROOT, "data", "workspace", "cache", `${n}-voices.json`))) || [];
    list.push({ ...v, name: v.name || n, available: avail ? !!avail[n] : null, icon: iconUrl(n === "openrouter" ? "prov-openrouter" : n) });
  }
  const order = { builtin: 0, adapter: 1, planned: 2 };
  // 사용 가능 → 무료(내 컴퓨터 · 온라인) → 유료 API → 준비 중, 시험용 무음은 맨 끝
  const rank = (v) => (v.name === "silent" ? 9 : (v.available === false ? 4 : 0) + (v.kind === "api" ? 2 : 0) + (order[v.status] ?? 3) * 0.1);
  list.sort((a, b) => rank(a) - rank(b) || String(a.title).localeCompare(String(b.title)));
  res.json(list);
}));
app.post("/api/voices/:name/preview", ah(async (req, res) => {
  const { name } = req.params; const voice = String(req.body?.voice || "");
  if (!/^[a-z0-9_-]+$/.test(name) || !existsSync(path.join(VOICES, name, "voice.json"))) throw notFound("음성 엔진이 없습니다");
  if (voice && !/^[A-Za-z0-9+_.-]+$/.test(voice)) throw bad("목소리 이름이 올바르지 않습니다");
  const text = String(req.body?.text || "안녕하세요, 플루마입니다. 오늘은 블루투스가 끊기는 이유를 알아볼게요.").slice(0, 200);
  const dir = path.join(ROOT, "data", "workspace", "tmp", "voice-preview"); await fs.mkdir(dir, { recursive: true });
  const out = path.join(dir, `${name}-${voice || "default"}-${Date.now().toString(36)}.wav`);
  const r = await py(["engine/voice/tts.py", text, out, name, ...(voice ? [voice] : [])], { timeout: 90e3, signal: requestSignal(req, res) });
  if (r.canceled) return;
  if (r.code === 2) { const m = /\[음성\] (.+)/.exec(r.err || ""); throw new HttpError(409, "voice_unavailable", m ? m[1].trim() : "이 음성을 쓸 수 없습니다"); }   // 설치 안 됨 · 키 없음 — 할 일을 그대로
  if (r.code !== 0 || !existsSync(out)) { console.error("[voice preview]", tail(r.err || r.out)); throw new HttpError(500, "voice_failed", "목소리를 만들지 못했습니다", tail(r.err || r.out, 3)); }
  res.json({ ok: true, url: `/api/voice-preview/${path.basename(out)}` });
}));
app.use("/api/voice-preview", express.static(path.join(ROOT, "data", "workspace", "tmp", "voice-preview")));

// ---------- 트렌드: 쇼츠 엑스레이(분해 분석) · 판별 ----------
const XRAY = path.join(ROOT, "data", "public", "trends", "xray");
const isVid = (v) => /^[A-Za-z0-9_-]{11}$/.test(String(v || ""));
app.get("/api/trends/xray", ah(async (_req, res) => {
  const ids = existsSync(XRAY) ? (await fs.readdir(XRAY)).filter((v) => isVid(v) && existsSync(path.join(XRAY, v, "xray.json"))) : [];
  const running = jobs.list({ type: "xray" }).filter((j) => !jobs.TERMINAL.has(j.status) && j.project?.startsWith("trend:")).map((j) => ({ id: j.project.slice(6), jobId: j.id, progress: j.progress, stage: j.stage }));
  res.json({ done: ids, running });
}));
app.post("/api/trends/xray/:vid", ah(async (req, res) => {
  const vid = req.params.vid; if (!isVid(vid)) throw bad("쇼츠 id 가 올바르지 않습니다");
  // 작업의 project 칸은 "trend:<id>" — 영상 편집 작업과 섞이지 않게
  const j = jobs.create({ type: "xray", project: `trend:${vid}`, key: `xray:${vid}`, label: "쇼츠 분해 분석", work: async (h) => {
    // 이미 끝난 단계는 건너뛴다(force 면 다시) — 에이전트 · 사용자가 같은 영상을 다시 불러도 몇 초 안에 끝나게
    const force = !!req.body?.force, dir = path.join(XRAY, vid);
    const fast = !!req.body?.fast;     // 빠른 분석: 같은 채널은 2편만 · 가벼운 받아쓰기(base) — 원클릭 도구와 견줄 속도가 필요할 때
    // deep=false(에이전트 레퍼런스 분석 기본): 누끼 · 음원 분리를 건너뛴다 — 이해는 VL 이 맡고, 레이어는 분해도 화면을 열 때만(deep)
    const deep = req.body?.deep !== false;
    const prev = await fs.readFile(path.join(dir, "xray.json"), "utf8").then(JSON.parse).catch(() => null);
    if (force || !prev || !existsSync(path.join(dir, "src.mp4")) || (deep && prev.quick)) {
      const r = await h.run(PY, ["engine/research/shorts_xray.py", vid, ...(fast ? ["--whisper", "base"] : []), ...(deep ? [] : ["--quick"])], { cwd: ROOT, onLine: (l) => { const m = /^@progress ([\d.]+) (.*)$/.exec(l); if (m) h.progress(Number(m[1]) * 0.7, m[2]); } });
      if (r.timedOut || r.canceled) return r;
      if (r.code !== 0) return { error: "분해 분석에 실패했습니다", detail: tail(r.err || r.out) };
    }
    // 이어서 VL 이해(보기 모델이 있으면 — 장면 · 훅 · 반전 · 편집 문법 · 자막 말투 · 붙잡는 장치). 키가 없거나 실패해도 측정 결과는 남는다
    // VL 이해와 스타일 카드를 동시에(2026-11-09: 차례로 돌려 VL 대기 동안 아무것도 안 함). VL 은 4분이 넘으면 끊는다 — 측정 결과는 남는다
    h.progress(0.7, "VL 로 보기 · 스타일 카드");
    const [u, s] = await Promise.all([
      h.run(PY, ["engine/providers/see.py", "ref", vid, ...(force ? ["--force"] : [])], { cwd: ROOT, timeout: 4 * 60e3 }),
      // 스타일 카드(매초 글자 인식 — 편당 2분)는 분해도 화면(deep)에서만. 에이전트의 빠른 분석은 건너뛰고 제작(produce.py)이 필요한 레퍼런스만 만든다(2026-11-09)
      (!force && existsSync(path.join(dir, "style", "style.json"))) || !deep ? Promise.resolve({ code: 0 }) : h.run(PY, ["engine/research/ref_style.py", vid], { cwd: ROOT, timeout: 20 * 60e3 }),
    ]);
    if (u.code !== 0 && u.code !== 10) h.log?.(`VL 이해 건너뜀: ${tail(u.out || u.err)}`);
    // 이어서 채널 말투 카드(같은 채널 쇼츠 여러 편 — 말투 · 구성 · 농담 · 목소리). 실패해도 스타일 카드는 남는다
    const c = req.body?.channel === false ? null : await h.run(PY, ["engine/research/ref_channel.py", vid, "--n", String(fast ? 2 : Math.max(2, Math.min(10, Number(req.body?.n) || 5))), ...(fast ? ["--whisper", "base"] : []), ...(force ? ["--fresh"] : [])], { cwd: ROOT, timeout: 40 * 60e3, onLine: (l) => { const m = /^@progress ([\d.]+) (.*)$/.exec(l); if (m) h.progress(0.8 + Number(m[1]) * 0.2, `채널 말투 · ${m[2]}`); } });
    const ch = c && c.code === 0 ? lastJson(c) : null;
    return { result: { url: `/api/public/trends/xray/${vid}/xray.json`, style: existsSync(path.join(dir, "style", "style.json")) ? `/api/public/trends/xray/${vid}/style/style.json` : null,
      channel: ch?.channel ? `/api/public/trends/channels/${ch.channel}/channel.json` : null } };
  } });
  res.status(202).json({ jobId: j.id });
}));
// 개체 추적 누끼 (engine/research/xray_track.py) — 분해한 쇼츠에서 찍은 개체 하나를 시간에 따라
app.get("/api/trends/xray/:vid/tracks", ah(async (req, res) => {
  const vid = req.params.vid; if (!isVid(vid)) throw bad("쇼츠 id 가 올바르지 않습니다");
  const dir = path.join(XRAY, vid, "track");
  const ids = existsSync(dir) ? await fs.readdir(dir) : [];
  const metas = (await Promise.all(ids.filter((t) => /^t\d+$/.test(t)).map((t) => fs.readFile(path.join(dir, t, "meta.json"), "utf8").then(JSON.parse).catch(() => null)))).filter(Boolean);
  const running = jobs.list({ type: "xray" }).filter((j) => !jobs.TERMINAL.has(j.status) && j.project === `track:${vid}`).map((j) => ({ jobId: j.id, progress: j.progress, stage: j.stage }));
  res.json({ tracks: metas.sort((a, b) => (a.at < b.at ? 1 : -1)), running });
}));
// 점 목록 [[x,y],…] (0~1) → "x,y;x,y"
const ptsArg = (v) => (Array.isArray(v) ? v : []).slice(0, 12).map((p) => { const x = Number(p?.[0]), y = Number(p?.[1]); if (!(x >= 0 && x <= 1 && y >= 0 && y <= 1)) throw bad("점 위치가 올바르지 않습니다"); return `${x.toFixed(4)},${y.toFixed(4)}`; }).join(";");
const trackPoint = (b) => {
  const num = (v, lo, hi) => { const n = Number(v); if (!Number.isFinite(n) || n < lo || n > hi) throw bad("추적 위치가 올바르지 않습니다"); return n; };
  return { t: num(b?.t, 0, 600), x: num(b?.x, 0, 1), y: num(b?.y, 0, 1), pos: ptsArg(b?.pos), neg: ptsArg(b?.neg) };
};
const trackArgs = ({ t, x, y, pos, neg }) => ["--t", String(t), "--x", String(x), "--y", String(y), ...(pos ? ["--pos", pos] : []), ...(neg ? ["--neg", neg] : [])];
// 한 프레임 미리보기 — 찍은 점(포함 · 빼기)으로 잘린 모양을 먼저 보여 주고, 맞으면 추적 시작
app.post("/api/trends/xray/:vid/segment", ah(async (req, res) => {
  const vid = req.params.vid; if (!isVid(vid)) throw bad("쇼츠 id 가 올바르지 않습니다");
  if (!existsSync(path.join(XRAY, vid, "src.mp4"))) throw bad("먼저 분해해야 합니다");
  const pt = trackPoint(req.body);
  await fs.mkdir(path.join(XRAY, vid, "track"), { recursive: true });
  const out = path.join(XRAY, vid, "track", "_preview.png");
  const r = await py(["engine/research/xray_track.py", vid, ...trackArgs(pt), "--preview", out], { timeout: 60e3 });
  if (r.code !== 0) throw new HttpError(422, "segment_failed", tail(r.err || r.out).split("\n").pop() || "개체를 찾지 못했습니다");
  res.json({ ok: true, url: `/api/public/trends/xray/${vid}/track/_preview.png?v=${Date.now()}` });
}));
app.post("/api/trends/xray/:vid/track", ah(async (req, res) => {
  const vid = req.params.vid; if (!isVid(vid)) throw bad("쇼츠 id 가 올바르지 않습니다");
  if (!existsSync(path.join(XRAY, vid, "src.mp4"))) throw bad("먼저 분해해야 합니다");
  const pt = trackPoint(req.body); const { t, x, y } = pt;
  const j = jobs.create({ type: "xray", project: `track:${vid}`, key: `track:${vid}:${t.toFixed(2)}:${x.toFixed(3)}:${y.toFixed(3)}:${pt.pos}:${pt.neg}`, label: "개체 추적 누끼", work: async (h) => {
    const r = await h.run(PY, ["engine/research/xray_track.py", vid, ...trackArgs(pt)], { cwd: ROOT, onLine: (l) => { const m = /^@progress ([\d.]+) (.*)$/.exec(l); if (m) h.progress(Number(m[1]), m[2]); } });
    if (r.timedOut || r.canceled) return r;
    return r.code === 0 ? {} : { error: "개체를 따라가지 못했습니다", detail: tail(r.err || r.out) };
  } });
  res.status(202).json({ jobId: j.id });
}));
app.delete("/api/trends/xray/:vid/track/:tid", ah(async (req, res) => {
  const { vid, tid } = req.params; if (!isVid(vid) || !/^t\d+$/.test(tid)) throw bad("추적 id 가 올바르지 않습니다");
  await fs.rm(path.join(XRAY, vid, "track", tid), { recursive: true, force: true });
  res.json({ ok: true });
}));
app.delete("/api/trends/xray/:vid", ah(async (req, res) => {
  const vid = req.params.vid; if (!isVid(vid)) throw bad("쇼츠 id 가 올바르지 않습니다");
  await fs.rm(path.join(XRAY, vid), { recursive: true, force: true });
  res.json({ ok: true });
}));
// 트렌드 요청 · 쇼츠 지우기 — index.json 은 trends.py 가 쓰므로 지우기도 스크립트로(동시에 써도 서로 덮지 않게)
app.delete("/api/trends/requests/:rid", ah(async (req, res) => {
  const rid = req.params.rid; if (!/^r\d{8}-\d{6}$/.test(rid)) throw bad("요청 id 가 올바르지 않습니다");
  const r = await py(["engine/research/trends.py", "remove", "--request", rid], { timeout: 30e3 });
  if (r.code !== 0) throw new HttpError(500, "trends_failed", "요청을 지우지 못했습니다", tail(r.err || r.out));
  res.json({ ok: true });
}));
app.delete("/api/trends/items/:vid", ah(async (req, res) => {
  const vid = req.params.vid; if (!isVid(vid)) throw bad("쇼츠 id 가 올바르지 않습니다");
  const r = await py(["engine/research/trends.py", "remove-item", "--id", vid], { timeout: 30e3 });
  if (r.code !== 0) throw new HttpError(500, "trends_failed", "쇼츠를 지우지 못했습니다", tail(r.err || r.out));
  await fs.rm(path.join(XRAY, vid), { recursive: true, force: true });   // 분해 결과도 함께
  res.json({ ok: true });
}));
// 판별(찜 · 보류 · 제외) — 트렌드 목록(index.json, 스크립트가 씀)과 따로 둔다: 동시에 써도 서로 덮지 않게
const PICKS = path.join(ROOT, "data", "workspace", "trend-picks.json");
const readPicks = async () => { try { return JSON.parse(await fs.readFile(PICKS, "utf8")); } catch { return {}; } };
let picksChain = Promise.resolve();
app.get("/api/trends/picks", ah(async (_req, res) => res.json(await readPicks())));
app.put("/api/trends/picks/:vid", ah(async (req, res) => {
  const vid = req.params.vid; if (!isVid(vid)) throw bad("쇼츠 id 가 올바르지 않습니다");
  const pick = req.body?.pick ?? null; const note = typeof req.body?.note === "string" ? req.body.note.slice(0, 500) : undefined;
  if (pick !== null && !["keep", "maybe", "skip"].includes(pick)) throw bad("판별 값이 올바르지 않습니다");
  const next = picksChain.then(async () => {
    const all = await readPicks();
    if (pick === null && !note) delete all[vid]; else all[vid] = { ...(all[vid] || {}), pick, ...(note !== undefined ? { note } : {}), at: Date.now() };
    await atomicWrite(PICKS, JSON.stringify(all, null, 1));
    return all[vid] ?? null;
  });
  picksChain = next.catch(() => {});
  res.json({ ok: true, pick: await next });
}));

// ---------- 제작 관문 (engine/checks/gate.py) — 의도 카드 확인 · 시안(장면 1~3) 승인. 최종 렌더 · 유료 생성 전에 필요 ----------
app.get("/api/projects/:id/gate", ah(async (req, res) => {
  const id = checkId(req.params.id);
  const r = await py(["engine/checks/gate.py", "status", id], { timeout: 30e3 });
  const v = lastJson(r); if (!v) throw new HttpError(500, "gate", tail(r.err || r.out)); res.json(v);
}));
app.post("/api/projects/:id/gate/:kind", ah(async (req, res) => {
  const id = checkId(req.params.id); const kind = req.params.kind;
  if (!["intent", "draft"].includes(kind)) throw bad("확인할 대상이 올바르지 않습니다");
  const r = await py(["engine/checks/gate.py", kind, id, "--by", "button"], { timeout: 30e3 });
  if (r.code !== 0) throw new HttpError(422, "gate", tail(r.err || r.out).split("\n").pop() || "확인하지 못했습니다");
  logEffort(ROOT, id, "approve", kind);
  res.json(lastJson(r) || { ok: true });   // 콘티 intent.confirmed 가 바뀌면 파일 감시가 화면에 알린다
}));

// ---------- Craft 앱 (ArtCraft 오픈소스 Photoshop · Illustrator · After Effects 류) ----------
const crafts = createCrafts(ROOT);
const craftName = (req) => { const c = crafts.get(String(req.params.name)); if (!c) throw notFound("없는 Craft 앱입니다"); return c; };
app.get("/api/crafts", (_req, res) => res.json(crafts.list()));
// 설치: 릴리스 받기 → SHA256 확인 → tools/crafts/<이름>/ (사용자가 설치 버튼을 눌렀을 때만)
app.post("/api/crafts/:name/install", ah(async (req, res) => {
  const c = craftName(req);
  const j = jobs.create({ type: "install", project: "_crafts", key: `craft:${c.name}`, label: `${c.title} 설치`, work: async (h) => {
    const r = await h.run(PY, ["engine/craft/crafts.py", "install", c.name, ...(req.body?.web === false ? ["--no-web"] : [])], { cwd: ROOT, onLine: (l) => { const m = /^@progress ([\d.]+) (.*)$/.exec(l); if (m) h.progress(Number(m[1]), m[2]); } });
    if (r.timedOut || r.canceled) return r;
    return r.code === 0 ? { result: { name: c.name } } : { error: `${c.title} 설치에 실패했습니다`, detail: tail(r.err || r.out) };
  } });
  res.status(202).json({ jobId: j.id });
}));
app.delete("/api/crafts/:name", ah(async (req, res) => {
  const c = craftName(req);
  await fs.rm(path.join(ROOT, "tools", "crafts", c.name), { recursive: true, force: true });
  res.json({ ok: true });
}));
// 에이전트에 붙이기 켜고 끄기
app.put("/api/crafts/:name", ah(async (req, res) => {
  const c = craftName(req);
  const f = path.join(ROOT, "data", "workspace", "settings.json");
  const cfg = (await readJson(f).catch(() => null)) ?? {};
  cfg.crafts = { ...(cfg.crafts ?? {}), [c.name]: !!req.body?.agent };
  await atomicWrite(f, JSON.stringify(cfg, null, 1));
  res.json({ ok: true });
}));
// 데스크톱 앱으로 열기(이 컴퓨터에서 창이 뜸). file 은 저장소 안 경로만
app.post("/api/crafts/:name/open", ah(async (req, res) => {
  const c = craftName(req);
  const bin = crafts.desktop(c.name); if (!bin || !existsSync(bin)) throw bad("먼저 설치해 주세요");
  const file = req.body?.file ? within(ROOT, String(req.body.file)) : null;
  const { spawn } = await import("node:child_process");
  const ch = spawn(bin, file ? [file] : [], { cwd: ROOT, detached: true, stdio: "ignore" });
  ch.on("error", () => {}); ch.unref();
  res.json({ ok: true });
}));
// 이 영상의 Craft 파일 — 단계(움직임 · 소리 · 컷 편집)와 장면 재료마다 '만든 앱 + 편집 파일'. 편집기의 'Craft 로 열기' 목록
app.get("/api/projects/:id/crafts", ah(async (req, res) => {
  const id = checkId(req.params.id);
  const base = path.join(ROOT, "data", "compositions", id, "craft");
  // 미리보기 = FilmCraft: 편집 프로젝트가 늘 있게(렌더 전이면 시퀀스 + 나레이션, 다른 엔진 렌더면 그 결과로 — 이미 최신이면 그대로)
  if (crafts.desktop("filmcraft") && existsSync(sbPath(id))) {
    await run(PY, ["-c", "import sys; sys.path.insert(0, 'engine'); import paths; from craft.edit import ensure; ensure(sys.argv[1])", id], { cwd: ROOT, timeout: 120_000 });
  }
  const man = await readJson(path.join(base, "craft.json"), {});
  const sha = async (f) => { try { return createHash("sha1").update(await fs.readFile(path.join(ROOT, f))).digest("hex"); } catch { return null; } };
  const inst = (app) => !!(app && crafts.desktop(app) && existsSync(crafts.desktop(app)));
  const stages = [];
  for (const [stage, m] of Object.entries(man)) {
    if (!m?.file || !existsSync(path.join(ROOT, m.file))) continue;
    const h = await sha(m.file);
    stages.push({ stage, app: m.app, file: m.file, edited: !!(m.hash && h && h !== m.hash), installed: inst(m.app) });
  }
  const materials = [];
  const mdir = path.join(base, "materials");
  for (const sd of (existsSync(mdir) ? (await fs.readdir(mdir)).sort() : [])) {
    for (const f of (await fs.readdir(path.join(mdir, sd))).sort()) {
      if (!f.endsWith(".json")) continue;
      const r = await readJson(path.join(mdir, sd, f), null);
      if (!r || typeof r !== "object" || Array.isArray(r) || !r.type || !r.key) continue;
      // 고칠 파일: 편집 파일(.vectorcraft) > 원본(사용자 · 에이전트가 넣은 파일) > 만든 결과
      const app = String(r.app || "").split("+")[0] || null;
      const file = r.editable || r.spec?.csv || r.spec?.xlsx || r.spec?.pdf || r.spec?.src || r.file;
      materials.push({ scene: r.scene, id: r.id, type: r.type, app, file, srcFile: r.spec?.src ?? null, installed: inst(app) });
    }
  }
  // 자산: 장면 재료를 파일 하나로 모은다(같은 그림이 여러 장면에 쓰여도 하나) — 편집 툴은 확장자로
  const assets = new Map();
  for (const m of materials) {
    const src = m.type === "illustration" ? null : m.file;
    const key = m.type === "illustration" ? `m:${m.scene}/${m.id}` : src && `a:${src}`;
    if (!key) continue;
    const id = m.type === "illustration" ? (m.srcFile || m.file) : src;
    const a = assets.get(id) ?? { stage: key, type: m.type, app: m.type === "illustration" ? "vectorcraft" : assetApp(src), file: id, scenes: [] };
    a.scenes.push(m.scene); assets.set(id, a);
  }
  // 올린 사진도 사진 자산으로(PhotoCraft 에서 바로 손봄)
  const up = path.join(ROOT, "data", "public", "uploads", id);
  for (const n of existsSync(up) ? (await fs.readdir(up)).sort() : []) {
    const f = path.join("public", "uploads", id, n);
    if (assetApp(n) === "photocraft" && !assets.has(f)) assets.set(f, { stage: `a:${f}`, type: "photo", app: "photocraft", file: f, scenes: [] });
  }
  // 소리 세션의 트랙(나레이션 · 음악 · 효과음)
  const au = stages.find((x) => x.stage === "audio");
  if (au) { const d = await readJson(path.join(ROOT, au.file), {}); au.tracks = (d.tracks ?? []).filter((t) => t.kind !== "Master").map((t) => t.name); }
  const mo = stages.find((x) => x.stage === "motion");
  if (mo) { const d = await readJson(path.join(ROOT, mo.file), {}); mo.comps = Object.values(d.items ?? {}).filter((it) => (it?.kind?.type ?? it?.kind) === "Composition" || (it?.kind?.type ?? "").toLowerCase() === "comp").map((it) => it.name).filter((n) => /^S\d/.test(n ?? "")).length; }
  res.json({ stages, materials, assets: [...assets.values()].filter((a) => a.app) });
}));
// Craft 작업 공간 — 편집기 안에 Craft 웹 빌드를 띄우고, 이 영상의 프로젝트를 넣고(열기), 저장을 받아 프로젝트 파일에 쓴다.
// 브라우저 안의 앱은 디스크 경로를 못 읽으므로, 프로젝트 안의 미디어 경로를 '/files/<고유 이름>' 으로 바꿔 넘기고 저장 때 되돌린다
const WEB_FILES = "/files/";
// 웹 빌드가 프로젝트를 묶음(zip: 프로젝트 + 프로젝트 기준 상대 경로의 미디어)으로 주고받는 앱
const WEB_BUNDLE = { soundcraft: ".scraftz" };
// 파일 하나를 그 형식의 Craft 앱으로 편집(사진 · 표 · 문서 · 벡터) — 앱 고유 형식으로 저장하면 명령행으로 원래 형식으로 되돌린다
const ASSET_APP = { ".png": "photocraft", ".jpg": "photocraft", ".jpeg": "photocraft", ".webp": "photocraft", ".csv": "gridcraft", ".xlsx": "gridcraft", ".pdf": "pdfcraft", ".svg": "vectorcraft" };
const NATIVE = { photocraft: ".pcraft", gridcraft: ".xlsx", vectorcraft: ".vectorcraft" };
const assetApp = (f) => (f ? ASSET_APP[path.extname(f).toLowerCase()] ?? null : null);
const studioTarget = async (id, stage) => {
  const base = path.join(ROOT, "data", "compositions", id, "craft");
  if (stage.startsWith("a:")) {
    const file = within(ROOT, stage.slice(2));
    const rel = path.relative(ROOT, file).split(path.sep);
    if (!((rel[0] === "compositions" && rel[1] === id) || rel[0] === "public") || !existsSync(file)) throw notFound("파일이 없습니다");
    const app = assetApp(file); if (!app) throw bad("이 형식을 편집할 Craft 앱이 없습니다");
    return { app, file, asset: true };
  }
  if (stage.startsWith("m:")) {                       // 장면 재료: m:<장면>/<재료 id> (VectorCraft 편집 파일)
    const [sc, mid] = stage.slice(2).split("/");
    if (!/^\d+$/.test(sc) || !/^[\w.-]+$/.test(mid ?? "")) throw bad("잘못된 재료입니다");
    const rec = await readJson(path.join(base, "materials", `s${sc.padStart(2, "0")}`, `${mid}.json`), null);
    if (!rec?.editable) throw notFound("이 재료는 Craft 편집 파일이 없습니다");
    return { app: rec.app?.split("+")[0] ?? "vectorcraft", file: within(ROOT, rec.editable) };
  }
  const m = (await readJson(path.join(base, "craft.json"), {}))[stage];
  if (!m?.file) throw notFound("이 단계의 Craft 프로젝트가 아직 없습니다(Craft 엔진으로 한 번 렌더하면 생깁니다)");
  return { app: m.app, file: within(ROOT, m.file) };
};
// 프로젝트 JSON 안에서 실제 파일을 가리키는 문자열(절대 경로 · 프로젝트 기준 상대 경로) → 고유 이름
const mediaMap = (text, projFile) => {
  const map = new Map(), used = new Set();
  for (const m of text.matchAll(/"((?:\/|\.\.?\/|[\w ().-]+\/)[^"\n]{1,400}?\.[A-Za-z0-9]{2,5})"/g)) {
    const ref = JSON.parse(`"${m[1]}"`);
    if (map.has(ref)) continue;
    const abs = path.isAbsolute(ref) ? ref : path.resolve(path.dirname(projFile), ref);
    if (!abs.startsWith(ROOT + path.sep) || !existsSync(abs)) continue;
    let name = path.basename(abs), k = 1;
    while (used.has(name)) name = `${k++}-${path.basename(abs)}`;
    used.add(name); map.set(ref, { name, abs });
  }
  return map;
};
const swapRefs = (text, pairs) => text.replace(/"((?:[^"\\]|\\.)*)"/g, (all, inner) => { try { const v = JSON.parse(all); return pairs.has(v) ? JSON.stringify(pairs.get(v)) : all; } catch { return all; } });
app.get("/api/projects/:id/studio/:stage", ah(async (req, res) => {
  const id = checkId(req.params.id), stage = String(req.params.stage);
  const { app: craft, file, asset } = await studioTarget(id, stage);
  if (asset) {
    const buf = await fs.readFile(file);
    return res.json({ app: craft, web: !!crafts.webDir(craft), project: { name: path.basename(file), hash: createHash("sha1").update(buf).digest("hex"), accept: [path.extname(file).toLowerCase(), NATIVE[craft]].filter(Boolean) }, media: [] });
  }
  const text = await fs.readFile(file, "utf8");
  const h = createHash("sha1").update(text).digest("hex");
  const bx = WEB_BUNDLE[craft];
  if (bx) return res.json({ app: craft, web: !!crafts.webDir(craft), project: { name: path.basename(file).replace(/\.[^.]+$/, bx), hash: h, accept: [path.extname(file), bx] }, media: [] });
  const map = mediaMap(text, file);
  res.json({ app: craft, web: !!crafts.webDir(craft), project: { name: path.basename(file), hash: h, accept: [path.extname(file)] },
    media: [...map.values()].map((v) => ({ name: v.name, url: `/api/projects/${id}/studio-file?p=${encodeURIComponent(path.relative(ROOT, v.abs))}` })) });
}));
app.get("/api/projects/:id/studio/:stage/project", ah(async (req, res) => {
  const id = checkId(req.params.id);
  const { app: craft, file, asset } = await studioTarget(id, String(req.params.stage));
  if (asset) return res.sendFile(file);
  const text = await fs.readFile(file, "utf8");
  if (WEB_BUNDLE[craft]) {          // 묶음: 프로젝트 + 상대 경로 미디어를 그 경로 그대로
    const rel = [...mediaMap(text, file)].filter(([ref]) => !path.isAbsolute(ref));
    const entries = [{ name: path.basename(file), data: Buffer.from(text) }, ...await Promise.all(rel.map(async ([ref, v]) => ({ name: ref.replace(/^\.\//, ""), data: await fs.readFile(v.abs) })))];
    return res.type("application/zip").send(zip(entries));
  }
  const pairs = new Map([...mediaMap(text, file)].map(([ref, v]) => [ref, WEB_FILES + v.name]));
  res.type("application/json").send(swapRefs(text, pairs));
}));
app.get("/api/projects/:id/studio-file", ah(async (req, res) => {
  const id = checkId(req.params.id, { allowSystem: true });
  // 작업물은 data/ 아래 — 'data/out/x' · 'out/x' · 절대 경로 모두 받는다(예전엔 data/ 앞을 몰라 채팅 안 그림 · 영상이 전부 '없음'이었다)
  let q = String(req.query.p ?? "").replace(/\\/g, "/").replace(/^\.?\//, "");
  if (!q.startsWith("data/") && /^(compositions|workspace|public|out|audio)\//.test(q)) q = `data/${q}`;
  const abs = within(ROOT, q);
  const rel = path.relative(path.join(ROOT, "data"), abs).split(path.sep);
  const mine = (n) => typeof n === "string" && (n === id || n.startsWith(id) || n.includes(`-${id}`) || n.includes(`${id}.`));
  // 이 영상의 파일만(제작 파일 · 작업 폴더 · 공개 재료 · 렌더 결과 · 음성 · 시안) — 채팅 안 결과 보기도 이것을 쓴다
  // workspace/asset-cache: 여러 영상이 같이 쓰는 무료 자료 저장(스톡 · 짤 · 레퍼런스 받기) — 개인 파일이 아니라 열어 준다(2026-11-09: 대화창 스톡 영상이 404 → 'No video with supported format')
  const ok = !rel[0]?.startsWith("..") && ((rel[0] === "compositions" && rel[1] === id) || (rel[0] === "workspace" && (mine(rel[2]) || rel[1] === "asset-cache")) || rel[0] === "public"
    || ((rel[0] === "out" || rel[0] === "audio") && rel.length === 2 && mine(rel[1])));
  if (!ok || !existsSync(abs)) throw notFound("파일이 없습니다");
  res.sendFile(abs, { headers: { "Cache-Control": "no-cache" } });   // 같은 이름으로 다시 그린 시안 — 늘 새로 확인(바뀌지 않았으면 304)
}));
app.post("/api/projects/:id/studio/:stage/save", express.raw({ type: "*/*", limit: "500mb" }), ah(async (req, res) => {
  const id = checkId(req.params.id);
  const { app: craft, file, asset } = await studioTarget(id, String(req.params.stage));
  const body = Buffer.isBuffer(req.body) ? req.body : Buffer.from(String(req.body ?? ""));
  if (asset) {
    await fs.copyFile(file, `${file}.bak`).catch(() => {});
    const name = String(req.query.name ?? "").toLowerCase();
    const nat = NATIVE[craft];
    if (nat && name.endsWith(nat) && !file.toLowerCase().endsWith(nat)) {
      // 앱 고유 형식(.pcraft · .xlsx · .vectorcraft)으로 저장됨 → 옆에 두고 원래 형식으로 변환
      const side = `${file}${nat}`;
      await atomicWrite(side, body);
      const cli = path.join(ROOT, JSON.parse(readFileSync(path.join(ROOT, "tools", "crafts", craft, "installed.json"), "utf8")).cli);
      const r = await run(cli, ["convert", side, file], { cwd: path.dirname(file) });
      if (r.code !== 0) throw bad(`변환하지 못했습니다: ${tail(r.err || r.out)}`);
    } else await atomicWrite(file, body);
    return res.json({ ok: true, file: path.relative(ROOT, file) });
  }
  let text;
  if (body.subarray(0, 2).toString() === "PK") {   // 묶음: 프로젝트 파일 + 미디어(프로젝트 폴더 안에만 쓴다)
    const dir = path.dirname(file), ext = path.extname(file);
    const ents = unzip(body);
    const pj = ents.find((e) => e.name.toLowerCase().endsWith(ext) && !e.name.includes("/"));
    if (!pj) throw bad("묶음에 프로젝트 파일이 없습니다");
    for (const e of ents) {
      if (e === pj) continue;
      const out = within(dir, e.name);
      if (!existsSync(out) || createHash("sha1").update(await fs.readFile(out)).digest("hex") !== createHash("sha1").update(e.data).digest("hex")) await atomicWrite(out, e.data);
    }
    text = pj.data.toString("utf8");
  } else text = body.toString("utf8");
  try { JSON.parse(text); } catch { throw bad("Craft 가 보낸 프로젝트를 읽지 못했습니다"); }
  const cur = await fs.readFile(file, "utf8");
  const back = new Map([...mediaMap(cur, file)].map(([ref, v]) => [WEB_FILES + v.name, ref]));
  text = swapRefs(text, back);
  await fs.copyFile(file, `${file}.bak`).catch(() => {});
  await atomicWrite(file, text);
  // 그림(장면 재료): 원본 SVG 로도 되돌려 쓴다 → 이 그림을 쓰는 모든 장면이 함께 바뀐다
  if (String(req.params.stage).startsWith("m:") && craft === "vectorcraft") {
    const rec = await readJson(file.replace(/\.vectorcraft$/, ".json"), null);
    const src = rec?.spec?.src && within(ROOT, rec.spec.src);
    if (src && src.endsWith(".svg")) {
      const cli = path.join(ROOT, JSON.parse(readFileSync(path.join(ROOT, "tools", "crafts", "vectorcraft", "installed.json"), "utf8")).cli);
      await fs.copyFile(src, `${src}.bak`).catch(() => {});
      const r = await run(cli, ["convert", file, src], { cwd: path.dirname(file) });
      if (r.code !== 0) throw bad(`원본 SVG 로 되돌리지 못했습니다: ${tail(r.err || r.out)}`);
    }
  }
  res.json({ ok: true, file: path.relative(ROOT, file) });
}));
// 결과물 보기 — 편집기 가운데는 편집 툴 화면이 아니라 고른 항목의 결과만 보여 준다(수정은 에이전트가 Craft 프로젝트를 고쳐서).
// → { kind: video|audio|image|table|pdf|none, url?, rows?, note?, updated? }
const fileUrl = (id, abs) => `/api/projects/${id}/studio-file?p=${encodeURIComponent(path.relative(ROOT, abs))}&v=${Math.round(statSync(abs).mtimeMs)}`;
app.get("/api/projects/:id/result/:stage", ah(async (req, res) => {
  const id = checkId(req.params.id), stage = String(req.params.stage);
  const newest = (files) => files.filter((f) => existsSync(f)).sort((a, b) => statSync(b).mtimeMs - statSync(a).mtimeMs)[0];
  const at = (f) => ({ updated: Math.round(statSync(f).mtimeMs) });
  if (stage === "edit") {
    const outs = existsSync(OUT) ? (await fs.readdir(OUT)).filter((n) => n.startsWith(id) && n.endsWith(".mp4")).map((n) => path.join(OUT, n)) : [];
    const f = newest(outs);
    return res.json(f ? { kind: "video", url: `/api/out/${encodeURIComponent(path.basename(f))}?v=${Math.round(statSync(f).mtimeMs)}`, name: path.basename(f), ...at(f) } : { kind: "none", note: "아직 렌더한 영상이 없어요 — 에이전트에게 '초안 만들어 줘'라고 하세요" });
  }
  if (stage === "audio.voice" || stage === "audio.sfx") {   // 소리 › 나레이션 · 효과음: 따로 남긴 파일(음성 단계)
    const f = path.join(ROOT, "data", "public", "audio", `${id}.${stage.slice(6)}.wav`);
    if (!existsSync(f)) return res.json({ kind: "none", note: "아직 따로 나뉜 소리 파일이 없어요 — 음성을 다시 만들면 생깁니다" });
    const marks = stage === "audio.sfx" ? await readJson(path.join(ROOT, "data", "public", "audio", `${id}.sfx.json`), []) : undefined;
    return res.json({ kind: "audio", url: fileUrl(id, f), name: path.basename(f), marks, ...at(f) });
  }
  if (stage === "audio") {
    const f = newest([path.join(ROOT, "data", "compositions", id, "craft", "audio", `${id}.mix.wav`), path.join(ROOT, "data", "audio", `${id}.wav`)]);
    return res.json(f ? { kind: "audio", url: fileUrl(id, f), name: path.basename(f), ...at(f) } : { kind: "none", note: "아직 나레이션이 없어요" });
  }
  if (stage === "motion") {
    const dir = path.join(ROOT, "data", "workspace", "render", id, "craft");
    const cands = existsSync(dir) ? (await fs.readdir(dir)).map((d) => path.join(dir, d, "silent.mp4")) : [];
    const f = newest(cands);
    return res.json(f ? { kind: "video", url: fileUrl(id, f), name: "그래픽(소리 없음)", ...at(f) } : { kind: "none", note: "아직 그래픽을 렌더하지 않았어요" });
  }
  const { file } = await studioTarget(id, stage);
  const ext = path.extname(file).toLowerCase();
  if (stage.startsWith("m:")) {          // 그림 재료: 렌더한 PNG(원본 SVG 가 바뀌었으면 다음 렌더에 반영)
    const png = file.replace(/\.vectorcraft$/, ".png");
    if (existsSync(png)) return res.json({ kind: "image", url: fileUrl(id, png), name: path.basename(png), ...at(png) });
  }
  if ([".png", ".jpg", ".jpeg", ".webp", ".svg"].includes(ext)) return res.json({ kind: "image", url: fileUrl(id, file), name: path.basename(file), ...at(file) });
  if (ext === ".pdf") return res.json({ kind: "pdf", url: fileUrl(id, file), name: path.basename(file), ...at(file) });
  if (ext === ".csv") {
    const rows = (await fs.readFile(file, "utf8")).trim().split(/\r?\n/).slice(0, 200).map((l) => l.split(","));
    return res.json({ kind: "table", rows, name: path.basename(file), ...at(file) });
  }
  res.json({ kind: "none", note: "미리 볼 수 없는 형식이에요" });
}));
// ---------- YouTube 연결 · 업로드 · 통계 (공식 API, 토큰은 ~/.shortsforge/youtube.json — 화면 · 에이전트로 보내지 않음) ----------
const yt = createYoutube();
app.get("/api/youtube", (_req, res) => res.json(yt.status()));
app.put("/api/youtube/client", ah(async (req, res) => {
  const { client_id, client_secret } = req.body || {};
  if (!/\.apps\.googleusercontent\.com$/.test(String(client_id || "").trim()) || !String(client_secret || "").trim()) throw bad("Google Cloud 의 OAuth 클라이언트 ID(…apps.googleusercontent.com)와 비밀을 넣어 주세요");
  yt.setClient(client_id, client_secret); res.json(yt.status());
}));
app.get("/api/youtube/auth", ah(async (req, res) => {
  const back = String(req.query.back || "http://localhost:4311/settings/youtube");
  if (!/^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?\//.test(back)) throw bad("돌아갈 주소가 이 컴퓨터가 아닙니다");
  try { res.redirect(yt.authUrl(back)); } catch (e) { throw bad(String(e.message || e)); }
}));
app.get("/api/youtube/callback", ah(async (req, res) => {
  if (req.query.error) return res.redirect(`http://localhost:4311/settings/youtube?error=${encodeURIComponent(String(req.query.error))}`);
  try { const back = await yt.callback(String(req.query.code || ""), String(req.query.state || "")); res.redirect(`${back}${back.includes("?") ? "&" : "?"}connected=1`); }
  catch (e) { res.redirect(`http://localhost:4311/settings/youtube?error=${encodeURIComponent(String(e.message || e))}`); }
}));
app.delete("/api/youtube", ah(async (_req, res) => { await yt.disconnect(); res.json(yt.status()); }));
app.get("/api/youtube/avatar", ah(async (_req, res) => {
  const f = await yt.avatar(path.join(ROOT, "data", "workspace", "cache"));
  if (!f) throw notFound("채널 아이콘이 없습니다");
  res.set("Cache-Control", "max-age=86400").sendFile(f);
}));
app.post("/api/youtube/refresh", ah(async (_req, res) => { await yt.refreshChannel(); res.json(yt.status()); }));
// 채널의 영상 목록 · 아무 영상의 통계(Fluma 밖에서 올린 것도) · 콘티와 연결
const ytErr = (e) => { throw Object.assign(new HttpError(e.status === 409 || e.status === 401 ? 409 : 502, "youtube", String(e.message || e))); };
app.get("/api/youtube/videos", ah(async (_req, res) => { try { res.json(await yt.videos()); } catch (e) { ytErr(e); } }));
app.get("/api/youtube/videos/:vid/stats", ah(async (req, res) => {
  const vid = String(req.params.vid); if (!/^[\w-]{6,20}$/.test(vid)) throw bad("잘못된 영상 id");
  const cache = path.join(ROOT, "data", "workspace", "cache", `yt-stats-${vid}.json`);
  const old = await readJson(cache, null);
  if (old && !req.query.fresh && Date.now() - Date.parse(old.at) < 10 * 60_000) return res.json(old);
  let out;
  // 시작일 = 게시일(모르면 채널 목록에서 찾는다) — 2005년부터 하루씩 받지 않게
  let since = String(req.query.since || "");
  if (!since) since = ((await yt.videos().catch(() => [])).find((x) => x.videoId === vid)?.published || new Date(Date.now() - 90 * 864e5).toISOString()).slice(0, 10);
  try { out = { ...(await yt.stats(vid, since)), scenes: [] }; } catch (e) { ytErr(e); }
  out.record = { videoId: vid, url: `https://youtube.com/shorts/${vid}`, uploaded_at: out.live?.snippet?.publishedAt ?? null, privacy: out.live?.status?.privacyStatus ?? "", title: out.live?.snippet?.title ?? vid, file: "" };
  await atomicWrite(cache, JSON.stringify(out));
  res.json(out);
}));
app.post("/api/projects/:id/youtube/link", ah(async (req, res) => {
  const id = checkId(req.params.id); if (!existsSync(sbPath(id))) throw notFound("콘티가 없습니다");
  const vid = String(req.body?.videoId || ""); if (!/^[\w-]{6,20}$/.test(vid)) throw bad("잘못된 영상 id");
  const v = (await yt.videos().catch(ytErr)).find((x) => x.videoId === vid);
  if (!v) throw notFound("내 채널에서 그 영상을 찾지 못했어요");
  const rec = { videoId: vid, url: `https://youtube.com/shorts/${vid}`, uploaded_at: v.published, privacy: v.privacy, title: v.title, file: "", linked: true };
  await atomicWrite(ytRec(id), JSON.stringify(rec, null, 1));
  res.json(rec);
}));

const ytRec = (id) => path.join(ROOT, "data", "compositions", id, "youtube.json");
/** 올릴 파일: 최종 렌더(가장 새 것), 없으면 초안 */
const uploadFile = async (id) => {
  const outs = existsSync(OUT) ? (await fs.readdir(OUT)).filter((n) => n.startsWith(id) && n.endsWith(".mp4")).map((n) => path.join(OUT, n)) : [];
  const by = (xs) => xs.sort((a, b) => statSync(b).mtimeMs - statSync(a).mtimeMs)[0];
  const tail = (f) => path.basename(f).slice(id.length);   // 영상 id 뒤만 본다(id 자체에 -s0… 같은 글자가 있을 수 있음)
  return by(outs.filter((f) => !/-draft|-s\d+(-\d+)?(-|\.)/.test(tail(f)))) || by(outs.filter((f) => !/-s\d+(-\d+)?(-|\.)/.test(tail(f)))) || null;
};
app.get("/api/projects/:id/youtube", ah(async (req, res) => {
  const id = checkId(req.params.id);
  const f = await uploadFile(id);
  res.json({ ...yt.status(), record: await readJson(ytRec(id), null), file: f ? { name: path.basename(f), draft: /-draft/.test(path.basename(f).slice(id.length)), size: statSync(f).size } : null });
}));
app.post("/api/projects/:id/youtube/upload", ah(async (req, res) => {
  const id = checkId(req.params.id); if (!existsSync(sbPath(id))) throw notFound("콘티가 없습니다");
  const f = await uploadFile(id); if (!f) throw bad("올릴 영상이 없어요 — 먼저 렌더해 주세요");
  if (!yt.status().connected) throw conflict("YouTube 계정이 연결되지 않았어요 — 설정 → YouTube");
  const sb = await readJson(sbPath(id), {});
  const b = req.body || {};
  const meta = { title: String(b.title || sb.title || id), description: String(b.description || ""), tags: Array.isArray(b.tags) ? b.tags.map(String).slice(0, 15) : [],
    privacy: ["private", "unlisted", "public"].includes(b.privacy) ? b.privacy : "private", synthetic: !!b.synthetic, language: sb.language || "ko" };
  const j = jobs.create({ type: "upload", project: id, key: `upload:${id}`, label: "YouTube 업로드", work: async (h) => {
    h.progress(0, "업로드 시작");
    const videoId = await yt.upload(f, meta, (p) => h.progress(p, `올리는 중 ${Math.round(p * 100)}%`));
    const rec = { videoId, url: `https://youtube.com/shorts/${videoId}`, uploaded_at: new Date().toISOString(), privacy: meta.privacy, title: meta.title, file: path.basename(f) };
    await atomicWrite(ytRec(id), JSON.stringify(rec, null, 1));
    return { result: rec };
  } });
  res.status(202).json({ jobId: j.id });
}));
// 통계 + 장면 매핑: 이탈 곡선(전체 길이 대비 비율 100칸)을 콘티 장면 시간에 겹쳐, 장면마다 남은 비율 · 그 장면에서 떨어진 폭을 낸다
app.get("/api/projects/:id/youtube/stats", ah(async (req, res) => {
  const id = checkId(req.params.id);
  const rec = await readJson(ytRec(id), null);
  if (!rec?.videoId) return res.json({ none: true });
  const cache = path.join(ROOT, "data", "compositions", id, "youtube.stats.json");
  const old = await readJson(cache, null);
  if (old && !req.query.fresh && Date.now() - Date.parse(old.at) < 10 * 60_000) return res.json(old);
  const st = await yt.stats(rec.videoId, rec.uploaded_at);
  const sb = await readJson(sbPath(id), { scenes: [] });
  const total = (sb.scenes || []).reduce((a, x) => a + (x.sec || 0), 0) || 1;
  let t = 0;
  const bounds = (sb.scenes || []).map((x, i) => { const a = t / total; t += x.sec || 0; return { i, role: x.role, caption: x.caption, narration: x.narration, from: a, to: t / total }; });
  const pts = (st.retention.rows || []).map((r) => ({ x: Number(r[0]), y: Number(r[1]), rel: Number(r[2]) }));
  const at = (x) => { if (!pts.length) return null; let best = pts[0]; for (const p of pts) if (Math.abs(p.x - x) < Math.abs(best.x - x)) best = p; return best.y; };
  const scenes = bounds.map((b) => { const y0 = at(b.from), y1 = at(b.to); return { ...b, start: y0, end: y1, drop: y0 != null && y1 != null ? Math.max(0, y0 - y1) : null }; });
  const out = { ...st, record: rec, scenes, duration: total };
  await atomicWrite(cache, JSON.stringify(out));
  res.json(out);
}));

// 브라우저 빌드(WebAssembly) — 같은 출처에서 열어 Fluma 화면 안에 띄운다. 스레드용 교차 출처 격리 헤더를 붙임
app.use("/api/crafts-web/:name", (req, res, next) => {
  const dir = crafts.get(req.params.name) && crafts.webDir(req.params.name);
  if (!dir || !existsSync(dir)) return sendError(res, 404, "not_installed", "브라우저 빌드가 설치되지 않았습니다");
  res.set({ "Cross-Origin-Opener-Policy": "same-origin", "Cross-Origin-Embedder-Policy": "require-corp", "Cross-Origin-Resource-Policy": "same-origin" });
  // 데모 프로젝트 대신 빈 화면으로 시작(Fluma 가 이 영상의 프로젝트를 넣는다)
  if (req.params.name === "effectcraft" && req.path === "/effectcraft-config.json") return res.set("Cache-Control", "no-cache").json({ startup: "empty" });
  express.static(dir)(req, res, next);
});

// ---------- MCP 서버 (에이전트가 쓸 외부 도구) — 비밀 값은 화면으로 보내지 않는다 ----------
app.get("/api/mcp", (_req, res) => res.json(publicMcp()));
app.put("/api/mcp/:name", ah(async (req, res) => {
  const name = req.params.name; if (!MCP_NAME.test(name)) throw bad("이름은 영문 소문자 · 숫자 · - _ (32자까지)");
  const d = loadMcp();
  try { d.servers[name] = mcpNormalize(req.body || {}, d.servers[name]); } catch (e) { throw bad(String(e.message || e)); }
  saveMcp(d);
  res.json({ ok: true, servers: publicMcp() });
}));
app.delete("/api/mcp/:name", ah(async (req, res) => {
  const d = loadMcp(); delete d.servers[req.params.name]; saveMcp(d);
  res.json({ ok: true, servers: publicMcp() });
}));
app.post("/api/mcp/:name/test", ah(async (req, res) => {
  if (!MCP_NAME.test(req.params.name)) throw bad("이름이 올바르지 않습니다");
  res.json(await testMcp(req.params.name, process.env));
}));

// ---------- 설치 (engine/core/install.py) — 작업으로 ----------
app.post("/api/install/:kind/:name", ah(async (req, res) => {
  const { kind, name } = req.params;
  if (!["engines", "voices"].includes(kind) || !/^[a-z0-9_-]+$/.test(name)) throw bad("설치할 대상이 올바르지 않습니다");
  const j = jobs.create({ type: "install", key: `install:${kind}:${name}`, label: `${name} 설치`, work: async (h) => {
    const r = await h.run(PY, ["engine/core/install.py", kind, name], { cwd: ROOT });
    invalidate(kind === "engines" ? "engines:avail" : "voices:avail");
    if (kind === "engines") engineAvail(); else cached("voices:avail", loadVoiceAvail);
    if (r.timedOut || r.canceled) return r;
    return r.code === 0 ? {} : { error: "설치하지 못했습니다", detail: tail(r.err || r.out) };
  } });
  res.status(202).json({ job: j.id, jobId: j.id });
}));
// 예전 화면 호환: { status: run|done|fail, lines, secs }
app.get("/api/install/jobs/:id", (req, res) => {
  const j = jobs.get(req.params.id); if (!j) return sendError(res, 404, "not_found", "작업이 없습니다");
  const status = j.status === "done" ? "done" : jobs.TERMINAL.has(j.status) ? "fail" : "run";
  const lines = j.events.filter((e) => e.payload.type === "log").slice(-60).map((e) => e.payload.line);
  if (j.error) lines.push(j.error);
  res.json({ status, lines, secs: Math.round(((j.ended || Date.now()) - (j.started || j.created)) / 1000) });
});
app.post("/api/registry/refresh", ah(async (_req, res) => {
  for (const k of ["engines:list", "engines:avail", "voices:avail", "memory"]) invalidate(k);
  engineList(); engineAvail(); cached("voices:avail", loadVoiceAvail, undefined, () => publish({ kind: "registry", name: "voices" }));
  memoryList(); refreshAgents().then(() => publish({ kind: "registry", name: "agents" }));
  res.status(202).json({ ok: true });
}));

// 룩 카탈로그 · 브랜드 키트는 2026-10-29 제거(ADR-0011) — 색은 영상마다 콘티 direction 이 정한다

// ---------- 스킬 (.claude/skills/<이름>/SKILL.md) ----------
const SKILLS = path.join(ROOT, ".claude", "skills");
function frontmatter(text) {
  const m = text.match(/^---\n([\s\S]*?)\n---/); const out = {};
  if (!m) return out;
  for (const line of m[1].split("\n")) { const kv = line.match(/^([A-Za-z_-]+):\s*(.*)$/); if (kv) out[kv[1]] = kv[2].replace(/^["']|["']$/g, ""); }
  return out;
}
app.get("/api/skills", ah(async (_req, res) => {
  if (!existsSync(SKILLS)) return res.json([]);
  const out = [];
  for (const name of (await fs.readdir(SKILLS)).sort()) {
    const p = path.join(SKILLS, name, "SKILL.md"); if (!existsSync(p)) continue;
    const fm = frontmatter(await fs.readFile(p, "utf8").catch(() => ""));
    out.push({ name: fm.name || name, description: fm.description || "", order: Number(fm.order || 99) });
  }
  out.sort((a, b) => a.order - b.order || a.name.localeCompare(b.name));
  res.json(out);
}));

// ---------- data/public/ 파일 목록 (프레임 폴더 · 썸네일은 뺌) ----------
async function listFiles(dir, base = "") {
  const out = [];
  if (!existsSync(dir)) return out;
  for (const e of await fs.readdir(dir, { withFileTypes: true })) {
    const rel = base ? `${base}/${e.name}` : e.name;
    const parts = rel.split("/");
    if (e.isDirectory()) {
      if (rel === "trends/thumbs") continue;
      if (parts[0] === "uploads" && parts.length >= 3) continue;   // 올린 영상의 프레임 폴더
      if (parts[0] === "elements" && parts.length >= 3) { if (existsSync(path.join(dir, e.name, "meta.json"))) out.push(`${rel}/meta.json`); continue; }
      out.push(...(await listFiles(path.join(dir, e.name), rel)));
    } else out.push(rel);
  }
  return out;
}
app.get("/api/static-files", ah(async (_req, res) => res.json(await listFiles(PUBLIC))));
// 트렌드를 아직 찾지 않은 첫 실행: 없는 파일이 아니라 빈 목록이다
app.get("/api/public/trends/index.json", (req, res, next) => { if (existsSync(path.join(PUBLIC, "trends", "index.json"))) return next(); res.json({ requests: [], items: [] }); });
app.use("/api/public", express.static(PUBLIC));

// ---------- 미리보기 빌드 · 초안 · 정지 화면 (작업 대기열 · 같은 영상은 차례로) ----------
async function waitOrThrow(j, req, res, code, message) {
  const done = await jobs.waitFor(j, req, res);
  if (done.status === "canceled") return null;
  if (done.status !== "done") throw new HttpError(500, code, done.error || message, done.detail);
  return done.result;
}
app.post("/api/projects/:id/build", ah(async (req, res) => {
  const id = checkId(req.params.id); if (!existsSync(sbPath(id))) throw notFound("콘티가 없습니다");
  const a = engArgs(req.body);
  const j = jobs.create({ type: "build", project: id, serial: true, key: `build:${id}:${a.join(",")}`, label: "미리보기 준비", work: async (h) => {
    const r = await h.run(PY, ["engine/render.py", `data/storyboards/${id}.json`, "--build", ...a], { cwd: ROOT });
    if (r.timedOut || r.canceled) return r;
    const last = r.out.trim().split("\n").pop() || "";
    if (r.code !== 0 || !last.endsWith("index.html")) return { error: "미리보기를 만들지 못했습니다", detail: tail(r.err || r.out) };
    const head = r.out.match(/\[엔진\] (\S+) · 템플릿 (\S+)/);
    const rel = path.relative(RENDER_WORK, last).split(path.sep).join("/");
    return { result: { engine: head?.[1], template: head?.[2], url: `/api/work/${rel}?v=${Date.now()}` } };
  } });
  const r = await waitOrThrow(j, req, res, "build_failed", "미리보기를 만들지 못했습니다"); if (!r) return;
  res.json({ ok: true, ...r });
}));
app.post("/api/projects/:id/draft", ah(async (req, res) => {
  const id = checkId(req.params.id); if (!existsSync(sbPath(id))) throw notFound("콘티가 없습니다");
  logEffort(ROOT, id, "render", "초안 렌더");
  const a = engArgs(req.body);
  const j = jobs.create({ type: "draft", project: id, key: `draft:${id}:${a.join(",")}`, label: "초안 렌더", work: async (h) => {
    const r = await h.run(PY, ["engine/render.py", `data/storyboards/${id}.json`, "--draft", ...a], { cwd: ROOT });
    if (r.timedOut || r.canceled) return r;
    const last = renderedFile(r);
    if (r.code !== 0 || !last) return { error: "초안을 렌더하지 못했습니다", detail: resultBlock(r.out)?.error || tail(r.err || r.out) };
    return { result: { url: `/api/out/${path.basename(last)}?v=${Date.now()}` } };
  } });
  const r = await waitOrThrow(j, req, res, "draft_failed", "초안을 렌더하지 못했습니다"); if (!r) return;
  res.json({ ok: true, ...r });
}));
app.use("/api/work", express.static(RENDER_WORK));

const STILLS = path.join(ROOT, "data", "workspace", "stills");
app.post("/api/projects/:id/still", ah(async (req, res) => {
  const id = checkId(req.params.id); if (!existsSync(sbPath(id))) throw notFound("콘티가 없습니다");
  const { seconds = [0] } = req.body || {};
  const secs = (Array.isArray(seconds) ? seconds : [seconds]).map((x) => Math.max(0, Number(x) || 0)).slice(0, 12);
  const a = engArgs(req.body);
  const j = jobs.create({ type: "still", project: id, serial: true, key: `still:${id}:${a.join(",")}:${secs.join(",")}`, label: "정지 화면", work: async (h) => {
    const r = await h.run(PY, ["engine/core/still.py", `data/storyboards/${id}.json`, ...secs.map(String), ...a], { cwd: ROOT });
    if (r.timedOut || r.canceled) return r;
    const paths = r.out.trim().split("\n").filter((l) => l.endsWith(".png"));
    if (r.code !== 0 || !paths.length) return { error: "정지 화면을 찍지 못했습니다", detail: tail(r.err || r.out) };
    const v = Date.now();
    return { result: { path: path.relative(ROOT, paths[0]), url: `/api/stills/${path.basename(paths[0])}?v=${v}`,
      stills: paths.map((p, i) => ({ seconds: secs[i], path: path.relative(ROOT, p), url: `/api/stills/${path.basename(p)}?v=${v}` })) } };
  } });
  const r = await waitOrThrow(j, req, res, "still_failed", "정지 화면을 찍지 못했습니다"); if (!r) return;
  res.json({ ok: true, ...r });
}));
app.use("/api/stills", express.static(STILLS));

// ---------- 표지: 가장 최근 렌더의 한 프레임 ----------
const COVERS = path.join(ROOT, "data", "workspace", "covers");
const coverBusy = new Map();
app.get("/api/projects/:id/cover", ah(async (req, res) => {
  const id = checkId(req.params.id);
  if (!existsSync(OUT)) return sendError(res, 404, "no_cover", "아직 렌더가 없습니다");
  const mine = await ownedBy(id, (await fs.readdir(OUT)).filter((f) => f.endsWith(".mp4")));
  const outs = [];
  for (const f of mine) { const st = await fs.stat(path.join(OUT, f)).catch(() => null); if (st) outs.push({ f, m: st.mtimeMs }); }
  if (!outs.length) return sendError(res, 404, "no_cover", "아직 렌더가 없습니다");
  outs.sort((a, b) => b.m - a.m);
  await fs.mkdir(COVERS, { recursive: true });
  const dst = path.join(COVERS, `${id}.jpg`);
  const st = await fs.stat(dst).catch(() => null);
  if (!st || st.mtimeMs < outs[0].m) {
    if (!coverBusy.has(id)) coverBusy.set(id, run("ffmpeg", ["-y", "-v", "error", "-ss", "1.2", "-i", path.join(OUT, outs[0].f), "-frames:v", "1", "-vf", "scale=216:-2", "-q:v", "4", dst], { timeout: 20e3 }).finally(() => coverBusy.delete(id)));
    const r = await coverBusy.get(id) ?? { code: existsSync(dst) ? 0 : 1 };
    if (r.code !== 0 && !existsSync(dst)) return sendError(res, 404, "no_cover", "표지를 만들지 못했습니다");
  }
  res.set("cache-control", "no-cache").sendFile(dst);
}));

// ---------- 렌더 (작업) ----------
/** render.py 출력 줄 → 진행률 · 단계 (대략) */
function renderProgress(h) {
  let groups = 1;
  return (l) => {
    let m;
    if (/^\[캐스팅\]/.test(l)) h.progress(0.05, "장면별 엔진 배정");
    else if ((m = l.match(/^\[묶음 (\d+)\/(\d+)\]/))) { groups = Number(m[2]); h.progress(0.08 + 0.62 * (Number(m[1]) - 1) / groups, `장면 묶음 ${m[1]}/${m[2]} 렌더`); }
    else if (/^\[엔진\]/.test(l)) h.progress(0.08, "화면 렌더");
    else if ((m = l.match(/(\d{1,3}(?:\.\d+)?)\s*%/)) && (h.job.stage || "").includes("렌더")) { const p = Math.min(100, Number(m[1])) / 100; h.progress(Math.max(h.job.progress || 0, 0.08 + 0.62 * p / groups), null); }
    else if (/마무리|자막|음성|finish|\.ass\b/i.test(l) && (h.job.progress || 0) < 0.75) h.progress(0.75, "음성 · 자막 입히기");
    else if (/^\[완료\]/.test(l)) h.progress(0.97, "마무리");
  };
}
function renderJob(id, body = {}) {
  const a = engArgs(body);
  // 출력 해상도 · 화질 · 초당 프레임 (engine/render.py --size --quality --fps)
  if (["720", "1080", "1440", "2160"].includes(String(body.size))) a.push("--size", String(body.size));
  if (["standard", "high", "max"].includes(body.quality)) a.push("--quality", body.quality);
  if ([30, 60].includes(Number(body.fps))) a.push("--fps", String(Number(body.fps)));
  // 시안: 장면 1~3 초안(관문 — 사용자가 보고 확인하면 최종 렌더 · 유료 생성이 풀린다)
  if (body.draft13) a.push("--draft", "--scenes", "1-3");
  if (body.force) a.push("--force");      // 최종본 디자인 관문을 사용자가 알고 넘김
  return jobs.create({ type: "render", project: id, key: `render:${id}`, label: body.draft13 ? "시안 렌더(장면 1~3)" : "렌더", work: async (h) => {
    await fs.mkdir(OUT, { recursive: true });
    const workRoot = path.join(RENDER_WORK, "_jobs", h.job.id);   // 미리보기 빌드 · 정지 화면과 다른 폴더
    h.progress(0.02, "준비");
    const r = await h.run(PY, ["engine/render.py", `data/storyboards/${id}.json`, ...a], { cwd: ROOT, env: { ...process.env, FLUMA_WORK_ROOT: workRoot }, onLine: renderProgress(h) });
    await fs.rm(workRoot, { recursive: true, force: true }).catch(() => {});
    if (r.timedOut || r.canceled) return r;
    const last = renderedFile(r);
    if (r.code !== 0 || !last) return { error: "렌더에 실패했습니다", detail: resultBlock(r.out)?.error || tail(r.err || r.out) };
    return { result: { url: `/api/out/${path.basename(last)}`, file: path.basename(last) } };
  } });
}
app.post("/api/render", ah(async (req, res) => {
  const id = checkId(req.body?.id); if (!existsSync(sbPath(id))) throw notFound("콘티가 없습니다");
  logEffort(ROOT, id, "render", "최종 렌더");
  const j = renderJob(id, req.body);
  res.status(202).json({ jobId: j.id, job: jobs.pub(j) });
}));
app.get("/api/jobs", (req, res) => {
  const project = req.query.project ? String(req.query.project) : undefined;
  if (project && !isId(project)) return sendError(res, 400, "bad_id", "올바르지 않은 id 입니다");
  res.json(jobs.list({ project, type: req.query.type ? String(req.query.type) : undefined }));
});
app.get("/api/jobs/:id", (req, res) => { const j = jobs.get(req.params.id); if (!j) return sendError(res, 404, "not_found", "작업이 없습니다"); res.json(jobs.pub(j)); });
app.delete("/api/jobs/:id", (req, res) => {
  const j = jobs.get(req.params.id); if (!j) return sendError(res, 404, "not_found", "작업이 없습니다");
  res.json({ ok: jobs.cancel(j.id), job: jobs.pub(j) });
});
const jobStream = (req, res) => { const j = jobs.get(req.params.id || req.params.jobId); if (!j) return sendError(res, 404, "not_found", "작업이 없습니다"); jobs.stream(j, req, res); };
app.get("/api/jobs/:id/events", jobStream);
app.get("/api/render/:jobId/events", jobStream);   // 예전 주소
app.use("/api/out", express.static(OUT));

// ---------- 렌더 영상 내려받기 — 편집기 '내려받기' 버튼. Docker 에서도 명령 없이 영상을 내 컴퓨터로(2026-11-05) ----------
// 이 영상의 data/out/<id>…mp4 만(다른 영상 · 다른 폴더 파일은 이름으로 막는다). 파일 이름은 영상 제목으로 저장되게
const rendersOf = async (id) => {
  if (!existsSync(OUT)) return [];
  const names = (await fs.readdir(OUT)).filter((n) => (n.startsWith(`${id}-`) || n === `${id}.mp4`) && n.endsWith(".mp4"));
  const rows = await Promise.all(names.map(async (n) => {
    const st = await fs.stat(path.join(OUT, n));
    const draft = n.includes("-draft"), variant = /-variants?(-\d+)?\.mp4$/.test(n);
    const aspect = /-16x9/.test(n) ? "16:9" : /-1x1/.test(n) ? "1:1" : "9:16";
    const size = (/-(720|1440|2160)p/.exec(n) || [])[1] || null;
    const part = (/-s(\d+(?:-\d+)?)(?:-|\.)/.exec(n) || [])[1] || null;
    return { name: n, bytes: st.size, mtime: st.mtimeMs, draft, variant, aspect, size, scenes: part, url: `/api/out/${encodeURIComponent(n)}`,
      download: `/api/projects/${id}/renders/${encodeURIComponent(n)}/download` };
  }));
  return rows.sort((a, b) => b.mtime - a.mtime);
};
app.get("/api/projects/:id/renders", ah(async (req, res) => { res.json(await rendersOf(checkId(req.params.id))); }));
app.get("/api/projects/:id/renders/:name/download", ah(async (req, res) => {
  const id = checkId(req.params.id), name = String(req.params.name);
  if (!(name.startsWith(`${id}-`) || name === `${id}.mp4`) || !name.endsWith(".mp4") || /[\\/]|\.\./.test(name)) throw notFound("영상이 없습니다");
  const f = path.join(OUT, name);
  if (!existsSync(f)) throw notFound("영상이 없습니다");
  let title = id;
  try { title = String(JSON.parse(await fs.readFile(sbPath(id), "utf8")).title || id); } catch { /* 콘티 없음 */ }
  const tag = name.slice(id.length).replace(/\.mp4$/, "").replace(/-craft-Scenes/, "").replace(/^-/, "");
  const nice = `${title}${tag ? ` (${tag})` : ""}.mp4`.replace(/[\\/:*?"<>|\n\r]+/g, " ").slice(0, 150);
  res.download(f, nice);
}));

// ---------- 유튜브 업로드 ----------
app.post("/api/upload", ah(async (req, res) => {
  const { id, mp4, privacy = "private", publishAt } = req.body || {};
  checkId(id);
  const name = String(mp4 || "").replace(/^\/?(api\/)?out\//, "").replace(/\?.*$/, "");
  if (!/^[A-Za-z0-9가-힣_.-]+\.mp4$/.test(name) || name.includes("..")) throw bad("data/out/ 폴더의 mp4 파일 이름만 올릴 수 있습니다", "bad_file");
  const file = within(OUT, name); if (!existsSync(file)) throw notFound("렌더 파일이 없습니다");
  if (!["private", "unlisted", "public"].includes(privacy)) throw bad("공개 범위가 올바르지 않습니다");
  const args = ["engine/publish/upload_youtube.py", `data/storyboards/${id}.json`, file, "--privacy", privacy];
  if (publishAt) { if (!/^\d{4}-\d{2}-\d{2}T[\d:.]+(Z|[+-]\d{2}:\d{2})?$/.test(String(publishAt))) throw bad("예약 시각 형식이 올바르지 않습니다"); args.push("--publish-at", String(publishAt)); }
  const r = await py(args, { timeout: 15 * 60e3, signal: requestSignal(req, res) });
  if (r.canceled) return;
  if (r.code !== 0) { console.error("[upload]", tail(r.err || r.out, 12)); throw new HttpError(500, "upload_failed", "유튜브에 올리지 못했습니다", tail(r.err || r.out, 3)); }
  const url = (r.out.match(/https:\/\/(?:www\.)?youtu(?:\.be|be\.com)\/\S+/) || [])[0] || null;
  res.json({ ok: true, url });
}));

// ---------- 시세 템플릿 채우기 ----------
app.post("/api/fill", ah(async (req, res) => {
  const { template, data } = req.body || {};
  if (!template || !data || typeof template !== "string" || typeof data !== "string") throw bad("template, data 가 필요합니다");
  const tpl = path.relative(ROOT, within(ROOT, template)), dat = path.relative(ROOT, within(ROOT, data));
  const r = await py(["engine/story/fill_template.py", tpl, dat], { timeout: 60e3 });
  if (r.code !== 0) throw new HttpError(500, "fill_failed", "템플릿을 채우지 못했습니다", tail(r.err || r.out, 3));
  const saved = r.out.match(/저장:\s+(.*?\.json)/);
  res.json({ ok: true, id: saved ? path.basename(saved[1], ".json") : null });
}));

// ---------- 채팅 (에이전트) ----------
const chatId = (req) => checkId(req.params.id, { allowSystem: true });
app.get("/api/projects/:id/chat", ah(async (req, res) => res.json(await agent.history(chatId(req)))));
app.get("/api/projects/:id/chat/events", (req, res) => {
  if (!isId(req.params.id, { allowSystem: true })) return sendError(res, 400, "bad_id", "올바르지 않은 id 입니다");
  res.set({ "Content-Type": "text/event-stream", "Cache-Control": "no-cache", Connection: "keep-alive", "X-Accel-Buffering": "no" });
  res.flushHeaders();
  res.write("retry: 3000\n\n");
  const off = agent.subscribe(req.params.id, res, Number(req.headers["last-event-id"] || 0));
  const hb = setInterval(() => res.write(": hb\n\n"), 15000);
  req.on("close", () => { clearInterval(hb); off(); });
});
app.post("/api/projects/:id/chat", ah(async (req, res) => {
  const id = chatId(req);
  const { message, look, template, skill, scene, model, steer, context, interrupt } = req.body || {};
  if (!message || typeof message !== "string") throw bad("메시지가 필요합니다");
  logEffort(ROOT, id, "chat", message.slice(0, 120));
  // 작업 중이면: 지금 턴에 끼워 넣고(가능하면), 안 되면 다음 차례로 줄 세운다 — 화면이 '작업 중'을 몰랐어도 거절하지 않음
  if (agent.running(id)) {
    if (interrupt) { const mode = agent.interrupt(id, message.slice(0, 20000), { look, template, skill, scene, model, context }); if (mode) return res.json({ ok: true, mode }); }
    const mode = await agent.say(id, message.slice(0, 20000), { look, template, skill, scene, model, context });
    return res.json({ ok: true, mode });
  }
  const r = await agent.start(id, { message: message.slice(0, 20000), look, template, skill, scene, model, context });
  res.json({ ok: true, mode: "start", ...r });
}));
app.get("/api/agent/active", (_req, res) => res.json(agent.active()));
// 홈 대화 목록: 영상(프로젝트)마다의 대화 기록 — 콘티가 아직 없는 기획 대화도 포함
app.get("/api/chats", ah(async (_req, res) => {
  const dir = path.join(ROOT, "data", "workspace", "sessions");
  const names = existsSync(dir) ? (await fs.readdir(dir)).filter((n) => n.endsWith(".json") && !n.startsWith("_")) : [];
  const out = [];
  for (const n of names) {
    const id = n.slice(0, -5); if (!isId(id)) continue;
    try {
      const s = JSON.parse(await fs.readFile(path.join(dir, n), "utf8"));
      const msgs = s.messages || []; if (!msgs.length) continue;
      const first = msgs.find((m) => m.role === "user");
      let title = null; try { title = JSON.parse(await fs.readFile(sbPath(id), "utf8")).title || null; } catch { /* 콘티 전 */ }
      out.push({ id, title: title || String(first?.text || "새 영상").split("\n")[0].slice(0, 60), updated: msgs.at(-1)?.ts ?? 0, count: msgs.length,
        storyboard: existsSync(sbPath(id)), audio: existsSync(path.join(ROOT, "data", "audio", `${id}.timing.json`)), composed: existsSync(path.join(ROOT, "data", "compositions", id, "scene.js")) || existsSync(path.join(ROOT, "data", "compositions", id, "craft", "craft.json")), running: agent.running(id) });
    } catch { /* 깨진 기록은 건너뜀 */ }
  }
  res.json(out.sort((a, b) => b.updated - a.updated));
}));
app.delete("/api/projects/:id/chat/queued/:index", (req, res) => {
  if (!isId(req.params.id, { allowSystem: true })) return sendError(res, 400, "bad_id", "올바르지 않은 id 입니다");
  res.json({ ok: agent.unqueue(req.params.id, Number(req.params.index)) });
});
app.post("/api/projects/:id/chat/stop", (req, res) => {
  if (!isId(req.params.id, { allowSystem: true })) return sendError(res, 400, "bad_id", "올바르지 않은 id 입니다");
  res.json({ ok: agent.stop(req.params.id) });
});
app.delete("/api/projects/:id/chat", ah(async (req, res) => { await agent.reset(chatId(req)); res.json({ ok: true }); }));
app.post("/api/projects/:id/revert", ah(async (req, res) => {
  const id = chatId(req);
  if (agent.running(id)) throw conflict("에이전트가 작업 중일 때는 되돌릴 수 없습니다", "busy");
  logEffort(ROOT, id, "undo", "되돌리기");
  const paths = Array.isArray(req.body?.paths) ? req.body.paths.filter((p) => typeof p === "string") : undefined;
  const r = await agent.revert(id, paths);
  res.json({ ok: r.conflicts.length === 0, files: r.files, conflicts: r.conflicts });
}));

// ---------- 설정 · 에이전트 실행 환경 ----------
const SETTINGS = path.join(ROOT, "data", "workspace", "settings.json");
const MODELS = ["", "opus", "sonnet", "haiku", "claude-fable-5-1"];
const EFFORTS = ["", "low", "medium", "high", "xhigh", "max"];
function sanitizeAgent(a = {}) {
  const str = (x, n = 120) => (typeof x === "string" ? x.trim().slice(0, n) : "");
  return {
    mode: a.mode === "api" ? "api" : "cli",
    cli: AGENTS.some((x) => x.id === a.cli && x.runs) ? a.cli : "claude",
    claudeModel: str(a.claudeModel), codexModel: str(a.codexModel),
    effort: EFFORTS.includes(a.effort) ? a.effort : "",
    provider: PROVIDERS.some((x) => x.id === a.provider) ? a.provider : "anthropic",
    apiModel: str(a.apiModel), baseUrl: /^https?:\/\//.test(str(a.baseUrl, 300)) ? str(a.baseUrl, 300) : "",
    protocol: a.protocol === "responses" ? "responses" : "anthropic",
  };
}
app.get("/api/agents", ah(async (_req, res) => {
  const keys = readKeys();
  const s = await readJson(SETTINGS, {}) || {};
  let active = null, problem = null;
  try { active = resolveRuntime(s).label; } catch (e) { problem = e.message; }
  res.json({ agents: detectAgents(), models: { claude: CLAUDE_MODELS, codex: codexModels() },
    providers: PROVIDERS.map((p) => ({ ...p, hasKey: !!keys[p.id] || !!p.local, keyMasked: mask(keys[p.id]) })), active, problem });
}));
app.put("/api/agent-keys/:id", ah(async (req, res) => {
  const { id } = req.params;
  if (!PROVIDERS.some((p) => p.id === id)) throw notFound("제공자가 없습니다");
  const key = String(req.body?.key ?? "").trim();
  if (key.length > 400 || /\s/.test(key)) throw bad("키 형식이 올바르지 않습니다", "bad_key");
  writeKey(id, key);
  res.json({ ok: true, keyMasked: mask(key) });
}));
// 연결 시험: 저장된(또는 제공자 기본) 주소로만 — 요청이 준 주소로 키를 보내지 않는다
app.post("/api/agent-test/:id", ah(async (req, res) => {
  const p = PROVIDERS.find((x) => x.id === req.params.id); if (!p) throw notFound("제공자가 없습니다");
  const s = (await readJson(SETTINGS, {})) || {};
  const stored = s.agent?.provider === p.id ? String(s.agent?.baseUrl || "") : "";
  let base = String(p.baseUrl || stored || "").replace(/\/+$/, "");
  const asked = String(req.body?.baseUrl || "").replace(/\/+$/, "");
  if (asked && base) { try { if (new URL(asked).host === new URL(base).host) base = asked; } catch { /* 무시 */ } }
  if (!base) throw bad("주소가 없습니다 — 설정에서 Base URL 을 먼저 저장하세요", "no_base_url");
  const key = readKeys()[p.id] || (p.local ? "ollama" : "");
  const protocol = p.custom ? (s.agent?.protocol === "responses" ? "responses" : "anthropic") : p.protocol;
  const url = protocol === "anthropic" ? `${base}${/\/v1$/.test(base) ? "" : "/v1"}/models` : `${base}/models`;
  const headers = p.auth === "x-api-key" ? { "x-api-key": key, "anthropic-version": "2023-06-01" } : p.auth === "api-key" ? { "api-key": key } : { authorization: `Bearer ${key}` };
  try {
    const r = await fetch(url, { headers, signal: AbortSignal.timeout(12000), redirect: "error" });
    const txt = await r.text();
    let n = null; try { const d = JSON.parse(txt); n = (d.data || d.models || []).length; } catch { /* 형식 다름 */ }
    res.json({ ok: r.ok, status: r.status, models: n, error: r.ok ? null : `응답 ${r.status}` });
  } catch (e) { res.json({ ok: false, error: e?.name === "TimeoutError" ? "응답이 없습니다 (12초)" : "연결하지 못했습니다" }); }
}));

// ---------- 능력별 모델(보기 · 만들기 · 말하기 — 오픈라우터) · 비용 상한 ----------
// 목록 · 가격은 engine/providers/catalog.py 가 오픈라우터 공개 목록에서(하루 한 번 캐시). 모델은 사용자가 고른다 — 코드에 박지 않는다
const CAPS = ["see.video", "voice.tts", "voice.stt", "make.sound", "embed"];   // 그림 · 영상 생성은 없앴다(2026-11-09) — 화면은 완전 로컬
function sanitizeModels(m = {}) {
  const o = {};
  for (const c of CAPS) { const v = typeof m?.[c] === "string" ? m[c].trim() : ""; if (v === "local" || /^[a-z0-9._-]+\/[a-z0-9._:-]+$/i.test(v)) o[c] = v; }
  return o;
}
function sanitizeBudget(b = {}) {
  const n = Number(b?.per_video);
  return { per_video: Number.isFinite(n) && n >= 0 && n <= 500 ? Math.round(n * 100) / 100 : 3 };
}
app.get("/api/models/caps", ah(async (_req, res) => {
  const r = await py(["engine/providers/catalog.py", "caps", "--json"], { timeout: 90e3 });
  const v = lastJson(r); if (!v) throw new Error(tail(r.err)); res.json(v);
}));
app.get("/api/models/list/:cap", ah(async (req, res) => {
  if (!CAPS.includes(req.params.cap)) throw notFound("그런 능력이 없습니다");
  const r = await py(["engine/providers/catalog.py", "list", req.params.cap, "--json", ...(req.query.refresh ? ["--refresh"] : [])], { timeout: 120e3 });
  const v = lastJson(r); if (!v) throw new Error(tail(r.err) || "모델 목록을 받지 못했습니다"); res.json(v);
}));
app.put("/api/models/choice", ah(async (req, res) => {
  const prev = (await readJson(SETTINGS, {})) || {};
  const s = { ...prev, models: sanitizeModels({ ...(prev.models || {}), ...(req.body?.models || {}) }), budget: sanitizeBudget(req.body?.budget ?? prev.budget) };
  markEcho(SETTINGS, clientOf(req));
  await atomicWrite(SETTINGS, JSON.stringify(s, null, 1));
  invalidate("voices:avail");
  res.json({ ok: true, models: s.models, budget: s.budget });
}));

app.get("/api/settings", ah(async (_req, res) => {
  const s = (await readJson(SETTINGS, {})) || {};
  res.json({ settings: { model: "", effort: "", language: "korean", voice_engine: "edge", voice_id: "", voice_auto: true, music_any_license: false, ...s }, models: MODELS, efforts: EFFORTS });
}));
app.put("/api/settings", ah(async (req, res) => {
  const b = req.body || {};
  const model = String(b.model ?? "").trim();
  if (model && !MODELS.includes(model) && !/^claude-[a-z0-9.-]+$/.test(model)) throw bad("모델 이름이 올바르지 않습니다");
  if (b.effort && !EFFORTS.includes(b.effort)) throw bad("생각 깊이가 올바르지 않습니다");
  const prev = (await readJson(SETTINGS, {})) || {};
  const okVoice = (v) => /^[a-z0-9_-]+$/.test(v) && existsSync(path.join(ROOT, "engine", "voice", "engines", v, "voice.json"));
  let ve = String(b.voice_engine ?? prev.voice_engine ?? "edge");
  if (!okVoice(ve)) {
    // 없어진 엔진(예: 2026-11-09 에 뺀 Gemini 음성)이 예전 설정에 남아 있으면 Edge 로 — 다른 설정 저장을 막지 않게
    if (b.voice_engine !== undefined && b.voice_engine !== prev.voice_engine) throw bad("음성 엔진이 올바르지 않습니다");
    ve = "edge";
  }
  const s = { model, effort: b.effort || "", language: ["english", "chinese"].includes(b.language) ? b.language : "korean",
    voice_engine: ve, voice_id: String(b.voice_id ?? prev.voice_id ?? "").slice(0, 80),
    voice_auto: (b.voice_auto ?? prev.voice_auto ?? true) !== false,                 // 자동: 영상마다 레퍼런스에 맞춰 목소리 · 말 속도를 고름(voice_match auto)
    music_any_license: (b.music_any_license ?? prev.music_any_license ?? false) === true, // 상업 유행곡도 영상에 직접 넣기(권리 위험을 사용자가 알고 켬)
    agent: sanitizeAgent(b.agent ?? prev.agent ?? {}),
    models: sanitizeModels(b.models ?? prev.models), budget: sanitizeBudget(b.budget ?? prev.budget) };
  markEcho(SETTINGS, clientOf(req));
  await atomicWrite(SETTINGS, JSON.stringify(s, null, 1));
  res.json({ ok: true, settings: s });
}));

// 목소리 다시 만들기 (작업): 나레이션 합성 → 장면 길이 · 단어 자막 → 검사
app.post("/api/projects/:id/voice", ah(async (req, res) => {
  const id = checkId(req.params.id); if (!existsSync(sbPath(id))) throw notFound("콘티가 없습니다");
  logEffort(ROOT, id, "voice", "목소리 다시 만들기");
  const j = jobs.create({ type: "voice", project: id, key: `voice:${id}`, label: "목소리 만들기", work: async (h) => {
    h.progress(0.05, "나레이션 합성");
    const r = await h.run(PY, ["engine/voice/assemble_audio.py", `data/storyboards/${id}.json`], { cwd: ROOT, onLine: (l) => { const m = l.match(/^\s*(\d+)\s+\S+\s+[\d.]+/); if (m) h.progress(null, `장면 ${Number(m[1]) + 1} 맞추는 중`); } });
    if (r.timedOut || r.canceled) return r;
    if (r.code !== 0) return { error: "목소리를 만들지 못했습니다", detail: tail(r.err || r.out) };
    h.progress(0.95, "검사");
    return { result: { lint: await lintOf(id) } };
  } });
  const r = await waitOrThrow(j, req, res, "voice_failed", "목소리를 만들지 못했습니다"); if (!r) return;
  res.json({ ok: true, jobId: j.id, lint: r.lint });
}));

// ---------- 올린 파일 (사진 · 실사 영상) → data/public/uploads/<id>/ ----------
const UPLOADS = path.join(PUBLIC, "uploads");
const IMG_EXT = [".jpg", ".jpeg", ".png", ".webp", ".gif"], VID_EXT = [".mp4", ".mov", ".webm", ".mkv", ".m4v"];
const AUD_EXT = [".mp3", ".m4a", ".wav", ".ogg", ".aac", ".flac"];   // 배경음악(콘티 music.src) — 권리는 사용자 판단
const MAX_UPLOAD = 2 * 1024 ** 3;
const safeName = (n) => path.basename(String(n || "")).normalize("NFC").replace(/[^A-Za-z0-9가-힣._-]+/g, "-").replace(/^[-.]+/, "").slice(0, 80);
async function probe(file) {
  const r = await run("ffprobe", ["-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:format=duration", "-of", "json", file], { timeout: 30e3 });
  try { const d = JSON.parse(r.out); const st = d.streams?.[0] || {}; return { width: st.width, height: st.height, duration: Number(d.format?.duration || 0) }; } catch { return {}; }
}
async function uploadList(id) {
  const dir = path.join(UPLOADS, id); if (!existsSync(dir)) return [];
  const out = [];
  for (const n of (await fs.readdir(dir)).sort()) {
    if (n.endsWith(".part")) continue;
    const ext = path.extname(n).toLowerCase(); const st = await fs.stat(path.join(dir, n)).catch(() => null);
    if (!st || st.isDirectory()) continue;
    if (IMG_EXT.includes(ext)) out.push({ name: n, kind: "image", url: `/api/public/uploads/${id}/${encodeURIComponent(n)}`, rel: `uploads/${id}/${n}`, size: st.size });
    else if (AUD_EXT.includes(ext)) out.push({ name: n, kind: "audio", url: `/api/public/uploads/${id}/${encodeURIComponent(n)}`, rel: `uploads/${id}/${n}`, size: st.size });
    else if (VID_EXT.includes(ext)) {
      const stem = n.slice(0, -ext.length); const meta = (await readJson(path.join(dir, stem, "meta.json"), {})) || {};
      const job = jobs.active(id).find((j) => j.type === "upload" && j.label.endsWith(n));
      out.push({ name: n, kind: "video", url: `/api/public/uploads/${id}/${encodeURIComponent(n)}`, rel: `uploads/${id}/${n}`, seq: `uploads/${id}/${stem}`,
        poster: meta.frames ? `/api/public/uploads/${id}/${encodeURIComponent(stem)}/f00001.jpg` : null, size: st.size, processing: job ? job.id : null, ...meta });
    }
  }
  return out;
}
app.get("/api/projects/:id/uploads", ah(async (req, res) => res.json(await uploadList(checkId(req.params.id)))));
/** 본문을 바로 디스크로 (메모리에 담지 않음). 영상은 프레임 풀기를 작업으로 */
app.post("/api/projects/:id/uploads", ah(async (req, res) => {
  const id = checkId(req.params.id); const name = safeName(req.query.name);
  if (!name) throw bad("파일 이름이 올바르지 않습니다");
  logEffort(ROOT, id, "upload", name);
  const ext = path.extname(name).toLowerCase();
  if (![...IMG_EXT, ...VID_EXT, ...AUD_EXT].includes(ext)) throw bad("사진(jpg · png · webp · gif) · 영상(mp4 · mov · webm · mkv) · 음악(mp3 · m4a · wav · ogg)만 올릴 수 있습니다", "bad_type");
  const len = Number(req.headers["content-length"] || 0);
  if (len > MAX_UPLOAD) throw new HttpError(413, "too_large", "2GB 보다 큰 파일은 올릴 수 없습니다");
  const dir = path.join(UPLOADS, id); await fs.mkdir(dir, { recursive: true });
  const file = within(dir, name), part = `${file}.part`;
  let size = 0;
  const limit = new Transform({ transform(chunk, _e, cb) { size += chunk.length; if (size > MAX_UPLOAD) cb(new HttpError(413, "too_large", "2GB 보다 큰 파일은 올릴 수 없습니다")); else cb(null, chunk); } });
  try { await pipeline(req, limit, createWriteStream(part)); }
  catch (e) { await fs.rm(part, { force: true }); if (e instanceof HttpError) throw e; throw new HttpError(400, "upload_aborted", "올리는 중에 끊겼습니다"); }
  if (!size) { await fs.rm(part, { force: true }); throw bad("빈 파일입니다", "empty"); }
  markEcho(file, clientOf(req));
  await fs.rename(part, file);
  let jobId = null;
  if (VID_EXT.includes(ext)) {
    // 30fps · 폭 1080 이하 JPG 프레임 (K.seq 가 시간으로 고름 → 렌더에서도 프레임 정확)
    const stem = name.slice(0, -ext.length); const fdir = path.join(dir, stem);
    const j = jobs.create({ type: "upload", project: id, key: `upload:${id}:${name}`, label: `영상 프레임 풀기 · ${name}`, work: async (h) => {
      await fs.rm(fdir, { recursive: true, force: true }); await fs.mkdir(fdir, { recursive: true });
      const info = await probe(file);
      h.progress(0.1, "프레임 푸는 중");
      const r = await h.run("ffmpeg", ["-v", "error", "-y", "-i", file, "-t", "180", "-vf", "fps=30,scale='min(1080,iw)':-2", "-q:v", "3", path.join(fdir, "f%05d.jpg")]);
      if (r.timedOut || r.canceled) return r;
      if (r.code !== 0) return { error: "영상을 풀지 못했습니다", detail: tail(r.err) };
      const frames = (await fs.readdir(fdir)).filter((f) => f.endsWith(".jpg")).length;
      await atomicWrite(path.join(fdir, "meta.json"), JSON.stringify({ frames, fps: 30, ext: "jpg", pad: 5, duration: info.duration, width: info.width, height: info.height, src: name }));
      publish({ kind: "uploads", id });
      return { result: { frames } };
    } });
    jobId = j.id;
  }
  res.json({ ok: true, jobId, files: await uploadList(id) });
}));
app.delete("/api/projects/:id/uploads/:name", ah(async (req, res) => {
  const id = checkId(req.params.id); const name = safeName(req.params.name);
  if (!name) throw bad("파일 이름이 올바르지 않습니다");
  const dir = path.join(UPLOADS, id); const ext = path.extname(name).toLowerCase();
  await fs.rm(within(dir, name), { force: true });
  if (VID_EXT.includes(ext)) await fs.rm(within(dir, name.slice(0, -ext.length)), { recursive: true, force: true });
  res.json({ ok: true, files: await uploadList(id) });
}));

// ---------- 레이어 요소 (data/public/elements/<id>/<이름>/) ----------
app.get("/api/projects/:id/elements", ah(async (req, res) => {
  const id = checkId(req.params.id);
  const dir = path.join(PUBLIC, "elements", id); if (!existsSync(dir)) return res.json([]);
  const out = [];
  for (const n of (await fs.readdir(dir)).sort()) {
    const m = await readJson(path.join(dir, n, "meta.json")); if (!m) continue;   // 만드는 중
    out.push({ name: n, rel: `elements/${id}/${n}`, poster: `/api/public/elements/${id}/${n}/f${String(Math.max(1, Math.ceil((m.frames || 1) / 2))).padStart(m.pad || 4, "0")}.${m.ext || "png"}`, ...m });
  }
  res.json(out);
}));

// ---------- 영상 삭제 → 휴지통 (data/workspace/trash/<시각>__<id>/) ----------
const TRASH = path.join(ROOT, "data", "workspace", "trash");
/** 옮기기 — 다른 디스크 · 볼륨 사이(Docker 볼륨 EXDEV)나 Windows 가 잠깐 잡고 있는 파일(EPERM · EBUSY)이면 복사 뒤 지운다 */
async function moveFile(src, dst) {
  await fs.mkdir(path.dirname(dst), { recursive: true });
  try { await fs.rename(src, dst); return; } catch (e) { if (!["EXDEV", "EPERM", "EBUSY", "EACCES"].includes(e?.code)) throw e; }
  await fs.cp(src, dst, { recursive: true, force: true, preserveTimestamps: true });
  for (let i = 0; ; i++) {
    try { await fs.rm(src, { recursive: true, force: true }); return; } catch (e) { if (i >= 4) throw e; await new Promise((r) => setTimeout(r, 300 * (i + 1))); }
  }
}
async function projectFiles(id) {
  // 이 영상만의 파일: 이름이 id 이거나 id. · id- 로 시작하면서 더 긴 다른 영상 id 의 것이 아닌 것. data/research/ 는 여러 영상이 같이 씀
  // 2026-11-09: 폴더가 data/ 아래로 옮겨진 뒤에도 옛 이름(storyboards · compositions · out …)을 보고 있어 콘티 · 렌더가 휴지통으로 안 갔다
  const dirs = ["data/storyboards", "data/compositions", "data/public/audio", "data/public/uploads", "data/public/elements", "data/public/archive", "data/audio", "data/out",
    "data/workspace/sessions", "data/workspace/render", "data/workspace/covers", "data/workspace/stills", "data/workspace/tmp", "data/workspace/feel", "data/workspace/concepts", "data/workspace/critique", "data/briefs"];
  const out = [];
  for (const d of dirs) {
    const abs = path.join(ROOT, d); if (!existsSync(abs)) continue;
    for (const n of await ownedBy(id, await fs.readdir(abs))) out.push(path.join(d, n));
  }
  return out;
}
app.delete("/api/projects/:id", ah(async (req, res) => {
  const id = checkId(req.params.id);
  if (agent.running(id)) throw conflict("에이전트가 이 영상을 만드는 중입니다 — 멈춘 뒤 지우세요", "busy");
  if (jobs.active(id).length) throw conflict("이 영상의 작업(렌더 등)이 진행 중입니다 — 끝나거나 취소한 뒤 지우세요", "busy");
  const files = await projectFiles(id);
  if (!files.length) throw notFound("지울 파일이 없습니다");
  const title = (await readJson(path.join(STORY, `${id}.json`)))?.title || id;
  const name = `${new Date().toISOString().replace(/[:.]/g, "-")}__${id}`;
  const dst = path.join(TRASH, name);
  for (const f of files) await moveFile(path.join(ROOT, f), path.join(dst, f));
  await atomicWrite(path.join(dst, "trash.json"), JSON.stringify({ id, title, deletedAt: new Date().toISOString(), files }, null, 1));
  idsCache.at = 0;
  publish({ kind: "storyboard", id, exists: false });
  res.json({ ok: true, trash: name, files: files.length });
}));
const TRASH_RE = /^[\w.-]+__[A-Za-z0-9가-힣_.-]+$/;
const trashDir = (name) => { if (!TRASH_RE.test(name) || name.includes("..")) throw bad("휴지통 항목 이름이 올바르지 않습니다"); return within(TRASH, name); };
app.get("/api/trash", ah(async (_req, res) => {
  if (!existsSync(TRASH)) return res.json([]);
  const list = [];
  for (const n of await fs.readdir(TRASH)) { const m = await readJson(path.join(TRASH, n, "trash.json")); if (m) list.push({ name: n, ...m }); }
  list.sort((a, b) => (a.deletedAt < b.deletedAt ? 1 : -1));
  res.json(list);
}));
app.post("/api/trash/:name/restore", ah(async (req, res) => {
  const src = trashDir(req.params.name);
  const meta = await readJson(path.join(src, "trash.json")); if (!meta) throw notFound("휴지통 항목이 없습니다");
  const files = (meta.files || []).filter((f) => typeof f === "string");
  for (const f of files) within(ROOT, f);
  const clash = files.filter((f) => existsSync(path.join(ROOT, f)));
  if (clash.length) throw conflict(`같은 이름의 파일이 이미 있습니다: ${clash[0]}`, "exists");
  for (const f of files) await moveFile(path.join(src, f), path.join(ROOT, f));
  await fs.rm(src, { recursive: true, force: true });
  idsCache.at = 0;
  res.json({ ok: true, id: meta.id });
}));
app.delete("/api/trash/:name", ah(async (req, res) => { await fs.rm(trashDir(req.params.name), { recursive: true, force: true }); res.json({ ok: true }); }));

// ---------- 편집기 손 수정값 (data/compositions/<id>/overrides.json) ----------
app.get("/api/compositions/:id/overrides", ah(async (req, res) => {
  const p = path.join(ROOT, "data", "compositions", checkId(req.params.id), "overrides.json");
  res.json((await readJson(p, {})) || {});
}));
app.put("/api/compositions/:id/overrides", ah(async (req, res) => {
  const dir = path.join(ROOT, "data", "compositions", checkId(req.params.id));
  if (!existsSync(dir)) throw notFound("화면 구성(컴포지션)이 없습니다");
  const b = req.body; if (!b || typeof b !== "object" || Array.isArray(b)) throw bad("손 수정값 형식이 올바르지 않습니다");
  logEffort(ROOT, req.params.id, "edit", "화면 손 수정");
  const p = path.join(dir, "overrides.json");
  markEcho(p, clientOf(req));
  await atomicWrite(p, JSON.stringify(b, null, 1));
  res.json({ ok: true });
}));

// ---------- 공유 기억 (engine/core/memory.py 와 같은 파일) ----------
const loadMemory = async () => { const r = await py(["engine/core/memory.py", "list", "--json"], { timeout: 30e3 }); try { return JSON.parse(r.out || "[]"); } catch { throw new Error(tail(r.err)); } };
const memoryList = () => cachedValue("memory", loadMemory, { wait: 1500 });
app.get("/api/memory", ah(async (_req, res) => res.json((await memoryList()) ?? [])));
app.delete("/api/memory/:id", ah(async (req, res) => {
  if (!/^[a-f0-9]{6,16}$/.test(req.params.id)) throw bad("기억 id 가 올바르지 않습니다");
  const r = await py(["engine/core/memory.py", "forget", "--id", req.params.id], { timeout: 30e3 });
  if (r.code !== 0) throw new HttpError(500, "memory_failed", "기억을 지우지 못했습니다");
  invalidate("memory"); await memoryList();
  res.json({ ok: true });
}));

// ---------- 캐릭터 ----------
app.get("/api/characters", ah(async (_req, res) => {
  const dir = path.join(ROOT, "data", "characters"), out = [];
  for (const d of existsSync(dir) ? await fs.readdir(dir) : []) {
    const c = await readJson(path.join(dir, d, "character.json")); if (!c?.parts) continue;
    out.push({ ...c, base: `/api/charfiles/${d}/${c.parts.base}`, mouths: Object.fromEntries(Object.entries(c.parts.mouth || {}).map(([k, v]) => [k, `/api/charfiles/${d}/${v}`])), eyes_closed: `/api/charfiles/${d}/${c.parts.eyes_closed}` });
  }
  res.json(out);
}));
app.use("/api/charfiles", express.static(path.join(ROOT, "data", "characters")));

// ---------- 대기열 (data/queue.md) ----------
app.get("/api/queue", ah(async (_req, res) => { res.type("text/plain").send(existsSync(QUEUE) ? await fs.readFile(QUEUE, "utf8") : ""); }));
app.put("/api/queue", express.text({ type: "*/*", limit: "1mb" }), ah(async (req, res) => { await atomicWrite(QUEUE, typeof req.body === "string" ? req.body : ""); res.json({ ok: true }); }));

// ---------- 파일 감시 → /api/events ----------
// 종류: storyboard · composition · overrides · audio · elements · uploads · renders · engines · skills · trends · characters · memory · settings
//       (+ job: 작업 상태, registry: 목록 캐시가 새로 계산됨 {name})
const watchers = new Set();
const recent = [];        // 다시 붙은 화면에 이어 보낼 최근 이벤트 (Last-Event-ID)
let evSeq = 0;
function publish(ev) {
  const id = ++evSeq;
  recent.push({ id, ev }); if (recent.length > 300) recent.shift();
  const data = `id: ${id}\ndata: ${JSON.stringify(ev)}\n\n`;
  for (const c of watchers) c.write(data);
}
const echoes = new Map();   // 절대 경로 -> { client, until } — 화면이 직접 쓴 파일의 감시 이벤트에 그 화면 id 를 붙인다
function markEcho(abs, client) { if (client) echoes.set(path.resolve(abs), { client, until: Date.now() + 3000 }); }
function echoOf(abs) { const e = echoes.get(abs); if (!e) return null; if (Date.now() > e.until) { echoes.delete(abs); return null; } return e.client; }
setInterval(() => { const now = Date.now(); for (const [k, v] of echoes) if (now > v.until) echoes.delete(k); }, 10e3).unref();

const audioId = (n) => n.replace(/\.(timing|captions)\.json$/, "").replace(/\.(wav|json|mp3)$/, "");
/** 바뀐 파일(저장소 기준 상대 경로, / 구분) → { kind, id } | null */
function classify(rel) {
  const p = rel.split("/");
  switch (p[0]) {
    case "storyboards": return p.length === 2 && p[1].endsWith(".json") && isId(p[1].slice(0, -5)) ? { kind: "storyboard", id: p[1].slice(0, -5) } : null;
    case "compositions":
      if (p.length < 3 || !isId(p[1]) || p[2] === "manim" || p[2] === "blender") return null;   // 요소 스크립트는 미리보기와 무관
      return p[2] === "overrides.json" ? { kind: "overrides", id: p[1] } : { kind: "composition", id: p[1] };
    case "tokens": return { kind: "engines" };
    case "characters": return { kind: "characters" };
    case ".claude": return { kind: "skills" };
    case "engines": return p[2] === "templates" ? { kind: "engines" } : null;
    case "out": return p.length === 2 && p[1].endsWith(".mp4") ? { kind: "renders", file: p[1] } : null;
    case "workspace":
      if (p[1] === "memory") return { kind: "memory" };
      return p[1] === "settings.json" && p.length === 2 ? { kind: "settings" } : null;
    case "public":
      if (p[1] === "audio" && p.length === 3) { const id = audioId(p[2]); return isId(id) ? { kind: "audio", id } : null; }
      if (p[1] === "elements" && p.length === 5 && p[4] === "meta.json" && isId(p[2])) return { kind: "elements", id: p[2] };
      if (p[1] === "uploads" && p.length === 4 && isId(p[2]) && !p[3].endsWith(".part")) return { kind: "uploads", id: p[2] };
      if (p[1] === "trends" && (p[2] === "index.json" || (p[2] === "analysis" && p.length === 4))) return { kind: "trends" };
      return null;
    default: return null;
  }
}
const pendingEv = new Map();   // "kind|id" -> { timer, paths:Set }
function onFsChange(rel) {
  const c = classify(rel.split(path.sep).join("/")); if (!c) return;
  const key = `${c.kind}|${c.id || c.file || ""}`;
  let e = pendingEv.get(key);
  if (!e) { e = { paths: new Set(), c }; pendingEv.set(key, e); }
  e.paths.add(path.join(ROOT, rel));
  clearTimeout(e.timer);
  e.timer = setTimeout(() => flushEv(key), 300);
}
async function flushEv(key) {
  const e = pendingEv.get(key); pendingEv.delete(key); if (!e) return;
  try {
    const { kind } = e.c;
    let id = e.c.id;
    if (kind === "renders") { id = ownerOf(e.c.file, await knownIds()) || undefined; }
    if (kind === "engines") { invalidate("engines:list"); }
    if (kind === "memory") { invalidate("memory"); memoryList(); }
    if (kind === "storyboard" || kind === "composition") idsCache.at = 0;
    const ev = { kind, ...(id ? { id } : {}) };
    for (const p of e.paths) { const cl = echoOf(p); if (cl) { ev.client = cl; break; } }
    if (kind === "storyboard") {
      ev.exists = existsSync(sbPath(id));
      if (ev.exists) ev.lint = await lintOf(id).catch(() => []);
    } else if ((kind === "composition" || kind === "audio" || kind === "elements") && id && existsSync(sbPath(id))) {
      ev.lint = await lintOf(id).catch(() => undefined);   // 검사 결과가 바뀔 수 있는 파일 → 화면의 '검사'도 함께 갱신
    }
    publish(ev);
  } catch (err) { console.error("[watch]", err); }
}
// 콘텐츠 폴더만 (엔진은 templates/ 만, public 은 필요한 하위 폴더만)
const engineTemplateDirs = existsSync(ENGINES) ? (await fs.readdir(ENGINES)).map((e) => path.join("engines", e, "templates")).filter((d) => existsSync(path.join(ROOT, d))) : [];
const WATCH = [
  ["storyboards", false], ["scenes", false], ["compositions", true], ["tokens", true], ["characters", true], [".claude/skills", true],
  ["data/workspace/memory", true], ["workspace", false], ["data/public/audio", false], ["data/public/elements", true], ["data/public/uploads", true], ["data/public/trends", false],
  ["data/public/trends/analysis", false], ["out", false], ...engineTemplateDirs.map((d) => [d, true]),
];
for (const [dir, recursive] of WATCH) {
  const abs = path.join(ROOT, dir);
  try {
    if (!existsSync(abs)) await fs.mkdir(abs, { recursive: true });
    const w = watch(abs, { recursive }, (_e, name) => {
      if (!name) return;
      const n = String(name);
      if (n.includes("node_modules") || /(^|[\\/])\./.test(n) || n.endsWith("~") || n.endsWith(".tmp") || n.endsWith(".part")) return;
      onFsChange(path.join(dir, n));
    });
    w.on("error", (e) => console.error(`[watch] ${dir}`, e.message));
  } catch (e) { console.error(`[watch] ${dir} 감시 실패`, e.message); }
}
app.get("/api/events", (req, res) => {
  res.set({ "Content-Type": "text/event-stream", "Cache-Control": "no-cache", Connection: "keep-alive", "X-Accel-Buffering": "no" });
  res.flushHeaders();
  res.write("retry: 3000\n\n");
  const last = Number(req.headers["last-event-id"] || 0);
  if (last) for (const { id, ev } of recent) if (id > last) res.write(`id: ${id}\ndata: ${JSON.stringify(ev)}\n\n`);
  watchers.add(res);
  const hb = setInterval(() => res.write(": hb\n\n"), 15000);
  req.on("close", () => { watchers.delete(res); clearInterval(hb); });
});

// 임시 폴더: 7일 지난 대화별 폴더 · 끝난 렌더 작업 폴더는 시작할 때 지운다
for (const [dir, days] of [[path.join(ROOT, "data", "workspace", "tmp"), 7], [path.join(RENDER_WORK, "_jobs"), 0]]) {
  if (!existsSync(dir)) continue;
  for (const d of await fs.readdir(dir)) {
    const p = path.join(dir, d); const st = await fs.stat(p).catch(() => null);
    if (st && Date.now() - st.mtimeMs > days * 86400e3) await fs.rm(p, { recursive: true, force: true }).catch(() => {});
  }
}

// 빌드된 정적 파일 (npm run build 후)
const dist = path.join(__dirname, "dist");
if (existsSync(dist)) app.use(express.static(dist));

// 없는 /api 주소 · 오류 → 같은 모양 {error:{code,message}}
app.use("/api", (_req, res) => sendError(res, 404, "not_found", "없는 주소입니다"));
// 화면 주소(/settings/media 등)를 바로 열거나 새로 고쳐도 앱이 뜨게 — /api 가 아닌 GET 은 index.html
if (existsSync(dist)) app.get(/^(?!\/api\/).*/, (req, res, next) => (req.accepts("html") ? res.sendFile(path.join(dist, "index.html")) : next()));
app.use((err, req, res, _next) => {
  if (err instanceof HttpError) return sendError(res, err.status, err.code, err.message, err.detail);
  if (err?.type === "entity.parse.failed") return sendError(res, 400, "bad_json", "요청 본문(JSON)이 올바르지 않습니다");
  if (err?.type === "entity.too.large") return sendError(res, 413, "too_large", "요청이 너무 큽니다");
  console.error(`[api] ${req.method} ${req.originalUrl}`, err);
  sendError(res, 500, "internal", "서버 오류가 났습니다");
});

// 목록 캐시를 미리 채운다 (첫 화면이 빈 목록을 덜 보게)
engineList(); engineAvail(); cached("voices:avail", loadVoiceAvail, undefined, () => publish({ kind: "registry", name: "voices" }));
memoryList();
refreshAgents().then(() => publish({ kind: "registry", name: "agents" }));

// 에이전트가 파일을 쓰는 서버이므로 이 컴퓨터에서만 접속 가능하게 한다
// 기본은 이 컴퓨터에서만(127.0.0.1). 컨테이너에서는 FLUMA_HOST=0.0.0.0 — 키 · 파일 접근이 있는 API 라 외부에 열지 않는다
const HOST = process.env.FLUMA_HOST || "127.0.0.1";
const server = app.listen(PORT, HOST, () => console.log(`[api] http://${HOST}:${PORT}  root=${ROOT}`));
const shutdown = () => { agent.shutdown(); for (const j of jobs.list()) if (!jobs.TERMINAL.has(j.status)) jobs.cancel(j.id); server.close(); setTimeout(() => process.exit(0), 1500).unref(); };
process.on("SIGTERM", shutdown); process.on("SIGINT", shutdown);
