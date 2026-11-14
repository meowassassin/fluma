#!/usr/bin/env python3
"""편집기 효과 모듈 — 영상 편집기(엔진 2)의 요소 하나에 Craft(EffectCraft) 효과 · 애니메이션 프리셋 · Fluma 레시피를 입혀 투명 배경 층으로 렌더한다.

편집기는 효과를 직접 그리지 않는다. 요소(글자 · 영상 · 그림)의 모양을 보내면 여기서 EffectCraft 컴프를 만들어
효과를 걸고 RGBA(webm VP9 + 알파)로 렌더한다 → 편집기가 그 요소를 렌더된 층으로 바꾼다(원래 요소는 되돌리기용으로 남김).
초안 · 최종과 같은 엔진이라 결과가 정확하다.

  python3 engine/craft/fxlayer.py list [--target text|video|image] [--q 낱말]     # 고를 수 있는 효과 목록(JSON)
  python3 engine/craft/fxlayer.py render <영상 id> <spec.json | ->                 # 렌더 → {"file","url","sec","cached"}

spec:
{ "target": "text"|"video"|"image", "canvas": {"w":1080,"h":1920,"fps":30}, "duration": 2.0,
  "text":  {"content","fontFamily","fontPx","bold","italic","color":"#fff","align":"center","x":0,"y":0,"tracking":0,"leading":1.2,
            "stroke": {"color","width"}?, "skew": 0},
  "media": {"src": "<저장소 상대 경로 또는 /api/… 주소>", "trimStart": 0, "x":0, "y":0, "scaleX":1, "scaleY":1, "rotate":0},
  "effect": {"kind": "effect"|"preset"|"textPreset"|"recipe", "id": "...", "params": {...}} }
x · y 는 캔버스 가운데 기준 px(편집기 transform.position 과 같음).
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
from craft.materials import cli  # noqa: E402
from craft import recipes as rec  # noqa: E402

CATALOG = ROOT / ".claude" / "skills" / "crafts" / "catalog" / "effectcraft.jsonl"
THUMBS = ROOT / "data" / "workspace" / "probe" / "recipes"
FONT_DIR = Path.home() / ".local" / "share" / "fonts" / "fluma"

# 편집에 쓸모없는 묶음(3D 채널 · 오디오 · 표현식 · 360 · 옛것 · 도구)은 뺀다
SKIP_MENU = {"3D Channel", "Audio", "Expression Controls", "Immersive Video", "Obsolete", "Utility"}
MENU_KO = {
    "Blur & Sharpen": "흐림 · 선명", "Channel": "채널", "Color Correction": "색 보정", "Distort": "왜곡", "Generate": "생성",
    "Keying": "키잉(배경 빼기)", "Matte": "매트", "Noise & Grain": "노이즈 · 그레인", "Perspective": "원근 · 그림자", "Simulation": "시뮬레이션",
    "Stylize": "스타일", "Text": "글자", "Time": "시간", "Transition": "전환 효과", "Paint": "페인트",
    "Transitions": "등장 · 퇴장", "Behaviors": "움직임", "Backgrounds": "배경",
}
TEXT_PRESETS = {
    "typewriter": "타자기", "fadeUpCharacters": "한 자씩 떠오르기", "bounceInWords": "단어 튀어나오기", "trackingIn": "자간 모으며 등장",
    "scramble": "글자 뒤섞이다 맞춰짐", "blurIn": "흐림에서 또렷하게", "jitter": "글자 떨림", "dropInLines": "줄마다 떨어지기",
}


# ---------------------------------------------------------------- 목록
def _catalog() -> list[dict]:
    if not CATALOG.exists():
        return []
    return [json.loads(x) for x in CATALOG.read_text("utf-8").splitlines() if x.strip()]


def _params(raw) -> list[dict]:
    try:
        ps = json.loads(raw) if isinstance(raw, str) and raw.startswith("[") else []
    except json.JSONDecodeError:
        return []
    out = []
    for p in ps:
        if p.get("type") in ("number", "float", "int", "angle", "percent", "slider", "bool", "checkbox", "color", "enum") and p.get("type") != "layer":
            out.append({k: p.get(k) for k in ("id", "name", "type", "default", "min", "max", "options", "decimals") if p.get(k) is not None})
    return out


def _recipe_ok(r: dict, target: str) -> bool:
    """편집기 요소 하나에 걸 수 있는 레시피 — EffectCraft · 이름은 TEXT/MAT 만(나머지는 기본값 있음)"""
    if r.get("app") != "effectcraft" or r.get("target") != "motion" or not (r.get("verified") or {}).get("ok"):
        return False
    need = [k for k in (r.get("vars") or {}) if k not in (r.get("defaults") or {})]
    if target == "text":
        return set(need) <= {"TEXT"}
    return set(need) <= {"MAT"} and "TEXT" not in need


def listing(target: str = "video", q: str = "") -> list[dict]:
    items: list[dict] = []
    for r in rec.load():
        if _recipe_ok(r, target):
            thumb = THUMBS / r["id"] / "after.png"
            items.append({"kind": "recipe", "id": r["id"], "label": r["title"], "group": "Fluma 레시피", "summary": r.get("when") or "",
                          "thumb": f"/api/craft-fx/thumb/{r['id']}" if thumb.exists() else None})
    if target == "text":
        items += [{"kind": "textPreset", "id": k, "label": v, "group": "글자 애니메이션", "summary": k} for k, v in TEXT_PRESETS.items()]
    for d in _catalog():
        if d["kind"] == "preset" and d["menu"] in ("Transitions", "Behaviors"):
            items.append({"kind": "preset", "id": d["id"], "label": d["label"], "group": MENU_KO[d["menu"]], "summary": d.get("summary") or ""})
    for d in _catalog():
        if d["kind"] == "effect" and d["menu"] not in SKIP_MENU:
            if target != "video" and d["menu"] in ("Time", "Keying"):
                continue
            items.append({"kind": "effect", "id": d["id"], "label": d["label"], "group": MENU_KO.get(d["menu"], d["menu"]),
                          "summary": d.get("summary") or "", "params": _params(d.get("params"))})
    if q:
        ql = q.lower()
        items = [x for x in items if ql in f"{x['label']} {x['group']} {x['summary']} {x['id']}".lower()]
    return items


# ---------------------------------------------------------------- 글꼴
def _font_name(family: str, bold: bool, italic: bool) -> str:
    """편집기 글꼴 이름 → EffectCraft 가 찾는 PostScript 이름. 저장소 · 시스템에 없으면 Google Fonts 에서 받아 사용자 글꼴 폴더에(무료 · OFL)"""
    fam = (family or "Pretendard").split(",")[0].strip().strip("'\"") or "Pretendard"
    want = f"{fam}:weight={200 if bold else 80}{':slant=100' if italic else ''}"

    def match() -> str | None:
        r = subprocess.run(["fc-match", "-f", "%{family}|%{postscriptname}", want], capture_output=True, text=True)
        f, _, ps = r.stdout.partition("|")
        return ps if ps and fam.lower().replace(" ", "") in f.lower().replace(" ", "") else None

    ps = match()
    if ps:
        return ps
    if _fetch_google(fam):
        ps = match()
        if ps:
            return ps
    return "Pretendard-Bold" if bold else "Pretendard-Regular"


def _fetch_google(fam: str) -> bool:
    import urllib.request
    url = "https://fonts.googleapis.com/css2?family=" + fam.replace(" ", "+") + ":wght@400;700"
    try:
        # 오래된 브라우저 표시 → TTF 주소를 돌려준다(Craft 앱은 woff2 를 못 읽는다)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 6.1) AppleWebKit/534.30 (KHTML, like Gecko) Safari/534.30"})
        css = urllib.request.urlopen(req, timeout=20).read().decode("utf-8")
    except Exception:  # noqa: BLE001
        return False
    srcs = list(dict.fromkeys(re.findall(r"url\((https://[^)]+\.ttf)\)", css)))
    if not srcs:
        return False
    d = FONT_DIR / "google"; d.mkdir(parents=True, exist_ok=True)
    for i, s in enumerate(srcs[:2]):
        out = d / f"{fam.replace(' ', '')}-{('Regular', 'Bold')[min(i, 1)]}.ttf"
        if not out.exists():
            try:
                out.write_bytes(urllib.request.urlopen(s, timeout=60).read())
            except Exception:  # noqa: BLE001
                return False
    subprocess.run(["fc-cache", "-f", str(d)], capture_output=True)
    return True


# ---------------------------------------------------------------- 렌더
def _src_path(src: str, pid: str) -> Path:
    """편집기 미디어 주소 → 저장소 안 파일"""
    s = src or ""
    if s.startswith("/api/pipefiles/"):
        p = ROOT / "data" / "compositions" / unquote(s[len("/api/pipefiles/"):].split("?")[0])
    elif s.startswith("/api/"):
        q = parse_qs(urlparse(s).query).get("p", [""])[0]
        p = ROOT / (q if q.startswith("data/") else f"data/{q}")
    else:
        p = ROOT / s
    p = p.resolve()
    if ROOT.resolve() not in p.parents or not p.is_file():
        raise SystemExit(f"미디어 파일을 찾지 못했습니다: {src}")
    return p


def _hex(c: str) -> list[float]:
    c = (c or "#ffffff").lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    try:
        return [int(c[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    except ValueError:
        return [1, 1, 1]


def _effect_jsx(eff: dict, target: str) -> str:
    kind, eid, params = eff.get("kind"), str(eff.get("id") or ""), eff.get("params") or {}
    if kind == "effect":
        d = next((x for x in _catalog() if x["kind"] == "effect" and x["id"] == eid), None)
        if not d:
            raise SystemExit(f"없는 효과: {eid}")
        names = {p["id"]: p["name"] for p in _params(d.get("params"))}
        sets = "".join(f"try{{P(f,{json.dumps(names[k])}).setValue({json.dumps(v)});}}catch(e){{}}" for k, v in params.items() if k in names)
        return f"var f=FX(TGT,{json.dumps(d['label'])});{sets}"
    if kind == "recipe":
        r = next((x for x in rec.load() if x["id"] == eid), None)
        if not r or not _recipe_ok(r, target):
            raise SystemExit(f"이 요소에 쓸 수 없는 레시피: {eid}")
        v = {"TEXT": "TGT", "MAT": "TGT", "COMP": "FX", **{k: x for k, x in params.items() if k.isupper()}}
        p = rec.expand(r, v)
        return "".join(s["params"]["code"].replace(rec.PRELUDE.replace("@COMP@", "FX"), "") + ";" for s in p["steps"] if s["id"] == "script.run")
    return ""   # preset · textPreset 는 명령(run)으로


def render(pid: str, spec: dict) -> dict:
    target = spec.get("target") or "video"
    cv = spec.get("canvas") or {}
    W, H, fps = int(cv.get("w") or 1080), int(cv.get("h") or 1920), float(cv.get("fps") or 30)
    sec = max(0.1, min(60.0, float(spec.get("duration") or 2)))
    eff = spec.get("effect") or {}
    key = hashlib.sha1(json.dumps(spec, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
    out_dir = ROOT / "data" / "compositions" / pid / "editor" / "fx"
    out = out_dir / f"{key}.webm"
    url = f"/api/pipefiles/{pid}/editor/fx/{key}.webm"
    if out.exists() and out.stat().st_size > 0:
        return {"file": str(out.relative_to(ROOT)), "url": url, "sec": sec, "cached": True}
    out_dir.mkdir(parents=True, exist_ok=True)
    work = out_dir / key; work.mkdir(exist_ok=True)
    proj = work / "fx.ecproj"

    js = [f"var C=app.project.items.addComp('FX',{W},{H},1,{sec:.3f},{fps:.3f});",
          "function L(n){var l=C.layer(n);if(!l)throw new Error('레이어 없음: '+n);return l;}",
          "function FX(l,name){if(typeof l=='string')l=L(l);var f=l.property('Effects').addProperty(name);if(!f)throw new Error('효과 없음: '+name);return f;}",
          "function P(g,name){var p=g.property(name);if(!p)throw new Error('속성 없음: '+name);return p;}",
          "function K(p,pairs){for(var i=0;i<pairs.length;i++)p.setValueAtTime(pairs[i][0],pairs[i][1]);}",
          "function EASE(p,inf){inf=inf||75;for(var k=1;k<=p.numKeys;k++){var v=p.keyValue(k);var n=(v instanceof Array)?v.length:1;var e=[];for(var d=0;d<n;d++)e.push(new KeyframeEase(0,inf));try{p.setTemporalEaseAtKey(k,e,e);}catch(x){}}}",
          "function ADJ(name){var a=C.layers.addSolid([1,1,1],name,C.width,C.height,1);a.adjustmentLayer=true;return a;}"]
    if target == "text":
        t = spec.get("text") or {}
        font = _font_name(t.get("fontFamily") or "Pretendard", bool(t.get("bold", True)), bool(t.get("italic")))
        px = float(t.get("fontPx") or 72)
        just = {"left": "LEFT_JUSTIFY", "right": "RIGHT_JUSTIFY"}.get(t.get("align") or "center", "CENTER_JUSTIFY")
        js += [f"var l=C.layers.addText({json.dumps(str(t.get('content') or ''))});l.name='TGT';",
               "var st=l.property('Source Text');var td=st.value;",
               f"td.font={json.dumps(font)};td.fontSize={px:.2f};td.fillColor={json.dumps(_hex(t.get('color')))};td.justification=ParagraphJustification.{just};",
               f"try{{td.tracking={float(t.get('tracking') or 0):.1f};td.leading={px * float(t.get('leading') or 1.2):.1f};}}catch(e){{}}"]
        if (t.get("stroke") or {}).get("width"):
            s = t["stroke"]
            js.append(f"try{{td.applyStroke=true;td.strokeColor={json.dumps(_hex(s.get('color')))};td.strokeWidth={float(s['width']):.1f};td.strokeOverFill=false;}}catch(e){{}}")
        js += ["st.setValue(td);",
               # 글자 상자 가운데를 기준점으로 — 편집기처럼 가운데가 x · y 에
               "try{var r=l.sourceRectAtTime(0,false);l.property('Transform').property('Anchor Point').setValue([r.left+r.width/2,r.top+r.height/2]);}catch(e){}",
               f"l.property('Transform').property('Position').setValue([{W / 2 + float(t.get('x') or 0):.1f},{H / 2 + float(t.get('y') or 0):.1f}]);"]
        if float(t.get("skew") or 0):
            js.append(f"try{{var sk=FX(l,'Transform');P(sk,'Skew').setValue({-float(t['skew']):.2f});}}catch(e){{}}")
    else:
        m = spec.get("media") or {}
        src = _src_path(str(m.get("src") or ""), pid)
        js += [f"var it=app.project.importFile(new ImportOptions(new File({json.dumps(str(src))})));var l=C.layers.add(it);l.name='TGT';",
               f"l.startTime={-float(m.get('trimStart') or 0):.3f};",
               # 편집기 기본 맞춤(캔버스 안에 다 보이게) × 편집기 배율
               f"var k=Math.min({W}/it.width,{H}/it.height)*100;l.property('Transform').property('Scale').setValue([k*{float(m.get('scaleX') or 1):.4f},k*{float(m.get('scaleY') or 1):.4f}]);",
               f"l.property('Transform').property('Position').setValue([{W / 2 + float(m.get('x') or 0):.1f},{H / 2 + float(m.get('y') or 0):.1f}]);",
               f"try{{l.property('Transform').property('Rotation').setValue({float(m.get('rotate') or 0):.2f});}}catch(e){{}}"]
    js.append("var TGT=L('TGT');")
    js.append(_effect_jsx(eff, target))
    js.append(f"app.project.save(new File({json.dumps(str(proj))}));writeLn('ok');")
    (work / "build.jsx").write_text("\n".join(js), "utf-8")
    ec = cli("effectcraft")
    r = subprocess.run([ec, "script", str(work / "build.jsx")], capture_output=True, text=True, timeout=180)
    if r.returncode != 0 or "ok" not in r.stdout:
        raise SystemExit(f"EffectCraft 컴프를 만들지 못했습니다: {(r.stderr or r.stdout).strip()[-400:]}")
    if eff.get("kind") in ("preset", "textPreset"):
        step = {"command": "anim.applyBuiltinPreset", "params": {"preset": eff.get("id"), "layers": ["TGT"]}} if eff["kind"] == "preset" \
            else {"command": "layer.applyTextPreset", "params": {"layer": "TGT", "preset": eff.get("id")}}
        sp = work / "steps.json"
        sp.write_text(json.dumps([{"command": "comp.open", "params": {"comp": "FX"}}, step]), "utf-8")
        r = subprocess.run([ec, "run", "--commands", str(sp), "--project", str(proj), "--save"], capture_output=True, text=True, timeout=180)
        if r.returncode != 0:
            raise SystemExit(f"프리셋을 걸지 못했습니다: {(r.stderr or r.stdout).strip()[-400:]}")
    r = subprocess.run([ec, "render", "--comp", "FX", "--out", str(out), "--format", "webm", "--channels", "rgba", "--quality", "best",
                        "--audio", "off", str(proj)], capture_output=True, text=True, timeout=900)
    if r.returncode != 0 or not out.exists():
        raise SystemExit(f"렌더 실패: {(r.stderr or r.stdout).strip()[-400:]}")
    return {"file": str(out.relative_to(ROOT)), "url": url, "sec": sec, "cached": False}


def main() -> int:
    a = sys.argv[1:]
    if not a or a[0] not in ("list", "render"):
        print(__doc__); return 2
    if a[0] == "list":
        tgt = a[a.index("--target") + 1] if "--target" in a else "video"
        q = a[a.index("--q") + 1] if "--q" in a else ""
        print(json.dumps(listing(tgt, q), ensure_ascii=False)); return 0
    if len(a) < 3:
        print(__doc__); return 2
    spec = json.loads(sys.stdin.read() if a[2] == "-" else Path(a[2]).read_text("utf-8"))
    print(json.dumps(render(a[1], spec), ensure_ascii=False)); return 0


if __name__ == "__main__":
    sys.exit(main())
