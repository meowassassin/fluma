#!/usr/bin/env python3
"""렌더 엔진 · 음성 엔진 설치기 — 설정 화면의 '설치' 버튼이 부른다. Linux · macOS · Windows 공통.

  python3 engine/core/install.py voices supertonic
  python3 engine/core/install.py --plan engines ffmpeg     # 무엇을 할지만 출력

설치 방법은 각 폴더의 engine.json / voice.json 의 "setup":
  venv      : <폴더>/.venv 에 파이썬 패키지 (uv 가 있으면 uv, 없으면 표준 venv + pip). torch:"cpu" 면 CPU 휠(리눅스 · 윈도우)
  npm       : <폴더> 에서 npm install
  container : engine.json 의 image 를 podman 또는 docker 로 받음
  system    : 운영체제 패키지 (관리자 권한이 필요하면 명령만 안내)
  manual    : 자동 설치가 어려움 — 명령만 안내
성공하고 import 확인까지 끝나면 <폴더>/.installed 를 남긴다 (빈 가상환경을 '사용 가능'으로 보지 않게).
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())  # 저장소 루트(engine/paths.py 가 있는 곳)
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401  engine 아래 묶음들을 import 경로에
from platform_util import ARCH, OS, venv_python, which  # noqa: E402


def say(msg):
    print(msg, flush=True)


def sh(cmd, cwd=None, env=None):
    """명령 실행 + 줄마다 그대로 보여 줌 (설정 화면 진행 표시)."""
    say("$ " + " ".join(str(c) for c in cmd))
    p = subprocess.Popen([str(c) for c in cmd], cwd=cwd, env={**os.environ, **(env or {})}, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                         shell=OS == "windows" and str(cmd[0]).lower().endswith((".cmd", ".bat")))
    for line in p.stdout:
        line = line.rstrip()
        if line:
            say("  " + line[-300:])
    if p.wait() != 0:
        raise SystemExit(f"실패 (exit {p.returncode}): {' '.join(str(c) for c in cmd[:4])} …")


def pkg_manager():
    if OS == "mac":
        return "mac"
    if OS == "windows":
        return "windows"
    return "linux-apt" if which("apt") else "linux-dnf" if which("dnf") else "linux-apt"


# ---------- 방식별 ----------
def do_venv(folder: Path, st: dict):
    py = venv_python(folder)
    uv = which("uv")
    if uv:
        sh([uv, "venv", "--allow-existing", "--python", st.get("python", "3.12"), str(folder / ".venv")])
        pip = [uv, "pip", "install", "--python", str(py)]
    else:
        say(f"uv 가 없어 표준 venv 로 만듭니다 (권장 파이썬 {st.get('python', '3.12')}, 지금 {sys.version.split()[0]})")
        sh([sys.executable, "-m", "venv", str(folder / ".venv")])
        sh([py, "-m", "pip", "install", "-U", "pip"])
        pip = [py, "-m", "pip", "install"]
    pk = list(st.get("packages", []))
    extra = []
    if st.get("torch") == "cpu" and OS in ("linux", "windows"):   # 맥은 기본 휠이 CPU · MPS
        extra = (["--index-strategy", "unsafe-best-match"] if uv else []) + ["--extra-index-url", "https://download.pytorch.org/whl/cpu"]
    sh(pip + extra + pk)
    for post in st.get("post", []):
        sh([py, *post])
    if st.get("check"):
        sh([py, "-c", st["check"]])


def do_npm(folder: Path, st: dict):
    npm = which("npm")
    if not npm:
        raise SystemExit("npm 이 없습니다 — Node.js(https://nodejs.org) 를 먼저 설치하세요")
    sh([npm, "install", "--no-audit", "--no-fund"], cwd=folder)


def do_container(folder: Path, st: dict, meta: dict):
    rt = which("podman") or which("docker")
    if not rt:
        raise SystemExit("podman 또는 docker 가 필요합니다 — macOS · Windows 는 Docker Desktop(https://www.docker.com/products/docker-desktop), 리눅스는 podman 패키지")
    sh([rt, "pull", meta["image"]])


def do_system(folder: Path, st: dict):
    if st.get("bin") and which(st["bin"]):
        say(f"{st['bin']} 이(가) 이미 있습니다: {which(st['bin'])}")
        return
    cmd = st["steps"].get(pkg_manager()) or next(iter(st["steps"].values()))
    if cmd.startswith("sudo"):
        raise SystemExit(f"관리자 권한이 필요합니다. 터미널에서 직접 실행하세요:\n  {cmd}")
    sh(cmd.split())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=["engines", "voices"])
    ap.add_argument("name")
    ap.add_argument("--plan", action="store_true")
    a = ap.parse_args()
    folder = (ROOT / "engine" / a.name / "renderer") if a.kind == "engines" else (ROOT / "engine" / "voice" / "engines" / a.name)
    meta_p = folder / ("engine.json" if a.kind == "engines" else "voice.json")
    if not meta_p.exists():
        raise SystemExit(f"없음: {meta_p}")
    meta = json.loads(meta_p.read_text(encoding="utf-8"))
    st = meta.get("setup") or {}
    t = st.get("type")
    say(f"[설치] {meta.get('title', a.name)} · 방식 {t} · {OS} {ARCH}")
    if a.plan or t == "manual":
        steps = st.get("steps", {})
        say("명령: " + (steps.get(pkg_manager()) or steps.get("all") or json.dumps(st, ensure_ascii=False)))
        if t == "manual":
            raise SystemExit("자동 설치가 어려운 엔진입니다 — 위 명령을 직접 실행하세요")
        return
    (folder / ".installed").unlink(missing_ok=True)
    {"venv": lambda: do_venv(folder, st), "npm": lambda: do_npm(folder, st), "container": lambda: do_container(folder, st, meta), "system": lambda: do_system(folder, st)}[t]()
    (folder / ".installed").write_text(json.dumps({"os": OS, "arch": ARCH}), encoding="utf-8")
    say(f"[완료] {meta.get('title', a.name)} 설치됨")


if __name__ == "__main__":
    main()
