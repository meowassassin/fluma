#!/usr/bin/env python3
"""외부 에이전트(내 Claude Code · Codex)용 — Fluma 를 설치 · 실행하고, 주제를 주면 첫 영상 기획까지 시작한다.
docs/skill/SKILL.md 가 이 도우미를 부른다. 결과는 engine/core/result.py 규약(0 · 10 · 1, FLUMA_RESULT 블록).

  python3 engine/fluma_agent.py start [--topic "주제"] [--local] [--build]

순서
  1. Docker 가 있으면: 미리 빌드한 이미지(ghcr.io/meowassassin/fluma)를 받아 띄운다(없거나 --build 면 직접 빌드).
     Docker 가 없거나 --local 이면: doctor.py --fix(전부 설치) 뒤 개발 서버를 띄운다
  2. http://localhost:4311 이 답할 때까지 기다린다
  3. --topic 이 있으면 새 영상을 만들고 그 주제로 기획 대화를 시작한다(plan 스킬) → 스튜디오 주소를 돌려준다
에이전트 로그인(Claude Code · Codex)은 사용자 컴퓨터의 것을 그대로 쓴다. 로그인이 없으면 종료 10 으로 알린다.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import string
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())  # 저장소 루트(engine/paths.py 가 있는 곳)
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401  engine 아래 묶음들을 import 경로에
from result import fail, needs_input, ok  # noqa: E402

URL = "http://localhost:4311"


def up(timeout: float = 600) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with urllib.request.urlopen(f"{URL}/api/engines", timeout=5) as r:
                if r.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(3)
    return False


def sh(cmd: list[str], timeout: int = 3600) -> subprocess.CompletedProcess:
    print(f"[fluma] {' '.join(cmd[:4])} …", flush=True)
    if cmd[:2] == ["docker", "compose"]:            # compose 파일은 docker/ 에 있다
        cmd = ["docker", "compose", "-f", str(ROOT / "docker" / "docker-compose.yml"), *cmd[2:]]
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)


def start_docker(build: bool) -> None:
    if not build:
        r = sh(["docker", "compose", "pull"], timeout=3600)        # 미리 빌드한 이미지(약 15GB — 처음 한 번)
        if r.returncode != 0:
            print("[fluma] 미리 빌드한 이미지를 받지 못해 직접 빌드합니다", flush=True)
            build = True
    if build:
        r = sh(["docker", "compose", "build"], timeout=5400)
        if r.returncode != 0:
            fail("fluma_agent", stage="docker build", error=(r.stderr or r.stdout).strip()[-300:])
    r = sh(["docker", "compose", "up", "-d"], timeout=600)
    if r.returncode != 0:
        msg = (r.stderr or r.stdout).strip()
        if "port is already allocated" in msg:
            fail("fluma_agent", stage="docker up", error="4311 포트를 다른 프로그램(다른 Fluma 등)이 쓰고 있습니다 — docker ps 로 확인해 그쪽을 내리세요")
        fail("fluma_agent", stage="docker up", error=msg[-300:])


def start_local() -> None:
    r = sh([sys.executable, "engine/doctor.py", "--fix"], timeout=5400)
    if r.returncode != 0:
        tail = (r.stdout + r.stderr).strip().splitlines()[-3:]
        if any("ffmpeg" in t or "Node" in t or "npm" in t for t in tail):
            needs_input("fluma_agent", needs=["ffmpeg · Node.js 20+ 설치(시스템 프로그램)"], how=" / ".join(tail))
        fail("fluma_agent", stage="install", error=" / ".join(tail))
    log = open(ROOT / "data" / "workspace" / "fluma-dev.log", "a") if (ROOT / "data" / "workspace").exists() else subprocess.DEVNULL
    subprocess.Popen(["npm", "--prefix", "web", "run", "dev"], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)


def logged_in() -> bool:
    """내 컴퓨터에 에이전트 로그인이 있나(파일이 있는지만 — 내용은 읽지 않는다)"""
    home = Path.home()
    return any(p.exists() for p in (home / ".claude" / ".credentials.json", home / ".claude.json", home / ".codex" / "auth.json")) \
        or bool(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"))


def first_video(topic: str) -> str:
    sid = time.strftime("%Y-%m-%d-") + "".join(random.choices(string.ascii_lowercase + string.digits, k=6)) + "-01"
    body = json.dumps({"message": f"{topic}\n\n이 주제로 쇼츠를 기획해 줘. 레퍼런스 쇼츠부터 찾아서 분석하고 훅 3안을 보여 줘.", "skill": "plan"}).encode()
    req = urllib.request.Request(f"{URL}/api/projects/{sid}/chat", data=body, method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        json.loads(r.read() or b"{}")
    return sid


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start"); s.add_argument("--topic"); s.add_argument("--local", action="store_true"); s.add_argument("--build", action="store_true")
    a = ap.parse_args()
    if not logged_in():
        needs_input("fluma_agent", needs=["Claude Code 또는 Codex 로그인"], how="터미널에서 `claude` 를 실행해 /login (또는 `codex login`) — 한 번만. 끝나면 같은 명령을 다시")
    already = up(timeout=3)
    if not already:
        docker = shutil.which("docker") and subprocess.run(["docker", "info"], capture_output=True).returncode == 0
        if docker and not a.local:
            start_docker(a.build)
        else:
            start_local()
        if not up():
            fail("fluma_agent", stage="start", error=f"{URL} 이 10분 안에 뜨지 않았습니다 — docker compose -f docker/docker-compose.yml logs 또는 data/workspace/fluma-dev.log 확인")
    if a.topic:
        try:
            sid = first_video(a.topic)
        except (urllib.error.URLError, OSError) as e:
            fail("fluma_agent", stage="first video", error=str(e))
        ok("fluma_agent", url=URL, video=sid, next=f"{URL} 을 열면 홈 대화에 기획이 진행 중입니다. 제작은 콘티를 확인한 뒤 '제작 시작'")
    ok("fluma_agent", url=URL, next=f"{URL} 을 열어 홈에 주제를 한 줄 적으세요")


if __name__ == "__main__":
    from result import run_main
    run_main("fluma_agent", main)
