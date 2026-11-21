#!/usr/bin/env python3
"""콘티 묶음 — 콘티 · 장면 코드 · 형태 · 조사 사실을 파일 하나로 받아 한 번에 저장하고, 모든 검사를 바로 돌려 묶어서 알린다.

2026-11-19 속도(한 편 15분): 콘티 · 장면 파일 · 형태를 따로 쓰고, 검사 → 고침 → 검사를 여러 번 돌아 도구 왕복이 수십 번이었다.
음성을 만들기 전에 검사를 끝내면 음성 뒤 다시 고칠 일도 준다.

  python3 engine/story/bundle.py apply <묶음.json>      # 저장 + 검사 → 막힘(L)만 고쳐 다시 apply
  python3 engine/story/bundle.py check <id>             # 저장된 콘티를 다시 검사만
묶음 형식:
  {"storyboard": {…콘티 전체…},
   "files": {"scenes/s01.jsx": "장면 코드", "forms/duck.json": {…형태…}},       # data/compositions/<id>/ 아래
   "research": {"facts": [{"claim", "value", "source"}], "visual_entities": […]}}   # 선택 — data/research/<id>.json + 기획 기록에 연결
콘티 안에서는 "$FILE:data/compositions/<id>/scenes/s01.jsx" 처럼 가리킨다.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
sys.path.insert(0, str(ROOT / "engine" / "checks"))
from result import fail, ok  # noqa: E402


def _form_problems(sid: str) -> list[str]:
    """형태 파일이 계산되는지(문법 · 도형 칸) — 렌더 전에"""
    out = []
    try:
        from craft.form import sdf
    except Exception:  # noqa: BLE001
        return out
    for f in sorted((ROOT / "data" / "compositions" / sid / "forms").glob("*.json")):
        try:
            sdf.compile_scene(json.loads(f.read_text("utf-8")))
        except Exception as e:  # noqa: BLE001
            out.append(f"L39 형태 {f.name}: {str(e)[:120]}")
    return out


def check(sid: str) -> tuple[list[str], list[str]]:
    import lint
    sb = json.loads((ROOT / "data" / "storyboards" / f"{sid}.json").read_text("utf-8"))
    fails = lint.lint(sb, [t for t in lint.recent_titles() if t != sb.get("title")])
    hard = [f"{c} {'' if i is None else f'장면{i + 1} '}{m}" for c, i, m in fails if not c.startswith("T")]
    soft = [f"{c} {'' if i is None else f'장면{i + 1} '}{m}" for c, i, m in fails if c.startswith("T")]
    # 2026-11-21 속도(품질 그대로): 빌드 뒤 · LLM 검토에서 막던 것을 쓰는 자리에서 — 화면 AI 티(visual_tell)와 형태 프레임 잘림.
    # 같은 검사를 앞당길 뿐이다(제작 단계도 그대로 다시 잰다). 지난 영상: 렌더 전 검토에서 4번 막혀 9분
    try:
        import quality_gate as qg
        import visual_tell as vt
        for x in vt.find(sb, sid):
            if qg.waived(sb, x):
                continue
            (hard if x["block"] else soft).append(f"{x['code']} {x['msg']}")
    except Exception as e:  # noqa: BLE001
        soft.append(f"V00 화면 AI 티 검사 못 함: {e}")
    return hard + _form_problems(sid) + _form_cuts(sid), soft


def _form_cuts(sid: str) -> list[str]:
    """형태 움직임 프레임이 화면 가장자리에서 잘리는지(받침판 · 소품) — 클로즈업(카메라 focus)은 일부러 자른 것이라 뺀다"""
    from PIL import Image
    sys.path.insert(0, str(ROOT / "engine"))
    from craft import form
    out = []
    for d in sorted((ROOT / "data" / "compositions" / sid / "forms").glob("*.anim")):
        try:
            src = json.loads((d.parent / f"{d.stem}.json").read_text("utf-8"))
        except (OSError, ValueError):
            continue
        cam = src.get("camera") or {}
        if cam.get("focus") is not None or (src.get("anim") or {}).get("tracks", {}).get("camera"):
            continue
        fr = sorted(d.glob("f*.png"))
        sides = sorted({x for f in fr[:: max(1, len(fr) // 3)][:4] for x in form.edge_cut(Image.open(f))})
        if sides:
            out.append(f"L40 형태 {d.stem}: 프레임 {' · '.join(sides)} 가장자리에서 형태가 잘린다 — 바닥 받침판이면 \"floor\": true, 소품이면 카메라 radius 를 키우거나 형태를 안으로")
    return out


def apply(path: Path) -> str:
    b = json.loads(path.read_text("utf-8"))
    sb = b.get("storyboard")
    if not isinstance(sb, dict) or not sb.get("id"):
        fail("bundle", stage="read", error="storyboard(id 포함)가 필요합니다")
    sid = sb["id"]
    comp = ROOT / "data" / "compositions" / sid
    for rel, body in (b.get("files") or {}).items():
        f = (comp / rel).resolve()
        if comp.resolve() not in f.parents:
            fail("bundle", stage="files", error=f"영상 폴더 밖 경로: {rel}")
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(body if isinstance(body, str) else json.dumps(body, ensure_ascii=False, indent=1), "utf-8")
    if isinstance(b.get("research"), dict):
        rf = ROOT / "data" / "research" / f"{sid}.json"
        rf.parent.mkdir(parents=True, exist_ok=True)
        rf.write_text(json.dumps(b["research"], ensure_ascii=False, indent=1), "utf-8")
        if (ROOT / "data" / "shotplans" / f"{sid}.json").exists():
            subprocess.run([sys.executable, "engine/gen/plan.py", "research", sid], cwd=ROOT, capture_output=True, text=True, timeout=60)
        srcs = [f.get("source") for f in b["research"].get("facts") or [] if str(f.get("source") or "").startswith("http")]
        sb.setdefault("sources", list(dict.fromkeys((sb.get("sources") or []) + srcs)))
    sp = ROOT / "data" / "storyboards" / f"{sid}.json"
    sp.parent.mkdir(parents=True, exist_ok=True)
    if sp.exists():
        shutil.copyfile(sp, sp.with_suffix(".json.prev"))
    sp.write_text(json.dumps(sb, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return sid


def main() -> int:
    a = sys.argv[1:]
    if len(a) < 2 or a[0] not in ("apply", "check"):
        print(__doc__); return 2
    sid = apply(Path(a[1]) if Path(a[1]).is_absolute() else ROOT / a[1]) if a[0] == "apply" else a[1]
    if "--write-scenes" in a:                          # 장면 코드가 없는 장면을 장면마다 동시에 쓴다(engine/story/scenes.py) — 콘티 · 형태를 먼저 저장한 뒤
        sbx = json.loads((ROOT / "data" / "storyboards" / f"{sid}.json").read_text("utf-8"))
        sd = ROOT / "data" / "compositions" / sid / "scenes"
        need = [i for i in range(1, len(sbx.get("scenes") or []) + 1) if not (sd / f"s{i:02d}.jsx").exists()]
        if need:
            sys.path.insert(0, str(ROOT / "engine" / "story"))
            import scenes as _sc
            t0 = time.time()
            r = _sc.write(sid, need, "", 8)
            print(f"- 장면 코드 {len(need)}개를 동시에 씀: {round(time.time() - t0, 1)}초" + "".join(f" · 장면 {n} 문법 오류: {e}" for n, (_, e) in r["times"].items() if e))
    hard, soft = check(sid)
    for x in hard:
        print(f"✗ {x}")
    for x in soft[:12]:
        print(f"△ {x}")
    rel = f"data/storyboards/{sid}.json"
    if hard:
        fail("bundle", stage="check", error=f"막힘 {len(hard)}건 — 전부 한 번에 고친다(묶음을 Write 로 통째로 다시 쓰거나 Edit 를 한 응답에 나란히) → 다시 apply 한 번", file=rel, hard=str(len(hard)), soft=str(len(soft)))
    ok("bundle", file=rel, soft=str(len(soft)), next=f"python3 engine/produce.py {rel} --prep --bg → 재료 · 장면 확인 → python3 engine/produce.py {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
