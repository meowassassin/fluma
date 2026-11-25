#!/usr/bin/env python3
"""작업 실행기 — fluma_jobs.submit 이 부모와 끊어 띄운다. python3 fluma_jobrun.py <작업 id>

자리 · 메모리를 기다렸다가 명령을 띄우고, 기록을 읽어 진행률을 job.json 에 적고, 끝나면 결과 블록(FLUMA_RESULT · FLUMA_ERROR ·
FLUMA_NEEDS_INPUT)을 job.result 로 옮긴다. 이 프로세스가 프로세스 그룹 리더라 취소 때 그룹째 끈다.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from fluma_jobs import JOBS, ROOT, _now, read, write  # noqa: E402
from detach import kill_tree, tree_rss_mb, try_lock  # noqa: E402
from platform_util import mem_available_gb  # noqa: E402

SLOTS = max(1, int(os.environ.get("FLUMA_HEAVY_SLOTS", "1")))
FRAC = re.compile(r"(?:프레임|frame|장면|scene|step|단계)\D{0,4}(\d+)\s*/\s*(\d+)", re.I)
PCT = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%")
NOISE = re.compile(r"^(\s*$|\s*at |Traceback|  File |[a-z_]+=)")
FINAL = {"FLUMA_RESULT": "done", "FLUMA_ERROR": "error", "FLUMA_NEEDS_INPUT": "needs_input"}


def final_block(lines: list[str]) -> tuple[str, dict] | None:
    """마지막 결과 블록 → (상태, {키: 값 | [값…]})"""
    for i in range(len(lines) - 1, -1, -1):
        head = lines[i].strip()
        if head in FINAL:
            fields: dict = {}
            for ln in lines[i + 1:]:
                if "=" not in ln:
                    continue
                k, v = ln.split("=", 1)
                k, v = k.strip(), v.replace("⏎", "\n")
                if k in fields:
                    fields[k] = (fields[k] if isinstance(fields[k], list) else [fields[k]]) + [v]
                else:
                    fields[k] = v
                if k == "result_file":
                    break
            return FINAL[head], fields
    return None


def take_slot(job: dict):
    """무거운 작업 자리 + 메모리를 기다려 잡는다(잡은 잠금 파일을 돌려줌 — 프로세스가 끝나면 운영체제가 푼다)"""
    (JOBS / "_slots").mkdir(parents=True, exist_ok=True)
    while True:
        for k in range(SLOTS):
            h = try_lock(JOBS / "_slots" / f"heavy{k}.lock")
            if h:
                need = float(job.get("mem_gb") or 0)
                waited = 0.0
                while need and mem_available_gb(default=99) < need and waited < 600:   # 메모리가 비기를 최대 10분
                    _mark(job["id"], status="waiting", waiting_for=f"메모리 {need:.1f}GB (지금 {mem_available_gb(default=0):.1f}GB)")
                    time.sleep(5); waited += 5
                return h
        _mark(job["id"], status="waiting", waiting_for="앞의 무거운 작업이 끝나기를")
        time.sleep(2)


def _mark(jid: str, **kw) -> dict:
    j = read(jid)
    if j.get("status") == "canceled":
        sys.exit(0)
    j.update(kw)
    write(j)
    return j


def progress_of(lines: list[str], job: dict) -> tuple[str | None, float | None]:
    stage, frac = None, None
    for ln in reversed(lines[-60:]):
        s = ln.strip()
        if not s or NOISE.match(ln) or s.startswith(("FLUMA_", "status=", "result_file=")):
            continue
        if stage is None:
            stage = s[:160]
        m = FRAC.search(s)
        if m and int(m.group(2)) > 0:
            frac = min(1.0, int(m.group(1)) / int(m.group(2)))
            break
        m = PCT.search(s)
        if m and frac is None and float(m.group(1)) <= 100:
            frac = float(m.group(1)) / 100
            break
    if job.get("kind") == "produce" and job.get("project"):   # produce 는 단계 기록 파일이 더 정확
        try:
            import json
            pg = json.loads((ROOT / "data" / "workspace" / "progress" / f"{job['project']}.json").read_text("utf-8"))
            if pg.get("stage"):
                done = ", ".join(f"{k} {v:.0f}s" for k, v in (pg.get("done") or {}).items() if v >= 1)
                stage = f"{pg['stage']} 단계" + (f" (끝난 단계: {done})" if done else "") + (f" · {stage}" if stage else "")
        except (OSError, ValueError):
            pass
    return stage, (round(frac, 3) if frac is not None else None)


def main() -> int:
    jid = sys.argv[1]
    job = read(jid)
    lock = take_slot(job) if job.get("heavy") else None
    log = JOBS / jid / "job.log"
    env = {**os.environ, "FLUMA_PRODUCE_CHILD": "1", "FLUMA_JOB_ID": jid, "PYTHONUNBUFFERED": "1"}
    with log.open("w") as lf:
        child = subprocess.Popen(job["cmd"], cwd=ROOT, stdout=lf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=env)
    job = _mark(jid, status="running", started=_now(), child_pid=child.pid, waiting_for=None)
    t0, timeout = time.time(), int(job.get("timeout") or 3600)
    peak = 0.0
    while child.poll() is None:
        time.sleep(1.5)
        peak = max(peak, tree_rss_mb(child.pid))
        if time.time() - t0 > timeout:
            kill_tree(child.pid)
            _mark(jid, status="error", ended=_now(), error=f"시간 초과 {timeout}s")
            return 1
        try:
            lines = log.read_text("utf-8", errors="replace").splitlines()
        except OSError:
            continue
        stage, frac = progress_of(lines, job)
        j = read(jid)
        if j.get("status") == "canceled":
            kill_tree(child.pid)
            return 0
        if (stage, frac) != (j.get("stage"), j.get("progress")) or round(peak) > (j.get("peak_mem_mb") or 0) + 100:
            j.update(stage=stage, progress=frac, peak_mem_mb=round(peak))
            write(j)
    lines = log.read_text("utf-8", errors="replace").splitlines() if log.exists() else []
    fb = final_block(lines)
    if fb:
        status, fields = fb
        err = None if status == "done" else (fields.get("error") or fields.get("needs") or "실패")
        _mark(jid, status=status, ended=_now(), exit=child.returncode, result=fields, error=err, progress=1.0 if status == "done" else None, peak_mem_mb=round(peak))
    elif child.returncode == 0:
        last = next((ln.strip() for ln in reversed(lines) if ln.strip()), "")
        _mark(jid, status="done", ended=_now(), exit=0, result={"last": last}, progress=1.0, peak_mem_mb=round(peak))
    else:
        tail = "\n".join(ln for ln in lines[-15:] if ln.strip())
        _mark(jid, status="error", ended=_now(), exit=child.returncode, error=tail[-800:] or f"exit {child.returncode}", peak_mem_mb=round(peak))
    if lock:
        lock.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
