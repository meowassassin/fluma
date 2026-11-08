// 운영체제 차이를 한곳에서 (Node 쪽). Linux · macOS · Windows 에서 같은 서버가 돌게.
import { existsSync } from "node:fs";
import path from "node:path";

export const OS = process.platform === "win32" ? "windows" : process.platform === "darwin" ? "mac" : "linux";

/** PATH 에서 실행 파일 찾기 (bash 없이). Windows 는 PATHEXT(.exe .cmd …)까지 */
export function which(name) {
  const exts = OS === "windows" ? (process.env.PATHEXT || ".EXE;.CMD;.BAT").split(";").map((e) => e.toLowerCase()) : [""];
  for (const dir of (process.env.PATH || "").split(path.delimiter)) {
    for (const e of exts) {
      const p = path.join(dir, name + e);
      if (dir && existsSync(p)) return p;
    }
  }
  return null;
}

/** 파이썬: FLUMA_PYTHON > 저장소 .venv > python3 > python > py */
export function pythonCmd(root) {
  if (process.env.FLUMA_PYTHON) return process.env.FLUMA_PYTHON;
  const venv = OS === "windows" ? path.join(root, ".venv", "Scripts", "python.exe") : path.join(root, ".venv", "bin", "python");
  if (existsSync(venv)) return venv;
  // 시작 때 버전을 확인하려고 프로세스를 띄우지 않는다(서버를 막음) — 처음 찾은 것을 쓴다
  for (const n of ["python3", "python", "py"]) { const p = which(n); if (p) return p; }
  return "python3";
}

/** 실행 파일을 spawn 할 때: Windows 의 npm 설치본(.cmd/.bat)은 셸로만 실행된다 */
export function spawnTarget(bin) {
  const full = which(bin) || bin;
  return { cmd: full, shell: OS === "windows" && /\.(cmd|bat)$/i.test(full) };
}

export const venvBin = (root) => path.join(root, ".venv", OS === "windows" ? "Scripts" : "bin");
