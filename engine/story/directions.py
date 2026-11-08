#!/usr/bin/env python3
"""디자인 방향 시안 — 영상마다 '어떤 모양으로 만들지'를 사용자가 고르게 한다(에이전트가 혼자 정하지 않는다).

  python3 engine/story/directions.py propose data/storyboards/<id>.json [--scenes 1-3]
      시안 2~3개(레퍼런스대로 · 담백하게 · 움직임 조금 — craft/design.py proposals)를 장면 1~3 초안으로 나란히 렌더
      → data/out/<id>-variants.mp4 · 시안별 영상. 시안은 data/workspace/directions/<id>.json 에 남는다
  python3 engine/story/directions.py pick data/storyboards/<id>.json <번호 | 이름>
      고른 시안을 콘티 direction 에 넣고 잠근다(locked) — 이후 direct.py 가 자동으로 바꾸지 않는다
  python3 engine/story/directions.py show data/storyboards/<id>.json
      지금 콘티의 디자인 값(사용자 · 레퍼런스 · 효과 없음 중 어디서 왔는지)

시안을 고르기 전에는 전체 초안을 만들지 않는다(produce 스킬). 사용자가 '알아서'라고 하면 레퍼런스 시안(없으면 담백하게)을 고른다.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
from craft import design  # noqa: E402
from result import fail, ok  # noqa: E402

PY = sys.executable
STORE = ROOT / "data" / "workspace" / "directions"


def _rel(p: Path) -> str:
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def ref_design(sb: dict) -> dict:
    try:
        from look import look, xrays
        return design.from_reference(look(sb), xrays(sb))
    except Exception:  # noqa: BLE001
        return {}


def cmd_propose(sp: Path, scenes: str) -> None:
    sb = json.loads(sp.read_text("utf-8"))
    props = design.proposals(sb, ref_design(sb))
    STORE.mkdir(parents=True, exist_ok=True)
    (STORE / f"{sb['id']}.json").write_text(json.dumps(props, ensure_ascii=False, indent=1), "utf-8")
    # variants.py 로 렌더: 원본 콘티를 건드리지 않게 시안을 variants 칸으로 넘긴 사본을 쓴다
    tmp = dict(sb)
    tmp["variants"] = [{"name": p["name"], "direction": p["direction"]} for p in props]
    sp2 = STORE / f"{sb['id']}.storyboard.json"
    sp2.write_text(json.dumps(tmp, ensure_ascii=False, indent=1), "utf-8")
    r = subprocess.run([PY, str(ROOT / "engine" / "story" / "variants.py"), "render", str(sp2), "--scenes", scenes, "--no-original", "--sb-dir", str(STORE)],
                       cwd=ROOT, capture_output=True, text=True)
    sys.stdout.write(r.stdout[-4000:])
    if r.returncode != 0:
        fail("directions", stage="render", error=(r.stderr or r.stdout).strip()[-400:])
    lines = [f"{k + 1}. {p['name']}: " + ", ".join(f"{a}={json.dumps(b, ensure_ascii=False)}" for a, b in p["direction"].items() if a != "design_from")
             for k, p in enumerate(props)]
    ok("directions", proposals=lines, next=f"사용자에게 나란히 영상을 보여 주고 고르게 한다 → python3 engine/story/directions.py pick {_rel(sp)} <번호>")


def cmd_pick(sp: Path, which: str) -> None:
    sb = json.loads(sp.read_text("utf-8"))
    f = STORE / f"{sb['id']}.json"
    if not f.exists():
        fail("directions", stage="pick", error="시안이 없습니다 — 먼저 propose")
    props = json.loads(f.read_text("utf-8"))
    p = None
    if which.isdigit() and 1 <= int(which) <= len(props):
        p = props[int(which) - 1]
    else:
        p = next((x for x in props if which in x["name"]), None)
    if not p:
        fail("directions", stage="pick", error=f"'{which}' 시안이 없습니다(1~{len(props)} 또는 이름)")
    d = dict(sb.get("direction") or {})
    for k in d.get("_auto") or []:
        d.pop(k, None)
    d.update(p["direction"])
    d.update({"locked": True, "picked": p["name"], "_auto": []})
    sb["direction"] = d
    sp.write_text(json.dumps(sb, ensure_ascii=False, indent=2) + "\n", "utf-8")
    ok("directions", picked=p["name"], next=f"python3 engine/produce.py {_rel(sp)}")


def cmd_show(sp: Path) -> None:
    sb = json.loads(sp.read_text("utf-8"))
    d = sb.get("direction") or {}
    z = design.resolve(sb)
    src = "사용자가 고름(" + str(d.get("picked")) + ")" if d.get("locked") else {"reference": "레퍼런스에서 잼", "none": "근거 없음 → 효과 없음"}.get(d.get("design_from"), "정하지 않음 → 효과 없음")
    print(f"출처: {src}")
    for k in design.KEYS:
        mark = "자동" if k in (d.get("_auto") or []) else ("직접" if k in d else "기본")
        print(f"  {k:13s} {mark:3s} {json.dumps(z[k], ensure_ascii=False)}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("propose"); pr.add_argument("storyboard"); pr.add_argument("--scenes", default="1-3")
    pk = sub.add_parser("pick"); pk.add_argument("storyboard"); pk.add_argument("which")
    sh = sub.add_parser("show"); sh.add_argument("storyboard")
    a = ap.parse_args()
    sp = Path(a.storyboard)
    sp = sp if sp.is_absolute() else ROOT / sp
    if not sp.exists():
        fail("directions", stage="storyboard", error=f"콘티가 없습니다: {a.storyboard}")
    {"propose": lambda: cmd_propose(sp, a.scenes), "pick": lambda: cmd_pick(sp, a.which), "show": lambda: cmd_show(sp)}[a.cmd]()
    return 0


if __name__ == "__main__":
    from result import run_main
    run_main("directions", main)
