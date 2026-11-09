#!/usr/bin/env python3
"""대화로 고치기 — 영상의 값(손잡이)을 바꾸고, 바뀐 부분만 다시 지어 바로 본다. 코드 · 좌표를 고치지 않는다.

  python3 engine/story/knob.py list    <id>                                  # 장면 · 요소 · 바꿀 수 있는 값(짧게)
  python3 engine/story/knob.py set     <id> <경로>=<값> [<경로>=<값> ...]      # 여러 값을 한 번에
  python3 engine/story/knob.py preview <id> --scene 4 [--at 0.5,0.9] [--clip] # 정지 화면(약 2초) · --clip 은 그 장면만 영상(초안 화질)

경로 — 장면 · 요소 · 전체 값
  s4.sec · s4.caption · s4.transition         장면 4의 칸
  route2d.adjust.dx                           요소(재료 id)의 칸 — 어느 장면이든 id 로 찾는다. 'sN.<id>.…' 로 장면을 밝혀도 된다
  route2d.args.gap                            새로 만든 요소(Blender · EffectCraft 스크립트)가 밝혀 둔 값(args)
  voice.speed · voice.id · music.gain_db · music.use · direction.transition · script
값 — JSON(숫자 · 참/거짓 · 문자열 · 목록), 또는 상대값 *0.7 · +0.5 · -0.2(지금 숫자에 곱하기 · 더하기). 지우기: <경로>=null
조정 값(adjust, 모든 요소 공통): dx · dy(화면 비율) · scale(배수) · rot(도) · opacity(0~1) · delay(초) · hide
바꾼 기록은 data/workspace/render/<id>/knobs.jsonl 에 남는다(되돌리기 · 비교).
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
from result import fail, ok  # noqa: E402

REL = re.compile(r"^([*+\-])\s*(-?\d+(?:\.\d+)?)$")


def sb_path(sid: str) -> Path:
    p = Path(sid)
    if p.suffix == ".json":
        return p if p.is_absolute() else ROOT / p
    return ROOT / "data" / "storyboards" / f"{sid}.json"


def find_material(sb: dict, mid: str, scene: int | None = None):
    for i, sc in enumerate(sb.get("scenes") or []):
        if scene is not None and i != scene:
            continue
        for m in sc.get("materials") or []:
            if isinstance(m, dict) and m.get("id") == mid:
                return i, m
    return None, None


def resolve(sb: dict, path: str) -> tuple[dict | list, str]:
    """경로 → (담는 dict, 마지막 열쇠). 중간 dict 는 없으면 만든다"""
    parts = path.split(".")
    scene = None
    if re.fullmatch(r"s\d+", parts[0]):
        scene = int(parts[0][1:]) - 1
        if not 0 <= scene < len(sb.get("scenes") or []):
            raise ValueError(f"장면 {scene + 1} 이 없습니다(1~{len(sb['scenes'])})")
        parts = parts[1:]
        if len(parts) == 1:                                   # s4.sec — 장면 칸
            return sb["scenes"][scene], parts[0]
    if not parts:
        raise ValueError("경로가 비었습니다")
    _, m = find_material(sb, parts[0], scene)
    if m is not None:
        node, rest = m, parts[1:]
    elif scene is not None:
        node, rest = sb["scenes"][scene], parts
    else:
        node, rest = sb, parts
    if not rest:
        raise ValueError(f"'{path}' — 요소 다음에 칸 이름이 필요합니다(예: {parts[0]}.adjust.scale)")
    for k in rest[:-1]:
        if isinstance(node, list):
            node = node[int(k)]
        else:
            node = node.setdefault(k, {})
    return node, rest[-1]


def parse_value(raw: str, cur):
    m = REL.match(raw.strip())
    if m and isinstance(cur, (int, float)) and not isinstance(cur, bool):
        op, x = m.group(1), float(m.group(2))
        return round(cur * x, 4) if op == "*" else round(cur + x if op == "+" else cur - x, 4)
    if m and cur is None and m.group(1) == "*":
        base = 1.0                                           # 처음 정하는 배수(scale · opacity): 기본 1 에 곱한다
        return round(base * float(m.group(2)), 4)
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def cmd_set(sid: str, pairs: list[str]) -> None:
    sp = sb_path(sid)
    sb = json.loads(sp.read_text("utf-8"))
    changes = []
    for pr in pairs:
        if "=" not in pr:
            fail("knob", stage="parse", error=f"'경로=값' 꼴이 아닙니다: {pr}")
        path, raw = pr.split("=", 1)
        try:
            node, key = resolve(sb, path.strip())
        except (ValueError, IndexError, KeyError) as e:
            fail("knob", stage="path", error=str(e))
        cur = node[int(key)] if isinstance(node, list) else node.get(key)
        val = parse_value(raw, cur)
        if val is None and isinstance(node, dict):
            node.pop(key, None)
        elif isinstance(node, list):
            node[int(key)] = val
        else:
            node[key] = val
        changes.append({"path": path.strip(), "from": cur, "to": val})
    sp.write_text(json.dumps(sb, ensure_ascii=False, indent=2) + "\n", "utf-8")
    log = ROOT / "data" / "workspace" / "render" / sb["id"] / "knobs.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as f:
        for c in changes:
            f.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), **c}, ensure_ascii=False) + "\n")
    ok("knob", changed=[f"{c['path']}: {json.dumps(c['from'], ensure_ascii=False)} → {json.dumps(c['to'], ensure_ascii=False)}" for c in changes],
       next=f"python3 engine/story/knob.py preview {sb['id']} --scene <n>")


def cmd_list(sid: str) -> None:
    sb = json.loads(sb_path(sid).read_text("utf-8"))
    rows = []
    for i, sc in enumerate(sb.get("scenes") or [], 1):
        rows.append(f"s{i} · {sc.get('role', '')} · {sc.get('sec')}초" + (f" · 전환 {sc['transition']}" if sc.get("transition") else "")
                    + (f" · \"{str(sc.get('narration') or '')[:28]}\"" if sc.get("narration") else ""))
        for m in sc.get("materials") or []:
            if not isinstance(m, dict):
                continue
            kind = m.get("type", "")
            if m.get("app"):
                kind += f"/{m['app']}"
            if m.get("method"):
                kind += f"/{m['method']}"
            extra = []
            if m.get("adjust"):
                extra.append("adjust " + json.dumps(m["adjust"], ensure_ascii=False))
            if m.get("args"):
                extra.append("args " + json.dumps({k: v for k, v in m["args"].items() if not isinstance(v, (dict, list)) or len(json.dumps(v)) < 60}, ensure_ascii=False)[:160])
            rows.append(f"   {m.get('id')} ({kind})" + (" · " + " · ".join(extra) if extra else ""))
    v, mu = sb.get("voice") or {}, sb.get("music") or {}
    rows.append(f"voice · {v.get('engine')} {v.get('id') or ''} ×{v.get('speed', 1)}")
    rows.append(f"music · {'켬' if mu.get('use', bool(mu.get('src'))) else '끔'} {mu.get('title') or ''} gain {mu.get('gain_db', '기본')}")
    print("\n".join(rows))


def scene_span(sb: dict, i: int) -> tuple[float, float]:
    t = 0.0
    for k, sc in enumerate(sb["scenes"]):
        if k == i:
            return t, float(sc.get("sec") or 0)
        t += float(sc.get("sec") or 0)
    raise ValueError(i)


def cmd_preview(sid: str, scene: int, at: list[float], clip: bool) -> None:
    sp = sb_path(sid)
    sb = json.loads(sp.read_text("utf-8"))
    i = scene - 1
    if not 0 <= i < len(sb["scenes"]):
        fail("knob", stage="scene", error=f"장면 {scene} 이 없습니다")
    t0 = time.time()
    if clip:      # 그 장면만 초안 화질로(소리 포함) — 움직임 · 속도를 볼 때
        r = subprocess.run([sys.executable, str(ROOT / "engine" / "render.py"), str(sp), "--draft", "--scenes", str(scene), "--size", "720"],
                           cwd=ROOT, capture_output=True, text=True, timeout=1800)
        out = next((ln.split("[완료]", 1)[1].strip() for ln in r.stdout.splitlines() if "[완료]" in ln), None)
        if r.returncode != 0 or not out:
            fail("knob", stage="clip", error=(r.stderr or r.stdout).strip()[-300:])
        rel = str(Path(out).resolve().relative_to(ROOT))
        ok("knob", file=rel, media=[f"{rel} | 장면 {scene}"], took=round(time.time() - t0, 1))
    from engines import make_job
    from craft.renderer import adapter as A
    job = make_job(sp, None, None, True)
    start, sec = scene_span(job.sb, i)
    secs = [round(start + max(0.05, min(sec - 0.05, sec * a)), 3) for a in at]
    shots = A.snapshot(job, secs)
    dst = ROOT / "data" / "workspace" / "stills" / sb["id"]
    dst.mkdir(parents=True, exist_ok=True)
    media = []
    for a, s_, p in zip(at, secs, shots):
        f = dst / f"knob-s{scene:02d}-{int(a * 100):03d}.png"
        shutil.copyfile(p, f)
        media.append(f"{f.relative_to(ROOT)} | 장면 {scene} · {s_ - start:.1f}초")
    ok("knob", media=media, took=round(time.time() - t0, 1), next="움직임 · 속도를 보려면 --clip")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["list", "set", "preview"])
    ap.add_argument("id")
    ap.add_argument("pairs", nargs="*")
    ap.add_argument("--scene", type=int)
    ap.add_argument("--at", default="0.5", help="장면 안 위치(0~1, 쉼표로 여러 장)")
    ap.add_argument("--clip", action="store_true")
    a = ap.parse_args()
    if a.cmd == "list":
        cmd_list(a.id)
    elif a.cmd == "set":
        if not a.pairs:
            fail("knob", stage="parse", error="바꿀 값이 없습니다 — 예: route2d.adjust.scale=*1.2")
        cmd_set(a.id, a.pairs)
    else:
        if not a.scene:
            fail("knob", stage="parse", error="--scene 이 필요합니다")
        cmd_preview(a.id, a.scene, [float(x) for x in a.at.split(",") if x.strip()], a.clip)
    return 0


if __name__ == "__main__":
    from result import run_main
    run_main("knob", main)
