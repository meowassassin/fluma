// 오래 걸리는 작업(렌더 · 초안 · 정지 화면 · 빌드 · 음성 · 설치 · 생성 · 업로드)의 공통 대기열.
//  - 무거운 작업(크롬 · ffmpeg · TTS)은 한 번에 하나, 가벼운 작업은 둘. 같은 영상의 정지 화면 · 빌드는 순서대로(같은 작업 폴더).
//  - 상태 · 진행률 · 단계 · 로그를 SSE 로 보낸다(이벤트 id → 다시 붙어도 이어 받음). 취소는 프로세스 그룹째.
import { randomUUID } from "node:crypto";
import { run as runProc, tail } from "./lib.mjs";

const CLASS = { xray: "heavy", render: "heavy", draft: "heavy", voice: "heavy", generate: "heavy", element: "heavy", upload: "heavy", install: "install", still: "light", build: "light" };
const LIMIT = { heavy: 1, light: 2, install: 1 };
const TIMEOUT = { xray: 20 * 60e3, render: 30 * 60e3, draft: 15 * 60e3, still: 3 * 60e3, build: 3 * 60e3, voice: 10 * 60e3, generate: 15 * 60e3, element: 30 * 60e3, upload: 10 * 60e3, install: 60 * 60e3 };
const TERMINAL = new Set(["done", "failed", "canceled"]);
const MAX_LOG = 500;

export function createJobs({ onChange } = {}) {
  const jobs = new Map();
  const queues = Object.fromEntries(Object.keys(LIMIT).map((k) => [k, { running: 0, wait: [] }]));
  const projectTail = new Map();   // 같은 영상의 가벼운 작업(정지 화면 · 빌드)을 줄 세운다

  const pub = (j) => ({ id: j.id, type: j.type, project: j.project, label: j.label, status: j.status, progress: j.progress, stage: j.stage,
    created: j.created, started: j.started, ended: j.ended, result: j.result, error: j.error, detail: j.detail });

  function push(j, payload) {
    if (payload.type === "log") { j.logCount++; if (j.logCount > MAX_LOG) { const k = j.events.findIndex((e) => e.payload.type === "log"); if (k >= 0) j.events.splice(k, 1); } }
    const ev = { id: ++j.seq, payload };
    j.events.push(ev);
    const data = `id: ${ev.id}\ndata: ${JSON.stringify(payload)}\n\n`;
    for (const c of j.clients) c.write(data);
    if (payload.type !== "log") onChange?.(pub(j));
  }
  function endClients(j) {
    for (const c of j.clients) { c.write("event: end\ndata: {}\n\n"); c.end(); }
    j.clients.clear();
  }
  function finish(j, status, { result, error, detail } = {}) {
    if (TERMINAL.has(j.status)) return;
    j.status = status; j.ended = Date.now();
    if (result) j.result = result;
    if (error) j.error = error;
    if (detail) j.detail = String(detail).slice(0, 300);
    if (status === "done") { j.progress = 1; push(j, { type: "done", ...(j.result || {}) }); }
    else if (status === "failed") push(j, { type: "failed", error: j.error || "작업이 실패했습니다", detail: j.detail });
    else push(j, { type: "canceled" });
    endClients(j);
    j.resolve(pub(j));
  }

  /** 대기열에서 꺼내 실행 */
  function pump(cls) {
    const q = queues[cls];
    while (q.running < LIMIT[cls] && q.wait.length) {
      const j = q.wait.shift();
      if (j.status !== "queued") continue;
      q.running++;
      start(j).finally(() => { q.running--; pump(cls); });
    }
  }
  async function start(j) {
    // 같은 영상의 가벼운 작업은 앞 작업이 끝날 때까지 기다린다
    if (j.serial) {
      const prev = projectTail.get(j.serialKey) || Promise.resolve();
      let release; const mine = new Promise((r) => { release = r; });
      projectTail.set(j.serialKey, prev.then(() => mine));
      await prev;
      try { await exec(j); } finally { release(); if (projectTail.get(j.serialKey) === mine) projectTail.delete(j.serialKey); }
    } else await exec(j);
  }
  async function exec(j) {
    if (j.status !== "queued") return;
    j.status = "running"; j.started = Date.now();
    push(j, { type: "progress", progress: j.progress, stage: j.stage || "시작" });
    const h = {
      job: j,
      signal: j.ac.signal,
      log: (line) => push(j, { type: "log", line: String(line).slice(0, 2000) }),
      progress: (p, stage) => {
        const np = p == null ? j.progress : Math.max(0, Math.min(1, p));
        if (np === j.progress && (stage ?? j.stage) === j.stage) return;
        j.progress = np; if (stage) j.stage = stage;
        push(j, { type: "progress", progress: j.progress, stage: j.stage });
      },
      /** 하위 프로세스: 취소 · 시간 제한 · 줄 로그가 작업에 묶인다 */
      run: (cmd, args, opts = {}) => runProc(cmd, args, {
        timeout: j.timeout, signal: j.ac.signal, ...opts,
        onLine: (l, isErr) => { h.log(l); opts.onLine?.(l, isErr); },
      }),
    };
    try {
      const r = await j.work(h);
      if (j.ac.signal.aborted) return finish(j, "canceled");
      if (r && r.timedOut) return finish(j, "failed", { error: "시간이 너무 오래 걸려 멈췄습니다", detail: tail(r.err) });
      if (r && r.error) return finish(j, "failed", { error: r.error, detail: r.detail });
      finish(j, "done", { result: r?.result || null });
    } catch (e) {
      if (j.ac.signal.aborted) return finish(j, "canceled");
      console.error(`[job ${j.type} ${j.id}]`, e);
      finish(j, "failed", { error: e?.message && /[가-힣]/.test(e.message) ? e.message : "작업 중 오류가 났습니다", detail: String(e?.stack || e).slice(0, 300) });
    }
  }

  /**
   * 작업 만들기. key 가 같은 진행 중 작업이 있으면 그것을 돌려준다(버튼 두 번 · 같은 빌드 동시 요청).
   * work(h) → { result?, error?, detail?, timedOut? }
   */
  function create({ type, project = null, label = "", key = null, serial = false, timeout, work }) {
    if (key) for (const j of jobs.values()) if (j.key === key && !TERMINAL.has(j.status)) return j;
    let resolve; const done = new Promise((r) => { resolve = r; });
    const j = { id: randomUUID(), type, project, label, key, status: "queued", progress: null, stage: "대기 중", created: Date.now(),
      started: null, ended: null, result: null, error: null, detail: null, events: [], seq: 0, logCount: 0, clients: new Set(),
      ac: new AbortController(), timeout: timeout ?? TIMEOUT[type] ?? 10 * 60e3, serial, serialKey: `${project}`, work, done, resolve, waiters: 0 };
    jobs.set(j.id, j);
    push(j, { type: "progress", progress: null, stage: "대기 중" });
    const cls = CLASS[type] || "light";
    queues[cls].wait.push(j);
    pump(cls);
    return j;
  }

  function cancel(id) {
    const j = jobs.get(id);
    if (!j || TERMINAL.has(j.status)) return false;
    j.ac.abort();
    if (j.status === "queued") finish(j, "canceled");
    return true;
  }

  /** 요청-응답으로 기다리는 작업: 모든 요청이 끊기면 취소 */
  async function waitFor(j, req, res) {
    j.waiters++;
    let gone = false;
    const onClose = () => { if (res.writableFinished || gone) return; gone = true; if (--j.waiters <= 0) cancel(j.id); };
    res.on("close", onClose);
    const r = await j.done;
    res.off("close", onClose);
    if (!gone) j.waiters--;
    return r;
  }

  function stream(j, req, res) {
    res.set({ "Content-Type": "text/event-stream", "Cache-Control": "no-cache", Connection: "keep-alive", "X-Accel-Buffering": "no" });
    res.flushHeaders();
    res.write("retry: 3000\n\n");
    const last = Number(req.headers["last-event-id"] || 0);
    for (const ev of j.events) if (ev.id > last) res.write(`id: ${ev.id}\ndata: ${JSON.stringify(ev.payload)}\n\n`);
    if (TERMINAL.has(j.status)) { res.write("event: end\ndata: {}\n\n"); return res.end(); }
    j.clients.add(res);
    const hb = setInterval(() => res.write(": hb\n\n"), 15000);
    req.on("close", () => { clearInterval(hb); j.clients.delete(res); });
  }

  // 끝난 작업은 30분 뒤 정리
  setInterval(() => {
    const now = Date.now();
    for (const [id, j] of jobs) if (TERMINAL.has(j.status) && now - j.ended > 30 * 60e3) jobs.delete(id);
  }, 5 * 60e3).unref();

  return {
    create, cancel, waitFor, stream,
    get: (id) => jobs.get(id) || null,
    pub,
    list: ({ project, type } = {}) => [...jobs.values()].filter((j) => (!project || j.project === project) && (!type || j.type === type)).map(pub).sort((a, b) => b.created - a.created),
    active: (project) => [...jobs.values()].filter((j) => j.project === project && !TERMINAL.has(j.status)).map(pub),
    TERMINAL,
  };
}
