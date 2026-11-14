// 운영체제 차이를 한곳에서 (Node 쪽). Linux · macOS · Windows 에서 같은 서버가 돌게.
import { existsSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import os from "node:os";

export const OS = process.platform === "win32" ? "windows" : process.platform === "darwin" ? "mac" : "linux";

/** 알려진 일반적인 CLI 설치 경로 후보 (PATH 누락 환경 대비 fallback) */
function getStandardPaths() {
  const home = os.homedir();
  const dirs = [];
  if (OS === "windows") {
    if (process.env.APPDATA) dirs.push(path.join(process.env.APPDATA, "npm"));
    if (process.env.LOCALAPPDATA) dirs.push(path.join(process.env.LOCALAPPDATA, "Programs"));
  } else {
    dirs.push(
      path.join(home, ".local", "bin"),
      path.join(home, ".npm-global", "bin"),
      path.join(home, ".cargo", "bin"),
      "/usr/local/bin",
      "/usr/bin",
      "/bin"
    );
    // fnm / nvm 경로 자동 보강
    const fnmCurrent = path.join(home, ".local", "share", "fnm", "current", "bin");
    if (existsSync(fnmCurrent)) dirs.push(fnmCurrent);
  }
  return dirs;
}

/** PATH 에서 실행 파일 찾기 (bash 없이). Windows 는 PATHEXT(.exe .cmd …)까지. 누락 시 표준 설치 경로 자동 fallback */
export function which(name) {
  const exts = OS === "windows" ? (process.env.PATHEXT || ".EXE;.CMD;.BAT").split(";").map((e) => e.toLowerCase()) : [""];
  const searchDirs = [
    ...(process.env.PATH || "").split(path.delimiter),
    ...getStandardPaths()
  ].filter(Boolean);

  const seen = new Set();
  for (const dir of searchDirs) {
    if (seen.has(dir)) continue;
    seen.add(dir);
    for (const e of exts) {
      const p = path.join(dir, name + e);
      try {
        if (existsSync(p)) {
          if (OS !== "windows") {
            try {
              const st = statSync(p);
              if (st.isFile()) return p;
            } catch {
              continue;
            }
          }
          return p;
        }
      } catch {}
    }
  }

  // Claude 특화 fallback: ~/.local/share/claude/versions 최신 버전 탐색
  if (name === "claude" && OS !== "windows") {
    const versionsDir = path.join(os.homedir(), ".local", "share", "claude", "versions");
    try {
      if (existsSync(versionsDir)) {
        const files = readdirSync(versionsDir).sort().reverse();
        for (const file of files) {
          const p = path.join(versionsDir, file);
          try {
            if (statSync(p).isFile()) return p;
          } catch {}
        }
      }
    } catch {}
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
