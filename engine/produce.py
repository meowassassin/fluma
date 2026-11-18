#!/usr/bin/env python3
"""제작 한 줄 — 콘티 → 음성 → 검사 → 재료 · 초안 렌더 → 장면별 정지 화면 → 편집 밀도 · 템포, 정해진 순서로.
에이전트가 단계를 손으로 고르지 않게(같은 콘티면 누가 돌려도 같은 결과) — 에이전트는 막힌 곳만 고친다.

  python3 engine/produce.py data/storyboards/<id>.json [--scenes 1-3] [--aspect 9:16] [--no-audio] [--keep-going] [--preview-only] [--delivery]

기본은 납품 해상도 한 번 렌더(half 초안 아님). 개발만 FLUMA_MODE=draft.

결과(engine/core/result.py 규약)
  0  FLUMA_RESULT — file(완성) · media(영상 + 장면별 정지 화면) · warn(편집 밀도 · 템포 권고) · time(단계별 초)
  1  FLUMA_ERROR  — stage(audio · lint · render) · error(검사에서 걸린 규칙 · 렌더 오류 짧게)
  10 FLUMA_NEEDS_INPUT — 사용자만 줄 수 있는 것(사용자 녹화 L36 · 스톡 영상 키 L38)
검사(lint)의 실패(L 규칙)가 있으면 렌더하지 않고 멈춘다(--keep-going 이면 렌더까지). 권고(T 규칙)는 warn 으로만.
단계별 소요 시간은 data/workspace/results/produce-timings.jsonl 에 쌓인다(어디가 느린지 보려고).
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())  # 저장소 루트(engine/paths.py 가 있는 곳)
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401  engine 아래 묶음들을 import 경로에
from result import fail, needs_input, ok, running  # noqa: E402

PY = sys.executable
TIMES: dict[str, float] = {}


PROG: dict = {}


def progress(stage: str | None, running: bool = True, error: str | None = None) -> None:
    """진행 기록 data/workspace/progress/<id>.json — 스튜디오 파이프라인 그래프가 이걸 보고 '지금 도는 단계'를 칠한다(추측하지 않게).
    stage: 지금 도는 단계(없으면 None) · done: 끝난 단계와 걸린 초 · pid: 이 프로세스(죽었으면 화면이 무시)"""
    sid = PROG.get("sid")
    if not sid:
        return
    PROG.update(stage=stage, running=running, error=error, updated=time.time(), pid=os.getpid(), done=dict(TIMES))
    if stage and PROG.get("stage_name") != stage:
        PROG["stage_name"], PROG["stage_started"] = stage, time.time()
    try:
        f = ROOT / "data" / "workspace" / "progress" / f"{sid}.json"
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps({k: v for k, v in PROG.items() if k != "stage_name"} | {"stage": stage}, ensure_ascii=False), "utf-8")
        tmp.replace(f)
    except OSError:
        pass


def step(name: str, cmd: list[str], timeout: int = 3600) -> subprocess.CompletedProcess:
    t0 = time.time()
    print(f"[제작] {name} …", flush=True)
    progress(name)
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    TIMES[name] = round(time.time() - t0, 1)
    progress(None)
    print(f"[제작] {name} {TIMES[name]}초 · 종료 {r.returncode}", flush=True)
    if name.startswith("skills"):
        for ln in (r.stdout or "").splitlines():
            m = re.match(r"^\[스킬 타이밍\] (\S+) ([\d.]+)초", ln.strip())
            if m:
                TIMES[f"skill:{m.group(1)}"] = float(m.group(2))
    return r


def _why(r: subprocess.CompletedProcess) -> str:
    """하위 단계가 실패한 이유 — result 의 error= 줄(없으면 마지막 줄). 2026-11-17: 'result_file=…' 줄이 이유로 나갔다"""
    lines = ((r.stdout or "") + "\n" + (r.stderr or "")).strip().splitlines()
    for ln in reversed(lines):
        if ln.startswith("error="):
            return ln[6:][:600]
    return (lines[-1] if lines else "알 수 없는 오류")[:600]


def block(out: str) -> dict:
    """스크립트 출력 끝의 결과 블록(FLUMA_…) → dict"""
    lines = (out or "").strip().split("\n")
    at = max((i for i, l in enumerate(lines) if l.startswith("FLUMA_")), default=-1)
    b: dict = {"head": lines[at]} if at >= 0 else {}
    for ln in lines[at + 1:] if at >= 0 else []:
        m = re.match(r"^([a-z_]+)=(.*)$", ln)
        if m:
            b.setdefault(m.group(1), []).append(m.group(2))
    return b


def _skill_fail(r: subprocess.CompletedProcess, *, hard: bool, sid: str, skip_viewer: bool) -> None:
    if r.returncode == 0:
        return
    if "stage=story" in (r.stdout or "") and skip_viewer:
        print("[제작] 시청자 구조 권고 — 렌더는 계속(채팅에서 콘티 보강)", flush=True)
        return
    if "stage=story" in (r.stdout or ""):
        save_times(sid)
        fail("produce", stage="story", error=(block(r.stdout).get("error") or ["콘티 구조를 다시 써야 함"])[0], time=[f"{k}:{v}" for k, v in TIMES.items()])
    err = (r.stderr or r.stdout).strip()[-400:]
    if hard:
        save_times(sid)
        fail("produce", stage="skills", error=err or "스킬 단계 실패", time=[f"{k}:{v}" for k, v in TIMES.items()])
    print(f"[제작] 스킬 단계 실패(콘티 그대로 진행): {err}", flush=True)


def lint_rows(out: str) -> list[tuple[str, str]]:
    """lint.py 출력 → [(규칙, 문장)]. L = 실패, T = 권고"""
    rows = []
    for ln in out.splitlines():
        m = re.match(r"^\s*([LT]\d{2})\b\s*(.*)$", ln.strip())
        if m:
            rows.append((m.group(1), m.group(2)[:200]))
    return rows


def save_times(sid: str) -> None:
    try:
        p = ROOT / "data" / "workspace" / "results" / "produce-timings.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"id": sid, "at": time.strftime("%Y-%m-%dT%H:%M:%S"), **TIMES}, ensure_ascii=False) + "\n")
    except OSError:
        pass


def stills(video: Path, sb: dict, sid: str) -> list[str]:
    """초안에서 장면마다 가운데 프레임 한 장 — 엔진으로 다시 그리지 않아 빠르다"""
    out_dir = ROOT / "data" / "workspace" / "stills" / sid
    out_dir.mkdir(parents=True, exist_ok=True)
    jobs, t = [], 0.0
    for k, sc in enumerate(sb.get("scenes") or []):
        sec = float(sc.get("sec") or 0)
        mid = t + sec / 2
        t += sec
        f = out_dir / f"draft-s{k + 1:02d}.png"
        jobs.append((k, mid, f))
    if not jobs:
        return []

    def _shot(job: tuple[int, float, Path]) -> str | None:
        k, mid, f = job
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{mid:.2f}", "-i", str(video), "-frames:v", "1", "-vf", "scale=540:-2", str(f)], capture_output=True)
        return f"{f.relative_to(ROOT)} | 장면 {k + 1} · {mid:.1f}초" if r.returncode == 0 and f.exists() else None

    with ThreadPoolExecutor(max_workers=min(4, len(jobs))) as ex:
        rows = list(ex.map(_shot, jobs))
    return [r for r in rows if r]


def extras(sid: str) -> list[str]:
    """썸네일 후보 · 장면 마커 목록 — 조립(FilmCraft file.exportFrame · markers.exportCsv)과 thumbnail 재료(DesignCraft)가 남긴 것"""
    rows = []
    man = ROOT / "data" / "compositions" / sid / "craft" / "craft.json"
    try:
        ed = (json.loads(man.read_text("utf-8")).get("edit") or {}) if man.exists() else {}
    except ValueError:
        ed = {}
    for f in sorted((ROOT / "data" / "compositions" / sid / "craft" / "materials").glob("s[0-9][0-9]/*.json")):
        try:
            r = json.loads(f.read_text("utf-8"))
        except ValueError:
            continue
        if isinstance(r, dict) and r.get("type") == "thumbnail" and r.get("file"):
            rows.append(f"{r['file']} | 썸네일(세로, DesignCraft)")
            if r.get("landscape"):
                rows.append(f"{r['landscape']} | 썸네일(가로 16:9)")
    th = (ed.get("thumb") or {}).get("file")
    if th and (ROOT / th).exists():
        rows.append(f"{th} | 썸네일 후보(훅 장면 프레임)")
    if ed.get("markers") and (ROOT / ed["markers"]).exists():
        rows.append(f"{ed['markers']} | 장면 마커 목록(FilmCraft)")
    return rows


_FINAL = ("FLUMA_RESULT", "FLUMA_ERROR", "FLUMA_NEEDS_INPUT")


def _spawn_detached(cmd: list[str], log: Path, env: dict) -> int:
    """부모와 완전히 끊긴 프로세스로 띄우고 pid 를 돌려준다(기록은 log 로).
    2026-11-17: 새 세션(start_new_session)으로만 떼면 여전히 부모의 자식이라, 에이전트 Bash 시간 제한이 자식까지 줄줄이 끄면서
    렌더 도중 결과 없이 죽었다. POSIX 는 두 번 갈라(double fork) 고아로 만들어 init 아래로 보낸다. Windows 는 분리 실행 플래그"""
    if os.name != "posix":
        flags = getattr(subprocess, "DETACHED_PROCESS", 0x8) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200)
        with log.open("w") as lf:
            return subprocess.Popen(cmd, cwd=ROOT, stdout=lf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=env, creationflags=flags).pid
    r, w = os.pipe()
    mid = os.fork()
    if mid == 0:                                    # 중간 프로세스: 새 세션을 만들고 진짜 작업을 하나 더 갈라 낸 뒤 바로 끝난다
        try:
            os.close(r)
            os.setsid()
            pid = os.fork()
            if pid == 0:
                os.close(w)
                fd = os.open(str(log), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
                nul = os.open(os.devnull, os.O_RDONLY)
                os.dup2(nul, 0); os.dup2(fd, 1); os.dup2(fd, 2)
                os.chdir(str(ROOT))
                os.execve(cmd[0], cmd, env)
            os.write(w, str(pid).encode())
        finally:
            os._exit(0)
    os.close(w)
    got = os.read(r, 32)
    os.close(r)
    os.waitpid(mid, 0)
    return int(got or b"0")


def _final_block(log: Path) -> tuple[list[str], int] | None:
    """뒤에서 돈 produce 기록의 마지막 결과 블록(FLUMA_RESULT · FLUMA_ERROR · FLUMA_NEEDS_INPUT ~ result_file=)과 종료 코드"""
    try:
        lines = log.read_text("utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].strip() in _FINAL:
            block = [lines[i].strip()]
            for ln in lines[i + 1:]:
                block.append(ln)
                if ln.startswith("result_file="):
                    break
            return block, {"FLUMA_RESULT": 0, "FLUMA_ERROR": 1, "FLUMA_NEEDS_INPUT": 10}[lines[i].strip()]
    return None


def _attach(sid: str, tmp: Path, prep: bool) -> int:
    """에이전트가 produce 를 앞에서 부르면 — 뒤에서 돌리고(새 세션이라 에이전트의 timeout · 턴 종료에 죽지 않는다) 기다렸다
    결과 블록을 그대로 넘긴다. 기다림 한도(FLUMA_ATTACH_WAIT, 기본 480초)를 넘기면 FLUMA_RUNNING(종료 11) — 같은 명령을 다시 부르면 이어서 기다린다.
    2026-11-17: 에이전트가 'timeout 595 produce.py' 로 돌려 대본 검토 도중 잘렸고, 다시 부르면 처음부터 다시 했다."""
    tmp.mkdir(parents=True, exist_ok=True)
    log, att = tmp / ("prep.log" if prep else "produce.log"), tmp / "attach.json"
    args = [x for x in sys.argv[1:] if x != "--bg"]
    try:
        st = json.loads(att.read_text("utf-8"))
    except (OSError, ValueError):
        st = {}

    def alive(pid) -> bool:
        try:
            os.kill(int(pid), 0)
            return True
        except (OSError, TypeError, ValueError):
            return False

    if st.get("args") == args and not st.get("delivered") and (alive(st.get("pid")) or _final_block(log)):
        pid = st["pid"]
        print(f"[제작] 뒤에서 도는 같은 제작(pid {pid})에 이어서 붙음", flush=True)
    else:
        pid = _spawn_detached([PY, str(Path(__file__).resolve()), *args], log, {**os.environ, "FLUMA_PRODUCE_CHILD": "1"})
        st = {"pid": pid, "args": args, "log": str(log.relative_to(ROOT)), "started": time.strftime("%Y-%m-%dT%H:%M:%S")}
        att.write_text(json.dumps(st, ensure_ascii=False), "utf-8")
        print(f"[제작] 뒤에서 시작(pid {pid}) — 기록 {st['log']}", flush=True)
    wait = float(os.environ.get("FLUMA_ATTACH_WAIT", "480"))
    t0 = time.time()
    while time.time() - t0 < wait:
        if not alive(pid):
            break
        time.sleep(2)
    else:
        try:
            pg = json.loads((ROOT / "data" / "workspace" / "progress" / f"{sid}.json").read_text("utf-8"))
        except (OSError, ValueError):
            pg = {}
        running("produce", stage=pg.get("stage") or "running", log=st["log"],
                next="작업은 뒤에서 계속 돈다 — 같은 명령을 다시 실행하면 이어서 기다린다(새로 시작하지 않는다)")
    fin = _final_block(log)
    st["delivered"] = True
    att.write_text(json.dumps(st, ensure_ascii=False), "utf-8")
    try:
        steps = [ln for ln in log.read_text("utf-8", errors="replace").splitlines() if ln.startswith("[제작]")]
    except OSError:
        steps = []
    print("\n".join(steps[-25:]), flush=True)
    if not fin:
        fail("produce", stage="background", error="뒤에서 돈 제작이 결과 없이 끝났습니다", log=st["log"])
    print("\n" + "\n".join(fin[0]), flush=True)
    return fin[1]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("storyboard")
    ap.add_argument("--scenes", help="이 장면만 초안(1부터, 예: 1-3)")
    ap.add_argument("--aspect", choices=["9:16", "16:9", "1:1"])
    ap.add_argument("--no-audio", action="store_true", help="음성을 다시 만들지 않는다(대사가 그대로일 때)")
    ap.add_argument("--keep-going", action="store_true", help="검사 실패(L)가 있어도 초안까지")
    ap.add_argument("--no-skills", action="store_true", help="대본 단계 스킬(각본가 · 감독 · 디자이너)을 건너뛴다 — 렌더 뒤 화면 검토는 그대로 돈다")
    ap.add_argument("--preview-only", action="store_true", help="납품(master) 렌더 없이 초안만")
    ap.add_argument("--delivery", action="store_true", help="납품(master) 렌더까지(한 번 더 느림)")
    ap.add_argument("--fast", action="store_true", help="스킬 · review/refine 생략(가장 빠름)")
    ap.add_argument("--prep", action="store_true", help="대본만 먼저: 이해 관문(시청자 · 각본가) · 음악 · 목소리 · 음성까지 하고 멈춘다 — "
                    "에이전트가 그동안 재료(2D 장면)를 짜고, 끝나면 그냥 produce 를 다시 부른다(대본이 그대로면 대본 단계는 건너뜀)")
    ap.add_argument("--prep-status", action="store_true", help="뒤에서 돌린 --prep 결과만 본다(돌는 중 · 끝 · 막힘과 이유)")
    ap.add_argument("--bg", action="store_true", help="(--prep 과 함께) 뒤에서 돌리고 바로 돌아온다 — 기록은 data/workspace/tmp/<id>/prep.log")
    a = ap.parse_args()
    if a.fast:
        a.no_skills = True
        a.preview_only = True
    sys.path.insert(0, str(ROOT / "engine" / "core"))
    import quality_mode as qm  # noqa: E402

    hard_skills = qm.hard_skills()
    use_draft = qm.use_draft_render() or (a.preview_only and not a.delivery)
    # 렌더 뒤 화면 검토(review)는 --no-skills 에서도 돈다 — --no-skills 는 대본 단계(각본가 · 감독 · 디자이너)만 건너뛴다.
    # 2026-11-17: 빠르게 만들려고 --no-skills 로 돌리면 화면 검토까지 꺼져, 화면 밖으로 잘린 장면이 그대로 나갔다. 끄려면 --fast 또는 FLUMA_DEEP_REVIEW=0
    deep = qm.deep_review() and not a.fast
    sp = Path(a.storyboard)
    sp = sp if sp.is_absolute() else ROOT / sp
    if not sp.exists():
        fail("produce", stage="storyboard", error=f"콘티가 없습니다: {a.storyboard}")
    sb = json.loads(sp.read_text("utf-8"))
    sid = sb["id"]
    lock_f0 = ROOT / "data" / "workspace" / "tmp" / sid / "produce.lock"
    prep_f = ROOT / "data" / "compositions" / sid / "prep.json"
    if a.prep_status:
        st = json.loads(prep_f.read_text("utf-8")) if prep_f.exists() else {}
        running = lock_f0.exists()
        if st.get("status") == "error":
            fail("produce", stage="prep", error=st.get("error") or "막힘", next="대본(나레이션 · 장면 순서)을 고치고 --prep --bg 다시")
        ok("produce", stage="prep", status="running" if running else (st.get("status") or "none"))
        return 0
    if a.bg:                                            # 뒤에서 돌리고 바로 돌아온다(어느 에이전트 런타임에서든 같은 명령)
        log = lock_f0.parent / ("prep.log" if a.prep else "produce.log")
        log.parent.mkdir(parents=True, exist_ok=True)
        args = [x for x in sys.argv[1:] if x != "--bg"]
        _spawn_detached([PY, str(Path(__file__).resolve()), *args], log, {**os.environ, "FLUMA_PRODUCE_CHILD": "1"})
        ok("produce", stage="background", log=str(log.relative_to(ROOT)), next="그동안 재료를 짠다 — 끝나면 python3 engine/produce.py " + str(sp.relative_to(ROOT)) + " (prep 이 아직 돌면 끝날 때까지 기다렸다 이어 간다)")
        return 0
    if os.environ.get("FLUMA_AGENT_RUNTIME") and not os.environ.get("FLUMA_PRODUCE_CHILD") and os.environ.get("FLUMA_PRODUCE_ATTACH", "1") != "0":
        return _attach(sid, lock_f0.parent, a.prep)
    # 같은 영상의 produce(예: --prep)가 아직 돌고 있으면 끝날 때까지 기다린다(최대 15분)
    t_wait = time.time()
    while lock_f0.exists():
        try:
            other = json.loads(lock_f0.read_text("utf-8")).get("pid")
            os.kill(int(other), 0)
        except (ValueError, OSError, TypeError):
            break
        if time.time() - t_wait > 900:
            fail("produce", stage="lock", error="같은 영상의 produce 가 15분 넘게 돌고 있습니다")
        time.sleep(3)
    if time.time() - t_wait > 3:
        print(f"[제작] 앞선 produce(--prep)를 {time.time() - t_wait:.0f}초 기다림", flush=True)
        sb = json.loads(sp.read_text("utf-8"))
    PROG.clear(); PROG.update(sid=sid, started=time.time())
    import atexit
    atexit.register(lambda: progress(None, running=False))      # 끝나든 실패하든 '도는 중' 표시를 내린다
    progress("start")
    rel = str(sp.relative_to(ROOT))
    lock_dir = ROOT / "data" / "workspace" / "tmp" / sid
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_f = lock_dir / "produce.lock"
    lock_f.write_text(json.dumps({"pid": os.getpid(), "at": time.time()}), "utf-8")
    import atexit

    atexit.register(lambda: lock_f.unlink(missing_ok=True))

    # 0) 대본 한 덩어리(sb.script) → 장면 나레이션 — 문장이 장면을 넘어 이어지게(이어 말하기로 한 번에 합성)
    r = step("script", [PY, "engine/story/script.py", rel], timeout=60)
    if r.returncode != 0:
        fail("produce", stage="script", error=(r.stderr or r.stdout).strip().splitlines()[-1])
    sb = json.loads(sp.read_text("utf-8"))

    # 범위(쇼츠 한 편에 요점 하나) — 비싼 대본 단계(모델 호출) 전에 바로 막는다
    sys.path.insert(0, str(ROOT / "engine" / "checks"))
    from lint import scope_problems
    sc_bad = scope_problems(sb, estimate=True)
    if sc_bad:
        save_times(sid)
        fail("produce", stage="scope", error=" / ".join(m for _, m in sc_bad), next="대본을 줄여 다시")

    # 대본만 먼저 해 둔 기록(--prep) — 말(나레이션 · 화면 글자 · 제목)이 그대로면 대본 단계(이해 관문 · 각본가)는 다시 하지 않는다
    from story.skill_pass import is_approved, words_hash
    prepped = False
    if not a.prep and prep_f.exists():
        try:
            pj = json.loads(prep_f.read_text("utf-8"))
        except ValueError:
            pj = {}
        same = pj.get("words") == words_hash(sb)
        if same and pj.get("status") == "error":   # 같은 대본으로 다시 돌려 봐야 같은 자리에서 막힌다 — 이유를 바로 알린다
            fail("produce", stage="prep", error=f"--prep 에서 막힌 대본 그대로입니다: {pj.get('error')}", next="대본(나레이션 · 장면 순서)을 고치고 --prep --bg 다시")
        prepped = same and pj.get("status", "ok") != "error"
    # 앞선 produce · 채팅에서 이해 관문을 마친 말 그대로면(skill_pass/approved.json) 대본 단계를 다시 하지 않는다.
    # 2026-11-17: 음성 실패 뒤 재시도마다 시청자 · 각본가 검토 9분을 처음부터 다시 했다
    if not a.prep and not prepped and is_approved(sp):
        prepped = True
    if prepped:
        print("[제작] 대본 단계는 이미 끝남(말이 그대로) — 연출 · 디자인만(바뀐 것만)", flush=True)

    # 0) 레퍼런스 스타일 — 없을 때만(느림). 여러 편이면 첫 레퍼런스만(FLUMA_REF_STYLE_LIMIT=1 기본)
    xr = ROOT / "data" / "public" / "trends" / "xray"
    ref_lim = max(1, int(os.environ.get("FLUMA_REF_STYLE_LIMIT", "1")))
    for rid in (sb.get("reference") or [])[:ref_lim]:
        if (xr / str(rid) / "xray.json").exists() and (xr / str(rid) / "src.mp4").exists() and not (xr / str(rid) / "style" / "style.json").exists():
            step(f"style:{rid}", [PY, "engine/research/ref_style.py", str(rid)], timeout=600)

    # 0.3) 스킬 단계 — 각본가(writer + humanizer-ko) → 감독(director) → 디자이너(designer + Astryx)를 콘티에 실제로 적용하고,
    #      검사가 막은 것은 담당 단계로 되돌려 고친다(engine/story/skill_pass.py). 콘티가 그대로면 다시 부르지 않는다(기록의 입력 해시).
    #      2026-11-11: 스킬은 에이전트가 읽기만 했고 엔진은 그 칸을 거의 안 읽었다 — 권고 대신 파이프라인 단계로
    from story.skill_pass import produce_skill_steps

    sk_steps = produce_skill_steps(sp) if not a.no_skills and qm.run_skill_pass_in_produce() else []
    if a.prep and sk_steps and not qm.skip_viewer_pass():      # 대본만: 시청자 · 각본가(이해 관문) — 연출 · 디자인은 재료가 생긴 뒤에
        sk_steps = []
        r = step("comprehension", [PY, "engine/story/skill_pass.py", "comprehension", rel], timeout=1200)
        print("\n".join(ln for ln in (r.stdout or "").splitlines() if ln.startswith("[스킬")), flush=True)
        if r.returncode != 0:
            save_times(sid)
            # 실패도 남긴다 — 뒤에서 돌린 prep 이 막힌 걸 아무도 몰라 대본 단계를 처음부터 다시 돌렸다(2026-11-17)
            prep_f.parent.mkdir(parents=True, exist_ok=True)
            prep_f.write_text(json.dumps({"status": "error", "words": words_hash(sb), "error": _why(r), "at": time.strftime("%Y-%m-%dT%H:%M:%S")}, ensure_ascii=False), "utf-8")
            fail("produce", stage="comprehension", error=_why(r))
        sb = json.loads(sp.read_text("utf-8"))
    elif prepped and sk_steps:                                  # 대본은 끝남 — 감독 · 디자이너만(동시에)
        sk_steps = []
        r = step("skills", [PY, "engine/story/skill_pass.py", "visual", rel], timeout=1200)
        print("\n".join(ln for ln in (r.stdout or "").splitlines() if ln.startswith("[스킬")), flush=True)
        _skill_fail(r, hard=hard_skills, sid=sid, skip_viewer=qm.skip_viewer_pass())
        sb = json.loads(sp.read_text("utf-8"))
    if sk_steps == ["writer", "director", "designer"]:
        sk_cmd = "pipeline" if qm.skip_viewer_pass() else "all"
        r = step("skills", [PY, "engine/story/skill_pass.py", sk_cmd, rel], timeout=2400)
        print("\n".join(ln for ln in (r.stdout or "").splitlines() if ln.startswith("[스킬")), flush=True)
        _skill_fail(r, hard=hard_skills, sid=sid, skip_viewer=qm.skip_viewer_pass())
        sb = json.loads(sp.read_text("utf-8"))
    elif sk_steps:
        print(f"[제작] 스킬 단계(맞춤) — {', '.join(sk_steps)}", flush=True)
        for sn in sk_steps:
            r = step(f"skills:{sn}", [PY, "engine/story/skill_pass.py", sn, rel], timeout=1800)
            print("\n".join(ln for ln in (r.stdout or "").splitlines() if ln.startswith("[스킬")), flush=True)
            _skill_fail(r, hard=hard_skills, sid=sid, skip_viewer=qm.skip_viewer_pass())
        sb = json.loads(sp.read_text("utf-8"))
    dr = step("direction", [PY, "engine/story/direct.py", rel, "--write"], timeout=120)
    if dr.returncode != 0:
        print(f"[제작] direction 자동 기록 실패(계속): {(dr.stderr or dr.stdout).strip()[-200:]}", flush=True)
    sb = json.loads(sp.read_text("utf-8"))
    step("materials", [PY, "engine/story/material_evidence.py", rel], timeout=120)
    sb = json.loads(sp.read_text("utf-8"))

    # 0.5) 배경 음악 — 넣을지 정하고 요즘 쓰이는 곡 중 맞는 것(무료 판)을 고른다 · 목소리 — 레퍼런스 화자와 닮은 목소리 · 말 속도(설정 '자동'일 때)
    #      음악 결정이 음성보다 먼저다: 음악이 깔리면 효과음을 빼는 규칙이 음성 단계에서 쓰인다
    if not a.no_audio:
        r = step("music", [PY, "engine/craft/music_pick.py", "auto", rel], timeout=600)
        if r.returncode != 0:
            print(f"[제작] 음악 고르기 실패(음악 없이 진행): {(r.stderr or r.stdout).strip()[-200:]}", flush=True)
        print("\n".join(ln for ln in (r.stdout or "").splitlines() if ln.startswith("[음")), flush=True)
        r = step("voice", [PY, "engine/voice/voice_match.py", "auto", rel], timeout=900)
        if r.returncode != 0:
            print(f"[제작] 목소리 자동 선택 실패(설정 기본 목소리로): {(r.stderr or r.stdout).strip()[-200:]}", flush=True)
        print("\n".join(ln for ln in (r.stdout or "").splitlines() if ln.startswith("[음")), flush=True)
        sb = json.loads(sp.read_text("utf-8"))

    # 0.9) 이해 관문 — 음성 직전의 '최종' 대본을 처음 보는 시청자가 다시 본다(그 사이 에이전트 · 검사 되먹임이 대본을 고쳤을 수 있다).
    #      대본이 그대로면 해시로 건너뛴다. 막히면 각본가가 고치고 다시 본다(skill_pass.comprehension_loop)
    if not a.no_skills and not qm.skip_viewer_pass() and not a.prep and not prepped:
        r = step("comprehension", [PY, "engine/story/skill_pass.py", "comprehension", rel], timeout=1200)
        print("\n".join(ln for ln in (r.stdout or "").splitlines() if ln.startswith("[스킬")), flush=True)
        if r.returncode != 0:
            save_times(sid)
            fail("produce", stage="comprehension", error=_why(r))
        sb = json.loads(sp.read_text("utf-8"))

    # 1) 음성 — 장면 길이가 여기서 정해진다
    if not a.no_audio or not (ROOT / "data" / "audio" / f"{sid}.wav").exists():
        r = step("audio", [PY, "engine/voice/assemble_audio.py", rel])
        if r.returncode != 0:
            save_times(sid)
            fail("produce", stage="audio", error=(r.stderr or r.stdout).strip().splitlines()[-1] if (r.stderr or r.stdout).strip() else "음성 실패", time=[f"{k}:{v}" for k, v in TIMES.items()])
        sb = json.loads(sp.read_text("utf-8"))          # 음성이 장면 길이를 고쳤을 수 있다
    if a.prep:                                          # 대본 · 음성까지 — 이제 장면 길이 · 낱말 시각($CUE)이 정해졌다
        prep_f.parent.mkdir(parents=True, exist_ok=True)
        prep_f.write_text(json.dumps({"status": "ok", "words": words_hash(sb), "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "time": TIMES}, ensure_ascii=False), "utf-8")
        save_times(sid)
        ok("produce", stage="prep", sec=[round(float(x.get("sec") or 0), 2) for x in sb.get("scenes") or []],
           next="재료(2D 장면 · $CUE)를 콘티에 넣고 python3 engine/produce.py " + rel + " (나레이션 · 화면 글자는 바꾸지 않는다 — 바꾸면 대본 단계를 다시 한다)",
           time=[f"{k}:{v}" for k, v in TIMES.items()])
        return 0

    # 2) 검사 — 실패(L)면 렌더하지 않는다. 사용자만 줄 수 있는 것(L36 녹화 · L38 키)은 입력 요청으로
    r = step("lint", [PY, "engine/checks/lint.py", rel])
    # 음성을 만든 뒤에야 드러나는 대사 문제(실측 길이 L05 · L14, 대사 길이)는 각본가 단계로 한 번 되돌려 고치고 음성을 다시 만든다
    if r.returncode != 0 and not a.no_skills and not a.no_audio and re.search(r"^(L05|L14|L04) |/narration", r.stdout or "", re.M):
        print("[제작] 음성 뒤 검사: 대사 문제 — 각본가 단계로 되돌림", flush=True)
        step("skills", [PY, "engine/story/skill_pass.py", "writer", rel, "--force"], timeout=1800)
        step("audio", [PY, "engine/voice/assemble_audio.py", rel])
        r = step("lint", [PY, "engine/checks/lint.py", rel])
    rows = lint_rows(r.stdout)
    hard = [(c, m) for c, m in rows if c.startswith("L")]
    soft = [(c, m) for c, m in rows if c.startswith(("T", "V", "D"))]
    asks = [(c, m) for c, m in hard if c in ("L36", "L38")]
    if hard and not a.keep_going:
        save_times(sid)
        if asks and len(asks) == len(hard):
            needs_input("produce", needs=[f"{c} {m}" for c, m in asks], how="사용자 녹화는 편집기에 올리기(이름에 재료 id) · 키는 설정 → API 키")
        fail("produce", stage="lint", error=" / ".join(f"{c} {m}" for c, m in hard[:6]), lint=[f"{c} {m}" for c, m in hard], time=[f"{k}:{v}" for k, v in TIMES.items()])

    try:
        sys.path.insert(0, str(ROOT / "engine" / "story"))
        from production_ready import touch_production_ready  # noqa: E402

        touch_production_ready(sp)
        sb = json.loads(sp.read_text("utf-8"))
    except Exception as e:  # noqa: BLE001
        print(f"[제작] production_ready 기록 생략: {e}", flush=True)

    # 2-0) 디자인 방향을 사용자가 골랐나(시안 · 직접 요청) — 안 골랐으면 레퍼런스 값 · 효과 없음으로 만든다(권고)
    if not (sb.get("direction") or {}).get("locked") and not sb.get("variant_of"):
        soft.append(("D01", f"디자인 방향을 사용자가 고르지 않음 — 전체 초안 전에 python3 engine/story/directions.py propose {rel} 로 시안을 보여 주고 고르게(지금은 레퍼런스에서 잰 값 · 없으면 효과 없음)"))

    # 2-0a) 콘셉트를 벌려 보고 사람이 골랐나(engine/story/concepts.py) — 건너뛰면 첫 안으로 굳는다(권고)
    if not sb.get("concept") and not sb.get("variant_of") and not sb.get("reference_skip"):
        soft.append(("D04", "콘셉트를 고르지 않음 — 콘티 전에 engine/story/concepts.py 로 안 6~8개를 벌리고 5초 시안을 보여 고르게"))

    # 2-0a2) 아트 디렉션 — 영상마다 시각 언어를 정한다(없으면 고정 템플릿 모양)
    if not sb.get("variant_of"):
        from craft.design import art_problems
        _ap = art_problems(sb)
        if _ap:
            soft.append(("D05", " · ".join(_ap) + " — 콘티 direction.art 에 palette · rule · avoid 를 정하기(produce 스킬)"))

    # 2-0a3) 시청 지속 — 형식 반복 · 한 사람만 · 실제 자료 없음 · 긴 정지(모든 영상에 드는 규칙)
    if not sb.get("variant_of"):
        import retention
        soft += [(c, f"{str(n) + '장면 ' if n else ''}{m}") for c, n, m in retention.check(sb)]

    # 2-0b) 디테일 다듬기(engine/craft/refine.py) — 초벌(어댑터) 그대로면 앱 기능 몇 개만 쓴 화면이다(권고)
    try:
        from craft.refine import coverage as _cov
        cv = _cov(sb)
        if not cv["grid"] and not sb.get("variant_of"):
            soft.append(("D02", f"다듬기 없음(초벌 그대로) — 초안을 본 뒤 refine 스킬: python3 engine/craft/session.py show {rel} <장면> → plan → try → keep"))
        elif cv["missing"]:
            soft.append(("D02", "계획했는데 안 다듬은 층: " + ", ".join(f"{s}장면 {ly}" for s, ly in cv["missing"][:8])))
    except ImportError:
        pass

    try:
        sys.path.insert(0, str(ROOT / "engine" / "story"))
        from ui_build import warm_all_ui_mocks  # noqa: E402

        t_ui = time.time()
        warm_all_ui_mocks(sb)
        TIMES["ui_warm"] = round(time.time() - t_ui, 1)
    except Exception as e:  # noqa: BLE001
        print(f"[제작] ui 병렬 빌드 생략: {e}", flush=True)

    # 2.9) 디자이너 정지 화면 검토(skill_pass review) — 렌더 앞에서. 정지 화면은 영상이 아니라 프로젝트에서 바로 그린다(engine/core/still.py → snapshot)
    #      2026-11-18: 렌더 뒤에 검토하면 바뀐 값(글자 위치 등)이 화면 전체에 걸려 두 번째 렌더가 통째로 돌았다(90초)
    if deep and not a.scenes:
        rr = step("review", [PY, "engine/story/skill_pass.py", "review", rel], timeout=2400)
        print("\n".join(ln for ln in (rr.stdout or "").splitlines() if ln.startswith("[스킬")), flush=True)
        sb = json.loads(sp.read_text("utf-8"))

    # 3) 재료 · 초안 렌더(재료는 렌더가 만든다 — engine/craft/materials.py)
    outfile_label = "완성" if not use_draft else "초안"
    cmd = [PY, "engine/render.py", rel] + (["--draft"] if use_draft else []) + (["--scenes", a.scenes] if a.scenes else []) + (["--aspect", a.aspect] if a.aspect else [])
    r = step("render", cmd)
    b = block(r.stdout)
    if r.returncode != 0 or b.get("head") != "FLUMA_RESULT":
        save_times(sid)
        fail("produce", stage="render", error=(b.get("error") or [(r.stderr or r.stdout).strip()[-300:]])[0], time=[f"{k}:{v}" for k, v in TIMES.items()])
    video = ROOT / b["file"][0]

    # 3.5) 렌더 뒤 자동 다듬기(refine)는 켤 때만 — 정지 화면 검토(review)는 렌더 앞(2.9)에서 한다
    #      2026-11-11: 디자인 값을 정해 놓고 결과를 안 봐서 터미널이 잘리고 숫자가 글자와 겹쳤다
    if deep and not a.scenes:   # (정지 화면 검토는 렌더 앞 2.9 로 옮김)
        if os.environ.get("FLUMA_DEEP_REFINE") == "1":   # 자동 다듬기(refine)는 켤 때만 — 2026-11-17 실측 219초(영상 하나 15분 안에 못 들어옴). 정지 화면 검토(review)는 그대로
            rf = step("refine", [PY, "engine/story/skill_pass.py", "refine", rel], timeout=2700)
            print("\n".join(ln for ln in (rf.stdout or "").splitlines() if ln.startswith("[스킬")), flush=True)
            if rf.returncode == 0 and '"kept": [{' in (rf.stdout or ""):
                r = step("render", cmd)
                b = block(r.stdout)
                if r.returncode == 0 and b.get("head") == "FLUMA_RESULT":
                    video = ROOT / b["file"][0]
    # 렌더가 찍은 편집 밀도 · 템포 문제(✗ 실패 · △ 권고)
    # 품질 관문(engine/checks/quality_gate.py): 경고를 막음 · 권고로 나눈다 — 막음이 남으면 완성본으로 내보내지 않는다(2026-11-18)
    import quality_gate as qg
    issues = [qg.from_render_line(ln) for ln in r.stdout.splitlines() if re.match(r"^\s*[✗△]", ln)]
    import refmatch   # 레퍼런스 대조: ref 를 적었는데 나란히 보지 않은 재료
    issues = [qg.issue("D03", n, f"{mid}: {why} — python3 engine/checks/refmatch.py sheet {rel} {mid} 로 그림을 보고 ok") for n, mid, why in refmatch.status(sb)] + issues
    from designcheck import findings as _df   # 렌더 결과를 재는 디자인 검사
    issues = [qg.issue(x["code"], x["scene"], x["msg"], x.get("block")) for x in (_df(video, sb) if not a.scenes else [])] + issues
    issues += [qg.issue(c, None, m, block=False) for c, m in soft]      # 말투 · 구성 · 절차(lint T · D01 · D02 · D04 · D05 · R) — 권고
    q_block, q_waived, q_adv = qg.split(sb, issues)
    warns = [qg.line(x) for x in q_block + q_adv]
    import usage as _usage
    depth = _usage.depth(sid)

    # 4) 장면별 정지 화면
    t0 = time.time()
    media = [f"{b['file'][0]} | {outfile_label}"] + (stills(video, sb, sid) if not a.scenes else []) + (extras(sid) if not a.scenes else [])
    if not a.scenes:                              # 초안 · 레퍼런스 나란히(프레임 12장씩) — 에이전트가 직접 본다(engine/checks/sheet.py)
        try:
            import sheet as _sheet
            media.insert(1, f"{_sheet.make(video, sb).relative_to(ROOT)} | 초안 · 레퍼런스 나란히")
        except Exception as e:  # noqa: BLE001
            print(f"[제작] 나란히 보기를 만들지 못함: {str(e)[:120]}", flush=True)
    TIMES["stills"] = round(time.time() - t0, 1)
    save_times(sid)
    if not a.scenes:                              # 화풍 거리 — 최근 영상과 너무 닮았으면 알린다(막지 않음, 로컬 CLIP · 1초 안쪽)
        try:
            sys.path.insert(0, str(ROOT / "engine" / "checks"))
            import style_distance
            sd = style_distance.check(sid)
            if sd.get("too_close"):
                warns.append(f"화풍: 최근 영상 {sd['nearest']} 과 {sd['similarity']} 로 거의 같은 모습 — 그림체 · 색 · 구도 · 카메라 문법 중 하나를 레퍼런스 쪽으로 바꿀 것")
        except Exception as e:  # noqa: BLE001
            print(f"[제작] 화풍 거리를 재지 못함: {str(e)[:120]}", flush=True)
    mu, vo = sb.get("music") or {}, sb.get("voice") or {}
    sound = [f"음악: {mu.get('title')} — {mu.get('by')} ({mu.get('license')}) · {mu.get('why')}" if mu.get("use") and mu.get("src") else f"음악: 안 넣음 — {mu.get('why') or '정하지 않음'}",
             f"목소리: {vo.get('engine')} · {vo.get('id') or '기본'} · ×{vo.get('speed', 1)}" + (f" — {vo['why']}" if vo.get("why") else "")]
    if mu.get("upload_sound"):
        sound.append("업로드 때 붙일 수 있는 유행곡(쇼츠 편집기 '사운드 추가'): " + " / ".join(mu["upload_sound"][:3]))
    if not a.scenes:
        qg.save(sid, b["file"][0], q_block, q_waived, q_adv)
    if q_block and not a.scenes:
        fail("produce", stage="quality", error=f"막음 {len(q_block)}건이 남아 완성본이 아니다 — 고친 뒤 다시(고칠 장면만: knob.py preview --scene N 으로 확인 → 마지막에 전체 produce 한 번)",
             block=[qg.line(x) for x in q_block], advise=[qg.line(x) for x in q_adv], waived=[f"{qg.line(x)} — 면제: {x['waived']}" for x in q_waived],
             file=b["file"][0], media=media, time=[f"{k}:{v}" for k, v in TIMES.items()],
             next="막음을 모두 고친다. 사용자가 그대로 두라고 한 항목만 콘티 waivers 에 {\"코드:장면\": {\"why\": ..., \"user_said\": 사용자 말 그대로}} 로 적는다(스스로 면제 금지)")
    ok("produce", file=b["file"][0], media=media, warn=warns, advise=len(q_adv), waived=[f"{qg.line(x)} — 면제: {x['waived']}" for x in q_waived], lint_soft=len(soft), depth=depth, sound=sound,
       time=[f"{k}:{v}" for k, v in TIMES.items()], next="먼저 '초안 · 레퍼런스 나란히'(sheet.png)를 Read 로 보고 director 검사(화면이 바뀌는 리듬 · 피사체 크기 · 글자 크기 · 시선 한 곳)로 레퍼런스와 견준다. "
            "고칠 장면만 있을 때는 전체 produce 를 반복하지 말고 knob.py set + knob.py preview --scene N(또는 produce.py --scenes N --no-audio) 로 확인한 뒤, 마지막에 한 번만 전체 produce")


if __name__ == "__main__":
    from result import run_main
    run_main("produce", main)
