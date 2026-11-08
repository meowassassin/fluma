#!/usr/bin/env python3
"""작업 세션 — 에이전트가 전문가처럼 장면을 '열고 → 시도하고 → 렌더해서 보고 → 남기는' 도구(engine/craft/refine.py 의 다듬기 기록).

  python3 engine/craft/session.py show <콘티> <장면>
      장면 재료(앱 · 결과 · 편집 파일) · 장면 컴프 레이어 이름 · 이미 남긴 다듬기 · 디테일 계획과 빠진 층
  python3 engine/craft/session.py plan <콘티> <장면> typo="제목 위계 3단 · 핵심어만 굵게" light="오른쪽 위 빛 번짐" …
      장면 디테일 계획(scenes[i].detail) — 층마다 무엇을 할지 한 줄. 빈 값이면 그 층을 지운다
  python3 engine/craft/session.py try <콘티> <장면> (--target motion|sound|edit | --material <id>) --pass <JSON|파일> [--at 초,초]
      콘티는 그대로 두고 사본에 적용해 전 · 후를 렌더 → data/workspace/session/<id>/ 의 PNG(소리는 WAV) 경로를 찍는다. 그림을 보고 고친다
  python3 engine/craft/session.py keep <콘티> <장면> (--target … | --material <id>) --pass <JSON|파일>
      검사(층 · 근거 · 명령 id)를 통과하면 콘티에 남긴다 → 다음 제작부터 늘 적용
  python3 engine/craft/session.py drop <콘티> <장면> (--target … | --material <id>) <번호>
  python3 engine/craft/session.py coverage <콘티>
      앱 × 디테일 층 다듬기 표 · 계획했는데 다듬지 않은 층

pass = {"layer": "typo", "app": "photocraft"(재료만), "steps": [{"id": "...", "params": {...}}], "why": "근거"}
장면 0 = 영상 전체(sb.refine). 명령은 craft_catalog.py search "<하고 싶은 일>", 층별 기법은 .claude/skills/refine/SKILL.md.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
from craft import refine  # noqa: E402
from craft.materials import cli  # noqa: E402
from result import fail, ok  # noqa: E402

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"


def _rel(p: Path) -> str:
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def _load(sp: Path) -> dict:
    return json.loads(sp.read_text("utf-8"))


def _save(sp: Path, sb: dict) -> None:
    sp.write_text(json.dumps(sb, ensure_ascii=False, indent=2) + "\n", "utf-8")


def _recipe_pass(a, sb: dict, n: int) -> dict:
    """--recipe <id> --vars K=V … → 펼친 pass(장면 컴프 · 길이는 자동)"""
    from craft import recipes
    r = recipes.load(a.recipe)
    if not r:
        fail("session", stage="recipe", error=f"레시피 '{a.recipe}' 없음 — python3 engine/craft/recipes.py list")
    v = {}
    if n:
        vv = refine.vars_for(sb, n - 1)
        v = {"COMP": vv["COMP"], "SEC": vv["SEC"]}
    for it in a.vars or []:
        k, _, x = it.partition("=")
        try:
            v[k.strip()] = json.loads(x)
        except ValueError:
            v[k.strip()] = x
    p = recipes.expand(r[0], v)
    if a.why:
        p["why"] = a.why
    return p


def _pass(v: str) -> dict:
    p = Path(v)
    o = json.loads(p.read_text("utf-8") if p.exists() else v)
    if isinstance(o, list):
        o = {"steps": o}
    for s in o.get("steps") or []:
        if "command" in s and "id" not in s:
            s["id"] = s.pop("command")
    return o


def _craft_dir(sid: str) -> Path:
    return ROOT / "data" / "compositions" / sid / "craft"


def _work(sid: str, n: int) -> Path:
    d = ROOT / "data" / "workspace" / "session" / sid / f"s{n:02d}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _scene(sb: dict, n: int) -> dict:
    scs = sb.get("scenes") or []
    if not 1 <= n <= len(scs):
        fail("session", stage="scene", error=f"장면은 1~{len(scs)}(0 = 영상 전체)")
    return scs[n - 1]


def _material(sc: dict, mid: str) -> dict:
    for m in sc.get("materials") or []:
        if str(m.get("id")) == mid:
            return m
    fail("session", stage="material", error=f"이 장면에 재료 '{mid}' 가 없습니다: {[m.get('id') for m in sc.get('materials') or []]}")


def _ecproj(sb: dict) -> Path:
    from engines import aspect_tag
    return _craft_dir(sb["id"]) / "motion" / f"{sb['id']}{aspect_tag(sb)}.ecproj"


def comp_layers(proj: Path) -> dict[str, list[str]]:
    ec = cli("effectcraft")
    if not ec or not proj.exists():
        return {}
    js = ('var o={};for(var i=1;i<=app.project.numItems;i++){var it=app.project.item(i);if(it instanceof CompItem){var L=[];'
          'for(var j=1;j<=it.numLayers;j++){var l=it.layer(j);L.push(l.name+" "+l.inPoint.toFixed(2)+"~"+l.outPoint.toFixed(2)+"s");}o[it.name]=L;}}'
          'writeLn(JSON.stringify(o));')
    r = subprocess.run([str(ec), "script", "--eval", js, str(proj)], capture_output=True, text=True, timeout=120)
    for ln in r.stdout.splitlines():
        if ln.startswith("{"):
            try:
                return json.loads(ln)
            except ValueError:
                pass
    return {}


def editable_layers(app: str | None, f: Path) -> list[str]:
    """재료 편집 파일 안 레이어(다듬기 명령이 이름으로 고른다 — 예: PhotoCraft layer.select {"name": "Backdrop"})"""
    c = cli(app) if app else None
    if not c or not f.exists():
        return []
    try:
        if app == "photocraft":
            r = subprocess.run([str(c), "run", str(f), "--cmd", "layer.list", "--params", '{"flat":true}'], capture_output=True, text=True, timeout=120)
            o = json.loads(r.stdout[r.stdout.index("{"):].splitlines()[0])
            return [f"{x['name']} ({x['kind']}{'' if x.get('visible') else ' · 숨김'})" for x in o["result"]["layers"]]
        r = subprocess.run([str(c), "info", str(f)], capture_output=True, text=True, timeout=120)
        o = json.loads(r.stdout[r.stdout.index("{"):]) if "{" in r.stdout else {}
        names = []

        def walk(x, depth=0):
            if isinstance(x, dict):
                nm = x.get("name")
                if nm and (x.get("kind") or x.get("type")) and depth <= 6:
                    names.append("  " * min(depth, 3) + f"{nm} ({x.get('kind') or x.get('type')})")
                for v in x.values():
                    if isinstance(v, (dict, list)):
                        walk(v, depth + 1)
            elif isinstance(x, list):
                for v in x:
                    walk(v, depth)
        walk(o)
        return names[:40]
    except (ValueError, KeyError, subprocess.TimeoutExpired):
        return []


# ---------------------------------------------------------------- show · plan · coverage
def cmd_show(sp: Path, n: int) -> None:
    sb = _load(sp)
    sc = _scene(sb, n)
    sid = sb["id"]
    print(f"[{n}장면] {sc.get('role')} · {sc.get('sec')}초 · 컴프 '{refine.comp_name(sb, n - 1)}'")
    print("재료:")
    for m in sc.get("materials") or []:
        rp = _craft_dir(sid) / "materials" / f"s{n:02d}" / f"{m.get('id')}.json"
        rec = json.loads(rp.read_text("utf-8")) if rp.exists() else {}
        print(f"  {m.get('id')}  {m.get('type')}  앱={rec.get('refined_app') or rec.get('app')}  결과={rec.get('file')}  "
              f"편집={rec.get('refined_editable') or rec.get('editable')}  다듬기={len(m.get('refine') or [])}")
        ed = rec.get("refined_editable") or rec.get("editable")
        for x in editable_layers(rec.get("refined_app") or rec.get("app"), ROOT / ed) if ed else []:
            print(f"      · {x}")
    lay = comp_layers(_ecproj(sb)).get(refine.comp_name(sb, n - 1)) or []
    print("장면 컴프 레이어(움직임 다듬기에서 이름으로 가리킨다):" + ("" if lay else " (아직 렌더 전 — produce 한 번 뒤에 보인다)"))
    for x in lay:
        print(f"  {x}")
    print("다듬기 기록:")
    for k, p in enumerate(sc.get("refine") or [], 1):
        print(f"  {k}. {p.get('target')} · {p.get('layer')} · 명령 {len(p.get('steps') or [])}개 — {p.get('why')}")
    print("디테일 계획:")
    cov = refine.coverage(sb)
    miss = {ly for s, ly in cov["missing"] if s == n}
    for ly, what in (sc.get("detail") or {}).items():
        print(f"  {ly:11s} {'(아직 안 다듬음) ' if ly in miss else ''}{what}")
    if not sc.get("detail"):
        print("  없음 — plan 으로 층마다 할 일을 먼저 적는다(" + " · ".join(refine.LAYERS) + ")")


def cmd_plan(sp: Path, n: int, items: list[str]) -> None:
    sb = _load(sp)
    sc = _scene(sb, n)
    det = dict(sc.get("detail") or {})
    for it in items:
        k, _, v = it.partition("=")
        k = k.strip()
        if k not in refine.LAYERS:
            fail("session", stage="plan", error=f"'{k}' 는 층 이름이 아닙니다: {' · '.join(refine.LAYERS)}")
        if v.strip():
            det[k] = v.strip()
        else:
            det.pop(k, None)
    sc["detail"] = det
    _save(sp, sb)
    ok("session", scene=n, detail=det)


def cmd_coverage(sp: Path) -> None:
    sb = _load(sp)
    cov = refine.coverage(sb)
    lays = list(refine.LAYERS)
    print("앱".ljust(14) + "".join(x[:10].ljust(12) for x in lays))
    for app, row in sorted(cov["grid"].items()):
        print(app.ljust(14) + "".join((f"{row[x][0]}회/{row[x][1]}" if x in row else "·").ljust(12) for x in lays))
    if not cov["grid"]:
        print("(다듬기 없음 — 초벌 그대로)")
    for s, ly in cov["missing"]:
        print(f"계획했는데 안 다듬음: {s}장면 {ly} — {(sb['scenes'][s - 1].get('detail') or {}).get(ly)}")


# ---------------------------------------------------------------- try
def _frames(ec: Path, proj: Path, comp: str, at: list[float], out: Path, tag: str) -> list[str]:
    res = []
    for t in at:
        p = out / f"{tag}-{t:05.2f}.png"
        r = subprocess.run([str(ec), "render-frame", "--project", str(proj), "--comp", comp, "--time", str(t), "--max-side", "960", "--out", str(p)],
                           capture_output=True, text=True, timeout=180)
        if r.returncode != 0:
            fail("session", stage="render-frame", error=(r.stderr or r.stdout)[-400:])
        res.append(_rel(p))
    return res


def try_motion(sb: dict, n: int | None, p: dict, at: list[float] | None) -> dict:
    ec = cli("effectcraft")
    proj = _ecproj(sb)
    if not ec or not proj.exists():
        fail("session", stage="motion", error="움직임 프로젝트가 없습니다 — produce 를 한 번 돌린 뒤")
    w = _work(sb["id"], n or 0)
    cp = w / "try.ecproj"
    shutil.copyfile(proj, cp)
    v = refine.vars_for(sb, n - 1 if n else None)
    steps = [{"command": "comp.open", "params": {"comp": v["COMP"]}}] + [{"command": s["id"], "params": refine.subst(s.get("params") or {}, v)} for s in p["steps"]]
    f = w / "try.motion.json"
    f.write_text(json.dumps(steps, ensure_ascii=False, indent=1), "utf-8")
    r = subprocess.run([str(ec), "run", "--commands", str(f), "--project", str(cp), "--save"], capture_output=True, text=True, timeout=600)
    bad = refine.script_failures(r.stdout)
    if r.returncode != 0 or bad:
        fail("session", stage="motion", error=" / ".join(bad[:5]) or (r.stderr or r.stdout)[-600:])
    at = at or [round(float(v.get("SEC") or 2) / 2, 2)]
    return {"before": _frames(ec, proj, v["COMP"], at, w, "before"), "after": _frames(ec, cp, v["COMP"], at, w, "after")}


def try_edit(sb: dict, n: int | None, p: dict, at: list[float] | None) -> dict:
    from craft.edit import _run_script
    fc = cli("filmcraft")
    proj = _craft_dir(sb["id"]) / "edit" / f"{sb['id']}.fcproj"
    if not fc or not proj.exists():
        fail("session", stage="edit", error="편집 프로젝트가 없습니다 — produce 를 한 번 돌린 뒤")
    w = _work(sb["id"], n or 0)
    cp = w / "try.fcproj"
    shutil.copyfile(proj, cp)
    v = refine.vars_for(sb, n - 1 if n else None)
    try:
        _run_script(fc, cp, [{"id": s["id"], "params": refine.subst(s.get("params") or {}, v)} for s in p["steps"]], cwd=w)
    except RuntimeError as e:
        fail("session", stage="edit", error=str(e)[-600:])
    at = at or [float(v.get("MID") or 1)]
    out = {"before": [], "after": []}
    for tag, pr in (("before", proj), ("after", cp)):
        for t in at:
            png = w / f"{tag}-{t:06.2f}.png"
            subprocess.run([str(fc), "--project", str(pr), "render", "--seconds", str(t), "--out", str(png)], capture_output=True, text=True, timeout=300)
            out[tag].append(_rel(png))
    return out


def try_sound(sb: dict, n: int | None, p: dict) -> dict:
    sc_cli = cli("soundcraft")
    sess = _craft_dir(sb["id"]) / "audio" / f"{sb['id']}.scraft"
    if not sc_cli or not sess.exists():
        fail("session", stage="sound", error="소리 세션이 없습니다 — produce 를 한 번 돌린 뒤")
    w = _work(sb["id"], n or 0)
    cp = w / "try.scraft"
    shutil.copyfile(sess, cp)
    v = refine.vars_for(sb, n - 1 if n else None)
    cmds = [x for s in p["steps"] for x in ("--cmd", f"{s['id']}={json.dumps(refine.subst(s.get('params') or {}, v), ensure_ascii=False)}")]
    end = refine.scene_times(sb)[-1][1]
    wav = w / "after.wav"
    r = subprocess.run([str(sc_cli), "run", "--in", str(cp), "--in-place", "--save", str(cp), *cmds, "--bounce", str(wav), "--end", f"{end:.3f}"],
                       capture_output=True, text=True, timeout=600, env={**__import__("os").environ, "SOUNDCRAFT_NO_PREFS": "1"})
    if r.returncode != 0 or not wav.exists():
        fail("session", stage="sound", error=(r.stderr or r.stdout)[-600:])
    out = {"after_full": _rel(wav)}
    before = _craft_dir(sb["id"]) / "audio" / f"{sb['id']}.mix.wav"
    if n:
        a, b = refine.scene_times(sb)[n - 1]
        for tag, src in (("before", before), ("after", wav)):
            if src.exists():
                dst = w / f"{tag}.scene.wav"
                subprocess.run([FFMPEG, "-y", "-v", "error", "-ss", str(a), "-to", str(b), "-i", str(src), str(dst)], check=False)
                out[tag] = _rel(dst)
    return out


def try_material(sb: dict, n: int, mid: str, p: dict) -> dict:
    rp = _craft_dir(sb["id"]) / "materials" / f"s{n:02d}" / f"{mid}.json"
    if not rp.exists():
        fail("session", stage="material", error="재료가 아직 없습니다 — produce 를 한 번 돌린 뒤")
    rec = json.loads(rp.read_text("utf-8"))
    if not rec.get("file"):
        fail("session", stage="material", error=f"재료 {mid} 는 파일이 없습니다(글자 · 수치 카드는 움직임 다듬기로)")
    base = {**rec, "editable": rec.get("refined_editable") or rec.get("editable"), "app": rec.get("refined_app") or rec.get("app")}
    w = _work(sb["id"], n)
    try:
        got = refine.apply_material(base, {"id": f"try-{mid}", "refine": [p]}, w)
    except RuntimeError as e:
        fail("session", stage="material", error=str(e)[-600:])
    return {"before": rec["file"], "after": got["file"], "editable": got.get("refined_editable")}


def _target(a) -> tuple[str, str | None]:
    if bool(a.target) == bool(a.material):
        fail("session", stage="args", error="--target(motion · sound · edit) 또는 --material <id> 중 하나")
    return (a.target, None) if a.target else ("material", a.material)


def cmd_try(sp: Path, n: int, a) -> None:
    sb = _load(sp)
    p = _recipe_pass(a, sb, n) if a.recipe else _pass(a.pass_)
    kind, mid = _target(a)
    at = [float(x) for x in a.at.split(",")] if a.at else None
    if kind == "material":
        _scene(sb, n)
        res = try_material(sb, n, mid, p)
    else:
        if n:
            _scene(sb, n)
        res = {"motion": lambda: try_motion(sb, n, p, at), "edit": lambda: try_edit(sb, n, p, at), "sound": lambda: try_sound(sb, n, p)}[kind]()
    ok("session", tried=kind, **res, next="전 · 후를 열어 보고 고친다. 마음에 들면 같은 인자로 keep(layer · why 를 채워서)")


# ---------------------------------------------------------------- keep · drop
def _bucket(sb: dict, n: int, kind: str, mid: str | None) -> list:
    if kind == "material":
        return _material(_scene(sb, n), mid).setdefault("refine", [])
    if n == 0:
        return sb.setdefault("refine", [])
    return _scene(sb, n).setdefault("refine", [])


def cmd_keep(sp: Path, n: int, a) -> None:
    sb = _load(sp)
    p = _recipe_pass(a, sb, n) if a.recipe else _pass(a.pass_)
    kind, mid = _target(a)
    if kind != "material":
        p = {"target": kind, **{k: v for k, v in p.items() if k != "app"}}
    _bucket(sb, n, kind, mid).append(p)
    errs = refine.validate(sb)
    if errs:
        fail("session", stage="keep", error=" / ".join(errs[:6]))
    _save(sp, sb)
    ok("session", kept=f"{n}장면 {kind}{' ' + mid if mid else ''} · {p.get('layer')} · 명령 {len(p.get('steps') or [])}개",
       next=f"python3 engine/produce.py {_rel(sp)}  (다음 제작부터 늘 적용)")


def cmd_drop(sp: Path, n: int, a) -> None:
    sb = _load(sp)
    kind, mid = _target(a)
    b = _bucket(sb, n, kind, mid)
    if not 1 <= a.index <= len(b):
        fail("session", stage="drop", error=f"번호는 1~{len(b)}")
    gone = b.pop(a.index - 1)
    _save(sp, sb)
    ok("session", dropped=f"{gone.get('layer')} — {gone.get('why')}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("show", "plan", "try", "keep", "drop", "coverage"):
        x = sub.add_parser(name)
        x.add_argument("storyboard")
        if name != "coverage":
            x.add_argument("scene", type=int)
        if name == "plan":
            x.add_argument("items", nargs="*")
        if name in ("try", "keep", "drop"):
            x.add_argument("--target", choices=list(refine.TARGETS))
            x.add_argument("--material")
        if name in ("try", "keep"):
            g = x.add_mutually_exclusive_group(required=True)
            g.add_argument("--pass", dest="pass_", help="pass JSON 또는 파일")
            g.add_argument("--recipe", help="검증된 레시피 id(engine/craft/recipes.py list)")
            x.add_argument("--vars", nargs="*", help="레시피 이름 채우기 TEXT='Sub 01' MAT='Mat card' T0=0.5")
            x.add_argument("--why", help="레시피를 쓰는 근거(없으면 레시피의 when)")
        if name == "try":
            x.add_argument("--at", help="장면 안 초(움직임) · 영상 초(편집), 쉼표로 여러 개")
        if name == "drop":
            x.add_argument("index", type=int)
    a = ap.parse_args()
    sp = Path(a.storyboard)
    sp = sp if sp.is_absolute() else ROOT / sp
    if not sp.exists():
        fail("session", stage="storyboard", error=f"콘티가 없습니다: {a.storyboard}")
    n = getattr(a, "scene", 0)
    {"show": lambda: cmd_show(sp, n), "plan": lambda: cmd_plan(sp, n, a.items), "try": lambda: cmd_try(sp, n, a),
     "keep": lambda: cmd_keep(sp, n, a), "drop": lambda: cmd_drop(sp, n, a), "coverage": lambda: cmd_coverage(sp)}[a.cmd]()
    return 0


if __name__ == "__main__":
    from result import run_main
    run_main("session", main)
