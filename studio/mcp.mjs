// MCP 서버 연결 — 사용자가 붙인 MCP 서버의 도구를 에이전트(Claude Code)가 쓸 수 있게 한다.
//  - 설정은 ~/.shortsforge/mcp.json(0600): 토큰 · 비밀이 들어가므로 workspace 가 아니라 에이전트가 읽지 못하는 폴더(DENY)에.
//  - 화면에는 env · header 값은 가린 채로만 보낸다.
//  - 에이전트 실행 때 켜 둔 서버만 --mcp-config 로 넘기고, 허용 도구에 mcp__<이름> 을 더한다.
//  - '연결 시험': stdio 는 실제로 띄워 initialize → tools/list, http 는 같은 요청을 POST 로.
import { spawn } from "node:child_process";
import { chmodSync, existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";

const DIR = path.join(os.homedir(), ".shortsforge");
export const MCP_FILE = path.join(DIR, "mcp.json");
const RUN_FILE = path.join(DIR, "mcp-run.json");   // 에이전트 실행 때 CLI 에 넘기는 파일(켜 둔 서버만)
export const NAME_RE = /^[a-z0-9][a-z0-9_-]{0,30}$/;

export function loadMcp() {
  try { const d = JSON.parse(readFileSync(MCP_FILE, "utf8")); return { servers: d.servers && typeof d.servers === "object" ? d.servers : {} }; }
  catch { return { servers: {} }; }
}
function writeSecret(file, obj) {
  mkdirSync(DIR, { recursive: true, mode: 0o700 });
  const tmp = `${file}.tmp`;
  writeFileSync(tmp, JSON.stringify(obj, null, 1), { mode: 0o600 });
  try { chmodSync(tmp, 0o600); } catch { /* 윈도우 */ }
  renameSync(tmp, file);
}
export const saveMcp = (d) => writeSecret(MCP_FILE, d);

/** 화면용: 비밀 값은 가린다(키 이름만) */
export function publicMcp() {
  const { servers } = loadMcp();
  return Object.entries(servers).map(([name, s]) => ({
    name, type: s.type, enabled: s.enabled !== false, command: s.command ?? null, args: s.args ?? [], url: s.url ?? null,
    env: Object.keys(s.env ?? {}), headers: Object.keys(s.headers ?? {}), lastTest: s.lastTest ?? null,
  }));
}

/** 입력 검사 · 정리. 빈 값으로 온 env/header 는 기존 값을 그대로 둔다(화면은 값을 모르므로) */
export function normalize(input, prev = {}) {
  const type = input.type === "http" ? "http" : "stdio";
  const kv = (obj, old = {}) => {
    const out = {};
    for (const [k, v] of Object.entries(obj ?? {})) {
      if (!/^[A-Za-z_][A-Za-z0-9_-]{0,63}$/.test(k)) throw new Error(`이름이 올바르지 않습니다: ${k}`);
      const val = String(v ?? "");
      out[k] = val === "" && old[k] != null ? old[k] : val.slice(0, 4000);
    }
    return out;
  };
  if (type === "stdio") {
    const command = String(input.command ?? "").trim();
    if (!command || command.length > 300 || /[\n\r]/.test(command)) throw new Error("실행할 명령이 필요합니다 (예: npx)");
    const args = (Array.isArray(input.args) ? input.args : []).map((a) => String(a)).filter((a) => a.length <= 500).slice(0, 40);
    return { type, command, args, env: kv(input.env, prev.env), enabled: input.enabled !== false, lastTest: prev.lastTest ?? null };
  }
  const url = String(input.url ?? "").trim();
  if (!/^https?:\/\/[^\s]+$/.test(url)) throw new Error("http(s) 주소가 필요합니다");
  return { type, url, headers: kv(input.headers, prev.headers), enabled: input.enabled !== false, lastTest: prev.lastTest ?? null };
}

/** 에이전트 실행용: 켜 둔 서버만 담은 설정 파일 경로와 허용 도구 이름. 없으면 null
 *  extra: 설치된 Craft 앱처럼 Fluma 가 직접 붙이는 서버 { 이름: { type, command, args } } — 사용자가 같은 이름을 붙였으면 사용자 것이 우선 */
export function runConfig(extra = {}) {
  const { servers } = loadMcp();
  const on = Object.entries(servers).filter(([n, s]) => NAME_RE.test(n) && s.enabled !== false);
  for (const [n, s] of Object.entries(extra)) if (NAME_RE.test(n) && !servers[n]) on.push([n, s]);
  if (!on.length) return null;
  const mcpServers = Object.fromEntries(on.map(([n, s]) => [n, s.type === "http"
    ? { type: "http", url: s.url, ...(Object.keys(s.headers ?? {}).length ? { headers: s.headers } : {}) }
    : { type: "stdio", command: s.command, args: s.args ?? [], ...(Object.keys(s.env ?? {}).length ? { env: s.env } : {}) }]));
  writeSecret(RUN_FILE, { mcpServers });
  return { file: RUN_FILE, tools: on.map(([n]) => `mcp__${n}`), names: on.map(([n]) => n), servers: mcpServers };
}

/** Codex 용 — 같은 MCP 서버(사용자 MCP + Craft 앱)를 `-c mcp_servers.<이름>.…` 설정 덮어쓰기로(파일 · 전역 설정을 건드리지 않음).
 *  값은 TOML 이고, 문자열 · 문자열 배열은 JSON 표기와 같다. 비밀 값(env · headers)은 명령줄에 싣지 않는다 — 그런 서버는 건너뛴다 */
export function codexArgsFor(servers = {}) {
  const out = [];
  for (const [n, s] of Object.entries(servers)) {
    if (!NAME_RE.test(n)) continue;
    if (s.type === "http") {
      if (Object.keys(s.headers ?? {}).length) continue;
      out.push(`mcp_servers.${n}.url=${JSON.stringify(s.url)}`);
    } else {
      if (Object.keys(s.env ?? {}).length) continue;
      out.push(`mcp_servers.${n}.command=${JSON.stringify(s.command)}`, `mcp_servers.${n}.args=${JSON.stringify(s.args ?? [])}`);
    }
  }
  return out;
}

const INIT = { jsonrpc: "2.0", id: 1, method: "initialize", params: { protocolVersion: "2025-03-26", capabilities: {}, clientInfo: { name: "fluma", version: "1" } } };
const LIST = { jsonrpc: "2.0", id: 2, method: "tools/list", params: {} };
const INITED = { jsonrpc: "2.0", method: "notifications/initialized" };

/** 연결 시험 → { ok, tools: [이름], server, error } */
export async function testMcp(name, env) {
  const { servers } = loadMcp();
  const s = servers[name]; if (!s) return { ok: false, error: "없는 서버입니다" };
  const r = s.type === "http" ? await testHttp(s) : await testStdio(s, env);
  servers[name] = { ...s, lastTest: { at: Date.now(), ok: r.ok, tools: r.tools?.length ?? 0, error: r.error ?? null } };
  saveMcp({ servers });
  return r;
}

function testStdio(s, env) {
  return new Promise((resolve) => {
    let child;
    try { child = spawn(s.command, s.args ?? [], { env: { ...env, ...(s.env ?? {}) }, stdio: ["pipe", "pipe", "pipe"], detached: process.platform !== "win32" }); }
    catch (e) { resolve({ ok: false, error: String(e.message || e) }); return; }
    let buf = "", err = "", server = null, done = false;
    const finish = (r) => { if (done) return; done = true; clearTimeout(t); try { process.kill(-child.pid, "SIGTERM"); } catch { try { child.kill(); } catch { /* 끝남 */ } } resolve(r); };
    const t = setTimeout(() => finish({ ok: false, error: server ? "도구 목록 응답이 없습니다(20초)" : `응답이 없습니다(20초)${err ? ` — ${err.trim().split("\n").slice(-2).join(" ")}` : ""}` }), 20000);
    child.on("error", (e) => finish({ ok: false, error: e.code === "ENOENT" ? `명령을 찾을 수 없습니다: ${s.command}` : String(e.message || e) }));
    child.on("close", (code) => finish({ ok: false, error: `서버가 끝났습니다(코드 ${code})${err ? ` — ${err.trim().split("\n").slice(-2).join(" ")}` : ""}` }));
    child.stderr.on("data", (b) => { err = (err + b).slice(-2000); });
    child.stdout.on("data", (b) => {
      buf += b; let i;
      while ((i = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, i).trim(); buf = buf.slice(i + 1); if (!line) continue;
        let m; try { m = JSON.parse(line); } catch { continue; }
        if (m.id === 1) {
          if (m.error) return finish({ ok: false, error: m.error.message || "초기화 실패" });
          server = m.result?.serverInfo?.name ?? null;
          child.stdin.write(JSON.stringify(INITED) + "\n" + JSON.stringify(LIST) + "\n");
        } else if (m.id === 2) {
          return finish(m.error ? { ok: false, server, error: m.error.message } : { ok: true, server, tools: (m.result?.tools ?? []).map((x) => x.name) });
        }
      }
    });
    child.stdin.write(JSON.stringify(INIT) + "\n");
  });
}

async function testHttp(s) {
  const post = async (body, sid) => {
    const r = await fetch(s.url, { method: "POST", signal: AbortSignal.timeout(15000),
      headers: { "content-type": "application/json", accept: "application/json, text/event-stream", ...(sid ? { "mcp-session-id": sid } : {}), ...(s.headers ?? {}) }, body: JSON.stringify(body) });
    const text = await r.text();
    if (!r.ok) throw new Error(`HTTP ${r.status} ${text.slice(0, 200)}`);
    // SSE 로 오면 data: 줄에서 꺼낸다
    const json = r.headers.get("content-type")?.includes("event-stream") ? text.split("\n").filter((l) => l.startsWith("data:")).map((l) => l.slice(5).trim()).filter(Boolean).at(-1) : text;
    return { msg: json ? JSON.parse(json) : {}, sid: r.headers.get("mcp-session-id") };
  };
  try {
    const a = await post(INIT);
    if (a.msg.error) return { ok: false, error: a.msg.error.message };
    await post(INITED, a.sid).catch(() => {});
    const b = await post(LIST, a.sid);
    return b.msg.error ? { ok: false, error: b.msg.error.message } : { ok: true, server: a.msg.result?.serverInfo?.name ?? null, tools: (b.msg.result?.tools ?? []).map((x) => x.name) };
  } catch (e) { return { ok: false, error: String(e.message || e) }; }
}

export const hasMcpFile = () => existsSync(MCP_FILE);
