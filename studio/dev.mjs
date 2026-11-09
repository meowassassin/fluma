// 개발 서버 실행기 — API(node server.mjs) 와 화면(vite)을 함께 띄우고, 하나가 끝나면 둘 다 끈다.
// 2026-11-09: 예전엔 concurrently 패키지에 기대어, 개발용 패키지를 안 깔았거나(npm install 전 · --omit=dev) 윈도우에서 'concurrently 가 없다'며 멈췄다.
// 외부 패키지 없이 Node 만으로 — Linux · macOS · Windows 같은 동작.
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const vite = path.join(here, "node_modules", "vite", "bin", "vite.js");
if (!existsSync(path.join(here, "node_modules", "express")) || !existsSync(vite)) {
  console.error("\n[fluma] 화면 패키지가 아직 없습니다 — 먼저 한 번 설치하세요:\n" +
    "        npm --prefix studio install          (저장소 폴더에서)\n" +
    "        또는  python engine/doctor.py --fix   (파이썬 · 패키지까지 한 번에)\n" +
    "[fluma] Studio packages are missing — run `npm --prefix studio install` (or `python engine/doctor.py --fix`) once.\n");
  process.exit(1);
}

const procs = [];
let stopping = false;
const color = { api: "\x1b[34m", web: "\x1b[32m" };
function run(name, args) {
  // node 실행 파일로 직접(윈도우의 .cmd 셸 문제 없음)
  const p = spawn(process.execPath, args, { cwd: here, env: process.env, stdio: ["inherit", "pipe", "pipe"], windowsHide: true });
  const tag = `${color[name] || ""}[${name}]\x1b[0m `;
  const pipe = (src, dst) => {
    let buf = "";
    src.on("data", (d) => {
      buf += d.toString();
      const lines = buf.split(/\r?\n/); buf = lines.pop();
      for (const l of lines) dst.write(tag + l + "\n");
    });
    src.on("end", () => { if (buf) dst.write(tag + buf + "\n"); });
  };
  pipe(p.stdout, process.stdout); pipe(p.stderr, process.stderr);
  p.on("exit", (code, sig) => {
    if (!stopping) {
      console.error(`${tag}끝남(${sig || code}) — 나머지도 끕니다`);
      stop(code ?? 1);
    }
  });
  procs.push(p);
}
function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  for (const p of procs) { try { p.kill(); } catch { /* 이미 끝남 */ } }
  setTimeout(() => process.exit(code), 500).unref();
}
process.on("SIGINT", () => stop(0));
process.on("SIGTERM", () => stop(0));

run("api", ["server.mjs"]);
run("web", [vite, "--port", "4311"]);
