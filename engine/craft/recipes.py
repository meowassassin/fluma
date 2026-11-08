#!/usr/bin/env python3
"""검증된 다듬기 레시피 — 층별로 '이렇게 하면 프로답게 보인다'를 실제로 돌려 확인한 pass 틀(.claude/skills/refine/recipes/*.json).

  python3 engine/craft/recipes.py list [--layer typo]
  python3 engine/craft/recipes.py show <id>
  python3 engine/craft/recipes.py verify [<id> …]     # 시험 견본(engine/craft/probe.py 가 만든 것)에 다시 돌려 전 · 후 띠 · 통과 기록
  세션에서: python3 engine/craft/session.py try <콘티> <장면> --target motion --recipe typo-stagger-chars --vars TEXT="Sub 01"

레시피 파일
  { "id", "layer", "target": "motion" | "material", "app", "title", "when": "언제 쓰나", "avoid": "쓰면 안 될 때",
    "vars": {"TEXT": "글자 레이어 이름", …}(필요한 이름), "defaults": {"T0": 0, …},
    "steps": [ {"id": "명령", "params": {…}} | {"jsx": "코드"} ],   # jsx = EffectCraft script.run — 앞에 공통 도우미(PRELUDE)가 붙는다
    "at": [보여 줄 시각 …], "verified": {"ok", "msg", "thumb", "app_version"} }
자리 @NAME@ 은 vars · defaults · 장면 값(COMP · SEC)으로 채운다. 펼친 결과가 콘티에 남으므로 레시피 파일 없이도 다시 제작된다.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
from craft.materials import cli  # noqa: E402

DIR = ROOT / ".claude" / "skills" / "refine" / "recipes"
WORK = ROOT / "data" / "workspace" / "probe" / "recipes"
_TOK = re.compile(r"@([A-Z][A-Z0-9_]*)@")

# EffectCraft JSX 공통 도우미 — 컴프 · 레이어 찾기, 효과 · 속성, 키프레임, 이징(속도 0 · 영향 %)
PRELUDE = r"""var C=(function(){for(var i=1;i<=app.project.numItems;i++){var it=app.project.item(i);if(it instanceof CompItem&&it.name=="@COMP@")return it;}throw new Error("컴프 없음: @COMP@");})();
function L(n){var l=C.layer(n);if(!l)throw new Error("레이어 없음: "+n);return l;}
function FX(l,name){var f=l.property("Effects").addProperty(name);if(!f)throw new Error("효과 없음: "+name);return f;}
function P(g,name){var p=g.property(name);if(!p)throw new Error("속성 없음: "+name);return p;}
function K(p,pairs){for(var i=0;i<pairs.length;i++)p.setValueAtTime(pairs[i][0],pairs[i][1]);}
function EASE(p,inf){inf=inf||75;for(var k=1;k<=p.numKeys;k++){var v=p.keyValue(k);var n=(v instanceof Array)?v.length:1;var e=[];for(var d=0;d<n;d++)e.push(new KeyframeEase(0,inf));try{p.setTemporalEaseAtKey(k,e,e);}catch(x){var e1=[new KeyframeEase(0,inf)];p.setTemporalEaseAtKey(k,e1,e1);}}}
function ADJ(name){var a=C.layers.addSolid([1,1,1],name,C.width,C.height,1);a.adjustmentLayer=true;return a;}
"""

# 시험 견본의 이름(probe.py 견본) — verify 가 쓴다
SAMPLE = {"effectcraft": {"COMP": "Probe", "TEXT": "Title", "MAT": "Image", "SHAPE": "Shape", "BG": "BG", "SEC": 4},
          "photocraft": {"PIXEL": "Layer 0", "TEXT": "Title", "SHAPE": "Shape"}}


def load(rid: str | None = None) -> list[dict]:
    out = [json.loads(f.read_text("utf-8")) for f in sorted(DIR.glob("*.json"))]
    return [r for r in out if r["id"] == rid] if rid else out


def _sub(o, v: dict):
    if isinstance(o, str):
        def rep(m):
            k = m.group(1)
            if k not in v:
                raise KeyError(k)
            x = v[k]
            return json.dumps(x, ensure_ascii=False)[1:-1] if isinstance(x, str) else json.dumps(x)
        s = _TOK.sub(rep, o)
        if _TOK.fullmatch(o) and not isinstance(v.get(o.strip("@")), str):
            return v[o.strip("@")]
        return s
    if isinstance(o, dict):
        return {k: _sub(x, v) for k, x in o.items()}
    if isinstance(o, list):
        return [_sub(x, v) for x in o]
    return o


def expand(r: dict, vars_: dict) -> dict:
    """레시피 → 콘티에 남길 pass(자리 채움 · jsx 는 script.run 으로)"""
    v = {**(r.get("defaults") or {}), **vars_}
    miss = [k for k in (r.get("vars") or {}) if k not in v]
    if miss:
        raise SystemExit(f"레시피 {r['id']}: 이름이 필요합니다 — " + ", ".join(f"{k}({r['vars'][k]})" for k in miss))
    steps = []
    for s in r["steps"]:
        if "jsx" in s:
            code = PRELUDE + s["jsx"]
            try:
                steps.append({"id": "script.run", "params": {"code": _sub(code, v), "name": r["id"]}})
            except KeyError as e:
                raise SystemExit(f"레시피 {r['id']}: @{e.args[0]}@ 값이 없습니다(--vars {e.args[0]}=…)")
        else:
            steps.append({"id": s["id"], "params": _sub(s.get("params") or {}, v)})
    p = {"layer": r["layer"], "steps": steps, "why": r.get("when") or r["title"], "recipe": r["id"]}
    if r["target"] == "material":
        p["app"] = r["app"]
    return p


# ---------------------------------------------------------------- 검증
def _strip(frames: list[Path], out: Path) -> None:
    from PIL import Image
    ims = [Image.open(f).convert("RGB") for f in frames if f.exists()]
    if not ims:
        return
    s = Image.new("RGB", (sum(i.width for i in ims) + 6 * (len(ims) - 1), ims[0].height), (255, 255, 255))
    x = 0
    for i in ims:
        s.paste(i, (x, 0)); x += i.width + 6
    s.save(out)


def _ec_render(ec: str, proj: Path, t: float, out: Path, env: dict) -> Path:
    subprocess.run([ec, "render-frame", "--project", str(proj), "--comp", "Probe", "--time", str(t), "--max-side", "360", "--out", str(out)],
                   capture_output=True, text=True, env=env, timeout=120)
    return out


def verify_one(r: dict) -> dict:
    from craft.probe import WORK as PW, env
    from craft.refine import subst
    e = env()
    d = WORK / r["id"]
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    app = r["app"]
    p = expand(r, SAMPLE.get(app, {}))
    if app == "effectcraft":
        base = PW / "effectcraft" / "sample.ecproj"
        if not base.exists():
            return {"ok": False, "msg": "시험 견본이 없습니다 — python3 engine/craft/probe.py effectcraft --part states"}
        ec = str(cli("effectcraft"))
        cp = d / "t.ecproj"
        shutil.copyfile(base, cp)
        steps = [{"command": "comp.open", "params": {"comp": "Probe"}}] + [{"command": s["id"], "params": subst(s["params"], {"COMP": "Probe"})} for s in p["steps"]]
        f = d / "steps.json"
        f.write_text(json.dumps(steps, ensure_ascii=False), "utf-8")
        rr = subprocess.run([ec, "run", "--commands", str(f), "--project", str(cp), "--save"], capture_output=True, text=True, env=e, timeout=300)
        out = rr.stdout + rr.stderr
        err = re.search(r'"error":\s*\{[^}]*"message":\s*"([^"]+)"', out)
        if rr.returncode != 0 or err:
            return {"ok": False, "msg": re.sub(r"\s+", " ", (err.group(1) if err else out))[-300:]}
        at = r.get("at") or [0.2, 1.0, 2.5]
        _strip([_ec_render(ec, base, t, d / f"b{k}.png", e) for k, t in enumerate(at)], d / "before.png")
        _strip([_ec_render(ec, cp, t, d / f"a{k}.png", e) for k, t in enumerate(at)], d / "after.png")
    elif app == "photocraft":
        from craft.adapters.craft_script import craft
        base = PW / "photocraft" / "sample.psd"
        if not base.exists():
            return {"ok": False, "msg": "시험 견본이 없습니다 — python3 engine/craft/probe.py photocraft --part states"}
        try:
            craft({"type": "craft", "id": "t", "app": "photocraft", "open": str(base.relative_to(ROOT)), "steps": p["steps"]}, d / "after.png", d)
        except RuntimeError as x:
            return {"ok": False, "msg": str(x)[-300:]}
        shutil.copyfile(PW / "photocraft" / "base.png", d / "before.png")
    else:
        return {"ok": False, "msg": f"{app} 검증은 아직 없음"}
    from craft.probe import diff
    v = diff(d / "before.png", d / "after.png") if (d / "after.png").exists() else 0
    return {"ok": v > 0.3, "diff": v, "msg": None if v > 0.3 else "적용은 됐지만 화면 변화가 없음",
            "thumb": str((d / "after.png").relative_to(ROOT)), "before": str((d / "before.png").relative_to(ROOT))}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    ls = sub.add_parser("list"); ls.add_argument("--layer")
    sh = sub.add_parser("show"); sh.add_argument("id")
    vf = sub.add_parser("verify"); vf.add_argument("ids", nargs="*")
    a = ap.parse_args()
    if a.cmd == "list":
        for r in load():
            if a.layer and r["layer"] != a.layer:
                continue
            ok = (r.get("verified") or {}).get("ok")
            print(f"{r['layer']:11s} {r['id']:28s} {r['app']:12s} {'✓' if ok else '✗' if ok is False else '?'} {r['title']} — {r.get('when', '')[:60]}")
        return 0
    if a.cmd == "show":
        r = load(a.id)
        if not r:
            print("없음"); return 1
        print(json.dumps(r[0], ensure_ascii=False, indent=1)); return 0
    from collections import defaultdict
    rows = [r for r in load() if not a.ids or r["id"] in a.ids]
    by = defaultdict(list)
    for r in rows:
        res = verify_one(r)
        r["verified"] = res
        (DIR / f"{r['id']}.json").write_text(json.dumps(r, ensure_ascii=False, indent=1) + "\n", "utf-8")
        print(f"{'✓' if res['ok'] else '✗'} {r['id']:28s} {res.get('diff', '')} {res.get('msg') or ''}")
        if res.get("thumb"):
            by[r["layer"]].append(r)
    # 층마다 전 · 후 판
    from PIL import Image, ImageDraw
    for layer, rs in by.items():
        ims = []
        for r in rs:
            b, t = Image.open(ROOT / r["verified"]["before"]).convert("RGB"), Image.open(ROOT / r["verified"]["thumb"]).convert("RGB")
            w = 900
            b, t = b.resize((w, int(b.height * w / b.width))), t.resize((w, int(t.height * w / t.width)))
            im = Image.new("RGB", (w, b.height + t.height + 40), (250, 250, 250))
            im.paste(b, (0, 0)); im.paste(t, (0, b.height + 6))
            ImageDraw.Draw(im).text((6, b.height + t.height + 12), f"{r['id']} (위: 전 · 아래: 후)", fill=(0, 0, 0))
            ims.append(im)
        sheet = Image.new("RGB", (max(i.width for i in ims), sum(i.height for i in ims) + 10 * len(ims)), (255, 255, 255))
        y = 0
        for i in ims:
            sheet.paste(i, (0, y)); y += i.height + 10
        sheet.save(WORK / f"sheet-{layer}.png")
        print(f"판: {(WORK / f'sheet-{layer}.png').relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
