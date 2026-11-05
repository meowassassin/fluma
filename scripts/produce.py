#!/usr/bin/env python3
"""제작 한 줄 — 콘티 → 음성 → 검사 → 재료 · 초안 렌더 → 장면별 정지 화면 → 편집 밀도 · 템포, 정해진 순서로.
에이전트가 단계를 손으로 고르지 않게(같은 콘티면 누가 돌려도 같은 결과) — 에이전트는 막힌 곳만 고친다.

  python3 scripts/produce.py storyboards/<id>.json [--scenes 1-3] [--aspect 9:16] [--no-audio] [--keep-going]

결과(scripts/result.py 규약)
  0  FLUMA_RESULT — file(초안) · media(초안 + 장면별 정지 화면) · warn(편집 밀도 · 템포 권고) · time(단계별 초)
  1  FLUMA_ERROR  — stage(audio · lint · render) · error(검사에서 걸린 규칙 · 렌더 오류 짧게)
  10 FLUMA_NEEDS_INPUT — 사용자만 줄 수 있는 것(사용자 녹화 L36 · 스톡 영상 키 L38)
검사(lint)의 실패(L 규칙)가 있으면 렌더하지 않고 멈춘다(--keep-going 이면 렌더까지). 권고(T 규칙)는 warn 으로만.
단계별 소요 시간은 workspace/results/produce-timings.jsonl 에 쌓인다(어디가 느린지 보려고).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from result import fail, needs_input, ok  # noqa: E402

PY = sys.executable
TIMES: dict[str, float] = {}


def step(name: str, cmd: list[str], timeout: int = 3600) -> subprocess.CompletedProcess:
    t0 = time.time()
    print(f"[제작] {name} …", flush=True)
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    TIMES[name] = round(time.time() - t0, 1)
    print(f"[제작] {name} {TIMES[name]}초 · 종료 {r.returncode}", flush=True)
    return r


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
        p = ROOT / "workspace" / "results" / "produce-timings.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"id": sid, "at": time.strftime("%Y-%m-%dT%H:%M:%S"), **TIMES}, ensure_ascii=False) + "\n")
    except OSError:
        pass


def stills(video: Path, sb: dict, sid: str) -> list[str]:
    """초안에서 장면마다 가운데 프레임 한 장 — 엔진으로 다시 그리지 않아 빠르다"""
    out_dir = ROOT / "workspace" / "stills" / sid
    out_dir.mkdir(parents=True, exist_ok=True)
    rows, t = [], 0.0
    for k, sc in enumerate(sb.get("scenes") or []):
        sec = float(sc.get("sec") or 0)
        mid = t + sec / 2
        t += sec
        f = out_dir / f"draft-s{k + 1:02d}.png"
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{mid:.2f}", "-i", str(video), "-frames:v", "1", "-vf", "scale=540:-2", str(f)], capture_output=True)
        if r.returncode == 0 and f.exists():
            rows.append(f"{f.relative_to(ROOT)} | 장면 {k + 1} · {mid:.1f}초")
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("storyboard")
    ap.add_argument("--scenes", help="이 장면만 초안(1부터, 예: 1-3)")
    ap.add_argument("--aspect", choices=["9:16", "16:9", "1:1"])
    ap.add_argument("--no-audio", action="store_true", help="음성을 다시 만들지 않는다(대사가 그대로일 때)")
    ap.add_argument("--keep-going", action="store_true", help="검사 실패(L)가 있어도 초안까지")
    a = ap.parse_args()
    sp = Path(a.storyboard)
    sp = sp if sp.is_absolute() else ROOT / sp
    if not sp.exists():
        fail("produce", stage="storyboard", error=f"콘티가 없습니다: {a.storyboard}")
    sb = json.loads(sp.read_text("utf-8"))
    sid = sb["id"]
    rel = str(sp.relative_to(ROOT))

    # 1) 음성 — 장면 길이가 여기서 정해진다
    if not a.no_audio or not (ROOT / "audio" / f"{sid}.wav").exists():
        r = step("audio", [PY, "scripts/assemble_audio.py", rel])
        if r.returncode != 0:
            save_times(sid)
            fail("produce", stage="audio", error=(r.stderr or r.stdout).strip().splitlines()[-1] if (r.stderr or r.stdout).strip() else "음성 실패", time=[f"{k}:{v}" for k, v in TIMES.items()])
        sb = json.loads(sp.read_text("utf-8"))          # 음성이 장면 길이를 고쳤을 수 있다

    # 2) 검사 — 실패(L)면 렌더하지 않는다. 사용자만 줄 수 있는 것(L36 녹화 · L38 키)은 입력 요청으로
    r = step("lint", [PY, "scripts/lint.py", rel])
    rows = lint_rows(r.stdout)
    hard = [(c, m) for c, m in rows if c.startswith("L")]
    soft = [(c, m) for c, m in rows if c.startswith("T")]
    asks = [(c, m) for c, m in hard if c in ("L36", "L38")]
    if hard and not a.keep_going:
        save_times(sid)
        if asks and len(asks) == len(hard):
            needs_input("produce", needs=[f"{c} {m}" for c, m in asks], how="사용자 녹화는 편집기에 올리기(이름에 재료 id) · 키는 설정 → API 키")
        fail("produce", stage="lint", error=" / ".join(f"{c} {m}" for c, m in hard[:6]), lint=[f"{c} {m}" for c, m in hard], time=[f"{k}:{v}" for k, v in TIMES.items()])

    # 3) 재료 · 초안 렌더(재료는 렌더가 만든다 — scripts/craft/materials.py)
    cmd = [PY, "scripts/render.py", rel, "--draft"] + (["--scenes", a.scenes] if a.scenes else []) + (["--aspect", a.aspect] if a.aspect else [])
    r = step("render", cmd)
    b = block(r.stdout)
    if r.returncode != 0 or b.get("head") != "FLUMA_RESULT":
        save_times(sid)
        fail("produce", stage="render", error=(b.get("error") or [(r.stderr or r.stdout).strip()[-300:]])[0], time=[f"{k}:{v}" for k, v in TIMES.items()])
    video = ROOT / b["file"][0]
    # 렌더가 찍은 편집 밀도 · 템포 문제(✗ 실패 · △ 권고)
    warns = [ln.strip() for ln in r.stdout.splitlines() if re.match(r"^\s*[✗△]", ln)]
    warns += [f"{c} {m}" for c, m in soft]

    # 4) 장면별 정지 화면
    t0 = time.time()
    media = [f"{b['file'][0]} | 초안"] + (stills(video, sb, sid) if not a.scenes else [])
    TIMES["stills"] = round(time.time() - t0, 1)
    save_times(sid)
    ok("produce", file=b["file"][0], media=media, warn=warns[:12], lint_soft=len(soft),
       time=[f"{k}:{v}" for k, v in TIMES.items()], next="정지 화면을 보고(Read) 글자 겹침 · 잘림 · 빈 화면 · 말과 안 맞는 재료를 고친 뒤 다시 produce")


if __name__ == "__main__":
    from result import run_main
    run_main("produce", main)
