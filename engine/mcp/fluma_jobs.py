"""MCP 작업 대기열 — 몇 분 걸리는 일(제작 · 렌더 · 레퍼런스 분석)을 작업 id 로 돌린다.

설계(볼트 02 Architecture/MCP 전환 설계):
  · 파일로 상태를 남긴다: data/workspace/jobs/<id>/job.json + job.log. MCP 서버(에이전트 세션)가 꺼져도 작업은 계속 돌고,
    다른 세션 · 스튜디오가 같은 상태를 읽는다.
  · 작업마다 부모와 끊긴 실행기(fluma_jobrun.py)가 명령을 띄우고, 진행률 · 결과 블록(FLUMA_RESULT …)을 job.json 에 적는다.
  · 무거운 작업(heavy)은 동시에 FLUMA_HEAVY_SLOTS 개(기본 1)만, 그리고 쓸 수 있는 메모리가 mem_gb 이상일 때만 시작(입장 제어).
  · 같은 key(예: produce:<id>)의 작업이 아직 돌면 새로 띄우지 않고 그 작업을 돌려준다(두 번 눌러 겹치는 렌더 방지).
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
from detach import alive, kill_tree, spawn_detached  # noqa: E402

JOBS = Path(os.environ.get("FLUMA_JOBS_DIR") or ROOT / "data" / "workspace" / "jobs")   # 테스트는 임시 폴더로
PY = sys.executable
ACTIVE = ("queued", "waiting", "running")
FINAL = ("done", "error", "needs_input", "canceled")


def _rel(p: Path) -> str:
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _path(jid: str) -> Path:
    if not jid or not all(c.isalnum() or c in "-_" for c in jid):
        raise ValueError("작업 id 형식이 올바르지 않습니다")
    return JOBS / jid / "job.json"


def read(jid: str) -> dict:
    p = _path(jid)
    try:
        return json.loads(p.read_text("utf-8"))
    except FileNotFoundError:
        raise ValueError(f"없는 작업입니다: {jid}") from None
    except (OSError, ValueError):
        time.sleep(0.05)                              # 실행기가 쓰는 도중 — 한 번 더
        return json.loads(p.read_text("utf-8"))


def write(job: dict) -> None:
    p = _path(job["id"])
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(job, ensure_ascii=False, indent=1), "utf-8")
    os.replace(tmp, p)


def _settle(job: dict) -> dict:
    """도는 중으로 적혀 있는데 실행기가 죽었으면 오류로 정리(전원 끔 · 강제 종료)"""
    if job.get("status") in ACTIVE and job.get("runner_pid") and not alive(job["runner_pid"]):
        time.sleep(0.3)
        job = read(job["id"])
        if job.get("status") in ACTIVE:
            job.update(status="error", error="실행기가 결과 없이 끝났습니다(강제 종료 · 재부팅)", ended=_now())
            write(job)
    return job


def get(jid: str) -> dict:
    return _settle(read(jid))


def list_jobs(project: str | None = None, active_only: bool = False, limit: int = 20) -> list[dict]:
    if not JOBS.exists():
        return []
    out = []
    for d in sorted(JOBS.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            j = _settle(read(d.name))
        except (ValueError, OSError):
            continue
        if project and j.get("project") != project:
            continue
        if active_only and j.get("status") not in ACTIVE:
            continue
        out.append(j)
        if len(out) >= limit:
            break
    return out


def submit(kind: str, cmd: list[str], *, project: str | None = None, label: str = "", key: str | None = None,
           heavy: bool = True, mem_gb: float = 2.0, timeout: int = 3600) -> dict:
    """작업을 띄우고 job 을 돌려준다(이미 같은 key 가 돌고 있으면 그 job 에 joined=True)"""
    if key:
        for j in list_jobs(active_only=True, limit=200):
            if j.get("key") == key:
                return {**j, "joined": True}
    JOBS.mkdir(parents=True, exist_ok=True)
    jid = time.strftime("%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    (JOBS / jid).mkdir()
    job = {"id": jid, "kind": kind, "label": label or kind, "project": project, "key": key, "cmd": cmd, "heavy": heavy,
           "mem_gb": mem_gb, "timeout": timeout, "status": "queued", "created": _now(), "started": None, "ended": None,
           "progress": None, "stage": None, "result": None, "error": None, "log": _rel(JOBS / jid / "job.log")}
    write(job)
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    pid = spawn_detached([PY, str(Path(__file__).with_name("fluma_jobrun.py")), jid], JOBS / jid / "runner.log", env, ROOT)
    job = read(jid)
    job["runner_pid"] = pid
    write(job)
    return job


def cancel(jid: str) -> dict:
    job = get(jid)
    if job.get("status") in FINAL:
        return job
    job.update(status="canceled", ended=_now(), error="취소했습니다")   # 먼저 적는다 — 실행기가 자식이 죽은 것을 '오류'로 적지 않게
    write(job)
    for pid in (job.get("runner_pid"), job.get("child_pid")):          # 실행기 = 프로세스 그룹 리더(자식 포함)
        if pid:
            kill_tree(int(pid))
    return read(jid)


def wait(jid: str, timeout: float = 50.0) -> dict:
    """끝나거나 timeout 초가 될 때까지 기다린다(MCP 호출 시간 제한에 안 걸리게 짧게 — 안 끝났으면 다시 부르면 됨)"""
    t0 = time.time()
    while True:
        job = get(jid)
        if job.get("status") in FINAL or time.time() - t0 >= timeout:
            return job
        time.sleep(1.0)


def log_tail(jid: str, lines: int = 30) -> str:
    p = JOBS / jid / "job.log"
    try:
        return "\n".join(p.read_text("utf-8", errors="replace").splitlines()[-lines:])
    except OSError:
        return ""


def brief(job: dict) -> dict:
    """에이전트에게 돌려줄 짧은 모양(명령 · 내부 pid 는 뺀다)"""
    keys = ("id", "kind", "label", "project", "status", "stage", "progress", "created", "started", "ended", "result", "error", "log", "joined", "waiting_for", "peak_mem_mb")
    out = {k: job[k] for k in keys if job.get(k) not in (None, "", [])}
    if job.get("started") and job.get("status") in ACTIVE:
        out["elapsed_s"] = int(time.time() - time.mktime(time.strptime(job["started"], "%Y-%m-%dT%H:%M:%S")))
    return out
