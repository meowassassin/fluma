#!/usr/bin/env python3
"""제작 한 줄 — 콘티 → 음성 → 검사 → 재료 · 초안 렌더 → 장면별 정지 화면 → 편집 밀도 · 템포, 정해진 순서로.
에이전트가 단계를 손으로 고르지 않게(같은 콘티면 누가 돌려도 같은 결과) — 에이전트는 막힌 곳만 고친다.

  python3 engine/produce.py data/storyboards/<id>.json [--scenes 1-3] [--aspect 9:16] [--no-audio] [--keep-going]

결과(engine/core/result.py 규약)
  0  FLUMA_RESULT — file(초안) · media(초안 + 장면별 정지 화면) · warn(편집 밀도 · 템포 권고) · time(단계별 초)
  1  FLUMA_ERROR  — stage(audio · lint · render) · error(검사에서 걸린 규칙 · 렌더 오류 짧게)
  10 FLUMA_NEEDS_INPUT — 사용자만 줄 수 있는 것(사용자 녹화 L36 · 스톡 영상 키 L38)
검사(lint)의 실패(L 규칙)가 있으면 렌더하지 않고 멈춘다(--keep-going 이면 렌더까지). 권고(T 규칙)는 warn 으로만.
단계별 소요 시간은 data/workspace/results/produce-timings.jsonl 에 쌓인다(어디가 느린지 보려고).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())  # 저장소 루트(engine/paths.py 가 있는 곳)
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401  engine 아래 묶음들을 import 경로에
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
    if not a.no_audio or not (ROOT / "data" / "audio" / f"{sid}.wav").exists():
        r = step("audio", [PY, "engine/voice/assemble_audio.py", rel])
        if r.returncode != 0:
            save_times(sid)
            fail("produce", stage="audio", error=(r.stderr or r.stdout).strip().splitlines()[-1] if (r.stderr or r.stdout).strip() else "음성 실패", time=[f"{k}:{v}" for k, v in TIMES.items()])
        sb = json.loads(sp.read_text("utf-8"))          # 음성이 장면 길이를 고쳤을 수 있다

    # 2) 검사 — 실패(L)면 렌더하지 않는다. 사용자만 줄 수 있는 것(L36 녹화 · L38 키)은 입력 요청으로
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

    # 2-1) 다양성 — 최근 영상과 같은 구성 · 한 종류 재료 반복(권고, 렌더는 계속). engine/craft/craft_variety.py
    try:
        import craft_variety
        soft += [(c, m) for c, m in craft_variety.check(sb)]
    except Exception as e:  # noqa: BLE001
        print(f"[제작] 다양성 검사 건너뜀: {e}", flush=True)

    # 3) 재료 · 초안 렌더(재료는 렌더가 만든다 — engine/craft/materials.py)
    cmd = [PY, "engine/render.py", rel, "--draft"] + (["--scenes", a.scenes] if a.scenes else []) + (["--aspect", a.aspect] if a.aspect else [])
    r = step("render", cmd)
    b = block(r.stdout)
    if r.returncode != 0 or b.get("head") != "FLUMA_RESULT":
        save_times(sid)
        fail("produce", stage="render", error=(b.get("error") or [(r.stderr or r.stdout).strip()[-300:]])[0], time=[f"{k}:{v}" for k, v in TIMES.items()])
    video = ROOT / b["file"][0]
    # 렌더가 찍은 편집 밀도 · 템포 문제(✗ 실패 · △ 권고)
    warns = [ln.strip() for ln in r.stdout.splitlines() if re.match(r"^\s*[✗△]", ln)]
    # 레퍼런스 대조(engine/checks/refmatch.py): 재료가 만들어진 뒤에 본다 — 맨 앞에 둬야 잘리지 않는다
    import refmatch
    warns = [f"D03 {n}장면 {mid}: {why} — python3 engine/checks/refmatch.py sheet {rel} {mid} 로 그림을 보고 ok" for n, mid, why in refmatch.status(sb)] + warns
    warns += [f"{c} {m}" for c, m in soft]
    # 렌더 결과를 재는 디자인 검사(engine/checks/designcheck.py) · 앱을 얼마나 깊게 썼나
    from designcheck import findings as _df
    _found = _df(video, sb) if not a.scenes else []
    warns = [f"{x['code']} {str(x['scene']) + '장면 ' if x['scene'] else ''}{x['msg']}" for x in _found] + warns
    import usage as _usage
    depth = _usage.depth(sid)

    # 4) 장면별 정지 화면
    t0 = time.time()
    media = [f"{b['file'][0]} | 초안"] + (stills(video, sb, sid) if not a.scenes else []) + (extras(sid) if not a.scenes else [])
    TIMES["stills"] = round(time.time() - t0, 1)
    save_times(sid)
    ok("produce", file=b["file"][0], media=media, warn=warns[:16], lint_soft=len(soft), depth=depth,
       time=[f"{k}:{v}" for k, v in TIMES.items()], next="정지 화면을 보고(Read) 글자 겹침 · 잘림 · 빈 화면 · 말과 안 맞는 재료를 고친 뒤 다시 produce")


if __name__ == "__main__":
    from result import run_main
    run_main("produce", main)
