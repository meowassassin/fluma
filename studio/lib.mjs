// 서버 공용 도구: 오류 봉투 · id 검사 · 원자적 쓰기 · 하위 프로세스(프로세스 그룹 종료 · 시간 제한)
import { spawn } from "node:child_process";
import { promises as fs, existsSync } from "node:fs";
import path from "node:path";
import { randomUUID } from "node:crypto";

/** 상태 코드 · 짧은 코드 · 사람이 읽는 한국어 문장. 오류 미들웨어가 {error:{code,message}} 로 바꾼다 */
export class HttpError extends Error {
  constructor(status, code, message, detail) { super(message); this.status = status; this.code = code; this.detail = detail; }
}
export const bad = (message, code = "bad_request") => new HttpError(400, code, message);
export const notFound = (message = "찾을 수 없습니다", code = "not_found") => new HttpError(404, code, message);
export const conflict = (message, code = "conflict") => new HttpError(409, code, message);

/** 비동기 라우트의 거부를 오류 미들웨어로 넘긴다 (Express 4 는 스스로 잡지 않음) */
export const ah = (fn) => (req, res, next) => { Promise.resolve(fn(req, res, next)).catch(next); };

export function sendError(res, status, code, message, detail) {
  if (res.headersSent) { try { res.end(); } catch { /* 이미 닫힘 */ } return; }
  const error = { code, message };
  if (detail) error.detail = String(detail).slice(0, 300);
  res.status(status).json({ error });
}

// ---------- id · 경로 ----------
export const ID_RE = /^[a-z0-9][a-z0-9_-]{0,80}$/;
/** 프로젝트 id (영상 · 시스템 대화 `_workspace` 포함 여부는 allowSystem) */
export function isId(id, { allowSystem = false } = {}) {
  if (typeof id !== "string") return false;
  if (allowSystem && /^_[a-z0-9][a-z0-9_-]{0,40}$/.test(id)) return true;
  return ID_RE.test(id);
}
export function checkId(id, opts) { if (!isId(id, opts)) throw bad("올바르지 않은 id 입니다", "bad_id"); return id; }
/** base 안의 경로만 (../ 탈출 방지) */
export function within(base, ...parts) {
  const b = path.resolve(base);
  const p = path.resolve(b, ...parts);
  if (p !== b && !p.startsWith(b + path.sep)) throw bad("허용되지 않은 경로입니다", "bad_path");
  return p;
}

// ---------- 파일 ----------
/** 임시 파일에 쓰고 rename (중간에 끊겨도 반쯤 쓴 파일이 남지 않음) */
export async function atomicWrite(file, data, { mode } = {}) {
  await fs.mkdir(path.dirname(file), { recursive: true });
  const tmp = `${file}.${process.pid}.${randomUUID().slice(0, 6)}.tmp`;
  await fs.writeFile(tmp, data, mode ? { mode } : undefined);
  if (mode) await fs.chmod(tmp, mode).catch(() => {});
  await fs.rename(tmp, file);
}
export async function readJson(file, fallback = null) {
  try { return JSON.parse(await fs.readFile(file, "utf8")); } catch { return fallback; }
}
export const exists = (p) => existsSync(p);

// ---------- 하위 프로세스 ----------
/** 프로세스 그룹째 끈다 (python → chrome · ffmpeg 자식까지). SIGTERM 뒤 5초 지나면 SIGKILL */
export function killTree(child) {
  if (!child || child.exitCode != null || child.signalCode != null) return;
  const sig = (s) => { try { process.kill(-child.pid, s); } catch { try { child.kill(s); } catch { /* 이미 끝남 */ } } };
  sig("SIGTERM");
  const t = setTimeout(() => sig("SIGKILL"), 5000); t.unref();
}

/**
 * 하위 프로세스 실행. { code, out, err, timedOut, canceled }.
 * detached(프로세스 그룹) · 시간 제한 · AbortSignal(취소 · 클라이언트 연결 끊김) 지원. onLine 은 줄마다.
 */
export function run(cmd, args, { cwd, env, onLine, timeout = 0, signal, onSpawn, maxBuf = 4_000_000 } = {}) {
  return new Promise((resolve) => {
    let child;
    try {
      child = spawn(cmd, args, { cwd, env: { PYTHONUNBUFFERED: "1", PYTHONUTF8: "1", PYTHONIOENCODING: "utf-8", ...(env || process.env) }, shell: false, detached: process.platform !== "win32" });
    } catch (e) { resolve({ code: -1, out: "", err: String(e), timedOut: false, canceled: false }); return; }
    onSpawn?.(child);
    let out = "", err = "", timedOut = false, canceled = false, done = false;
    const tails = { o: "", e: "" };
    const feed = (buf, isErr) => {
      const s = buf.toString();
      if (isErr) { if (err.length < maxBuf) err += s; } else if (out.length < maxBuf) out += s;
      if (!onLine) return;
      const k = isErr ? "e" : "o";
      const lines = (tails[k] + s).split(/\r?\n|\r/);
      tails[k] = lines.pop();
      for (const l of lines) if (l.trim()) onLine(l, isErr);
    };
    child.stdout?.on("data", (b) => feed(b, false));
    child.stderr?.on("data", (b) => feed(b, true));
    const timer = timeout ? setTimeout(() => { timedOut = true; killTree(child); }, timeout) : null;
    const onAbort = () => { canceled = true; killTree(child); };
    if (signal) { if (signal.aborted) onAbort(); else signal.addEventListener("abort", onAbort, { once: true }); }
    const finish = (code) => {
      if (done) return; done = true;
      if (timer) clearTimeout(timer);
      signal?.removeEventListener?.("abort", onAbort);
      for (const k of ["o", "e"]) if (onLine && tails[k].trim()) onLine(tails[k], k === "e");
      resolve({ code, out, err, timedOut, canceled });
    };
    child.on("close", (code) => finish(code));
    child.on("error", (e) => { err += String(e); finish(-1); });
  });
}

/** 요청이 끊기면 abort 되는 신호 (응답을 다 보낸 뒤의 close 는 무시) */
export function requestSignal(req, res) {
  const ac = new AbortController();
  res.on("close", () => { if (!res.writableFinished) ac.abort(); });
  return ac.signal;
}

/** 마지막 몇 줄만 (서버 로그 · 작업 실패 detail 용) */
export const tail = (s, n = 6) => String(s || "").trim().split("\n").filter(Boolean).slice(-n).join("\n");

/** 사람 개입 기록 — 영상마다 사람이 직접 한 일(승인 · 채팅 · 직접 편집 · 되돌리기 · 올리기 · 음성 다시 · 렌더 누름)을 한 줄씩.
 *  data/workspace/effort/<id>.jsonl → engine/core/effort.py 가 '사람 개입 n번 · 걸린 시간 · 비용'으로 묶는다(공개 데모 결과물 옆 숫자, 2026-11-02).
 *  에이전트가 스스로 한 일은 세지 않는다 — 서버 API 는 사람이 화면에서 누른 것만 지난다 */
export async function logEffort(root, id, kind, detail = "") {
  try {
    const dir = path.join(root, "workspace", "effort");
    await fs.mkdir(dir, { recursive: true });
    await fs.appendFile(path.join(dir, `${id}.jsonl`), JSON.stringify({ at: new Date().toISOString(), kind, detail: String(detail).slice(0, 200) }) + "\n");
  } catch { /* 기록 실패가 작업을 막지 않는다 */ }
}
