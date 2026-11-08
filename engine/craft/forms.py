#!/usr/bin/env python3
"""화면 형식 라이브러리 — 콘티에 형식 이름과 내용만 적으면 앱 재료로 펼친다. 영상마다 그림 코드를 새로 쓰지 않는다.

  {"type": "form", "form": "parchment", "id": "p", "title": "…", "body": "…"}             낡은 양피지 글
  {"type": "form", "form": "atlas", "id": "m", "bbox": [서, 남, 동, 북], "route": [[경도, 위도]…], "marks": [[경도, 위도]…]}   실제 지형 옛 지도
  {"type": "form", "form": "gridchart", "id": "c", "bars": [{"value": 42, "color": "#…"}…], "max": 240}    모눈 도표
  {"type": "form", "form": "comic", "id": "k", "panels": [{"color": "#…", "image": "경로"}…]}     칸 나눈 만화(2 · 3 · 4칸)
  {"type": "form", "form": "sunset", "id": "s"}                                             석양 · 능선
  {"type": "form", "form": "halftone", "id": "h", "image": "경로"}                          신문 망점 사진(실제 사진을 넣는다)
  {"type": "archive", "id": "a", "title": "File:….jpg"}                                     실제 자료(engine/capture/commons.py) — 출처가 콘티 sources 에 들어간다
  {"type": "cast", "id": "kim", "look": {…}, "poses": ["talk", "shock"]}                   인물(engine/craft/cast.py)

펼친 결과는 앱 재료(craft)라 편집 파일이 남고 사용량이 기록된다. make_job 이 렌더 전에 펼친다.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
INK, RED = "#2b2118", "#a3201c"
W0, H0 = 1920, 1080


def _size(sb: dict) -> tuple[int, int]:
    from engines import aspect_size
    return aspect_size(sb)


class VC:
    """VectorCraft 명령 묶음"""

    def __init__(self):
        self.st: list = []

    def poly(self, pts, fill=None, stroke=None, weight=0, closed=True, dash=None):
        st = self.st
        st.append({"id": "path.create", "params": {"anchors": [{"x": round(x, 1), "y": round(y, 1)} for x, y in pts], "closed": closed}})
        i = len(st) - 1
        st.append({"id": "paint.setFill", "params": {"id": f"${i}.id", **({"color": fill} if fill else {"none": True})}})
        st.append({"id": "paint.setStroke", "params": {"id": f"${i}.id", **({"color": stroke} if stroke else {"none": True})}})
        if stroke:
            st.append({"id": "stroke.set", "params": {"id": f"${i}.id", "weight": weight, "cap": "round", "join": "round", **({"dash": dash} if dash else {})}})

    def rect(self, x0, y0, x1, y1, fill, stroke=None, weight=0):
        self.poly([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], fill, stroke, weight)


def vmat(mid, w, h, v: VC) -> dict:
    return {"id": mid, "type": "craft", "app": "vectorcraft", "show": False, "new": {"width": w, "height": h, "units": "Pixels"}, "steps": v.st, "export": {"format": "png", "size": [w, h]}}


def pmat(mid, w, h, steps, m=None, show=True) -> dict:
    r = {"id": mid, "type": "craft", "app": "photocraft", "new": {"width": w, "height": h, "background": "#ffffff"}, "steps": steps, "place": "full", "export": {"format": "png", "size": [w, h]}}
    if not show:
        r["show"] = False
    return r


def place(path, w, h, mode=None, opacity=None, scale=100):
    st = [{"id": "file.placeEmbedded", "params": {"path": path, "center": [w / 2, h / 2], "smartObject": False, "scale": scale}}]
    if mode or opacity is not None:
        st.append({"id": "layer.setProps", "params": {**({"blend": mode} if mode else {}), **({"opacity": opacity} if opacity is not None else {})}})
    return st


def parchment_base(w, h, seed=9, burn=True):
    st = [{"id": "filter.render.fibers", "params": {"variance": 26, "strength": 3, "seed": seed, "foreground": "#dcc597", "background": "#cfb681"}},
          {"id": "layer.new.layer", "params": {"name": "얼룩", "mode": "Multiply", "opacity": .46}},
          {"id": "filter.render.clouds", "params": {"seed": seed + 3, "foreground": "#ffffff", "background": "#a98a5c"}}]
    if burn:
        e = [[[-30, -30, 1], [w + 30, -30, 1]], [[w + 30, -30, 1], [w + 30, h + 30, 1]], [[w + 30, h + 30, 1], [-30, h + 30, 1]], [[-30, h + 30, 1], [-30, -30, 1]]]
        st += [{"id": "layer.new.layer", "params": {"name": "탄 가장자리", "mode": "Multiply", "opacity": .85}}] + [{"id": "paint.stroke", "params": {"points": q, "size": 190, "hardness": .1, "color": "#4b2d14"}} for q in e] + [{"id": "filter.blur.gaussianBlur", "params": {"radius": 60}}]
    return st


def _parchment(m, sid, n, w, h, md):
    from craft.board_text import page
    pg = page(f"{m['id']}_t", w, h, m)
    return [pg, pmat(m["id"], w, h, parchment_base(w, h, int(m.get("seed", 9))) + place(f"{md}/{pg['id']}.png", w, h, "Multiply", .9))]


def _atlas(m, sid, n, w, h, md):
    from craft.geo import land
    v = VC()
    polys, to = land(m["bbox"], w, h, margin=int(m.get("margin", 0)))
    for pts in polys:
        v.poly(pts, "#c9ad74", INK, 4)
    cx, cy = w / 2, h / 2
    for pts in polys:                                # 옛 지도의 바다 쪽 빗금
        step = max(1, len(pts) // 260)
        for i in range(0, len(pts), step):
            x, y = pts[i]
            a, b = pts[i - 1], pts[(i + 1) % len(pts)]
            nx, ny = (b[1] - a[1]), -(b[0] - a[0])
            d = math.hypot(nx, ny) or 1
            l = 9 + (i % 3) * 5
            v.poly([(x, y), (x - nx / d * l, y - ny / d * l)], None, INK, 1.8, closed=False)
    for q in m.get("mountains") or []:
        x, y = to(*q)
        v.poly([(x - 26, y + 14), (x - 4, y - 20), (x + 2, y - 8), (x + 26, y + 14)], None, INK, 4, closed=False)
    if m.get("route"):
        v.poly([to(*q) for q in m["route"]], None, "#8e2a1c", 8, closed=False, dash=[16, 16])
    for q in m.get("marks") or []:
        x, y = to(*q)
        v.rect(x - 11, y - 11, x + 11, y + 11, "#8e2a1c", INK, 3)
    x, y = w - 180, h - 240
    v.poly([(x, y - 90), (x + 16, y), (x, y + 90), (x - 16, y)], INK)
    v.poly([(x - 90, y), (x, y - 16), (x + 90, y), (x, y + 16)], "#c9ad74", INK, 3)
    mp = vmat(f"{m['id']}_v", w, h, v)
    return [mp, pmat(m["id"], w, h, parchment_base(w, h, 11) + place(f"{md}/{mp['id']}.png", w, h, "Multiply", .95))]


def _gridchart(m, sid, n, w, h, md):
    v = VC()
    v.rect(0, 0, w, h, "#f4f0e6")
    for x in range(0, w, 60):
        v.poly([(x, 0), (x, h)], None, "#c9d6dc", 1.5, closed=False)
    for y in range(0, h, 60):
        v.poly([(0, y), (w, y)], None, "#c9d6dc", 1.5, closed=False)
    top, gap = int(m.get("top", 400)), int(m.get("gap", 240))
    mx = float(m.get("max") or max(b["value"] for b in m["bars"]))
    x0, x1 = 240, w - 240
    for i, b in enumerate(m["bars"]):
        v.rect(x0, top + i * gap, x0 + (x1 - x0) * b["value"] / mx, top + i * gap + 70, b.get("color", RED))
    mp = vmat(f"{m['id']}_v", w, h, v)
    return [mp, pmat(m["id"], w, h, place(f"{md}/{mp['id']}.png", w, h))]


def _comic(m, sid, n, w, h, md):
    v = VC()
    v.rect(0, 0, w, h, "#f1e8d6")
    ps = m["panels"]
    rows = 2 if len(ps) == 4 else 1
    cols = len(ps) // rows
    gx, gy, top, bot = 50, 30, 50, h - 200
    cw, ch = (w - gx * (cols + 1)) / cols, (bot - top - gy * (rows - 1)) / rows
    boxes = []
    for i, p in enumerate(ps):
        x0, y0 = gx + (i % cols) * (cw + gx), top + (i // cols) * (ch + gy)
        v.rect(x0, y0, x0 + cw, y0 + ch, p.get("color", "#e0b95f"), "#17110c", 9)
        boxes.append((x0, y0, x0 + cw, y0 + ch))
    mp = vmat(f"{m['id']}_v", w, h, v)
    st = place(f"{md}/{mp['id']}.png", w, h)
    for (x0, y0, x1, y1), p in zip(boxes, ps):
        if p.get("image"):
            st.append({"id": "file.placeEmbedded", "params": {"path": p["image"], "center": [(x0 + x1) / 2 + float(p.get("dx", 0)), (y0 + y1) / 2], "smartObject": False, "scale": float(p.get("scale", 60))}})
    st.append({"id": "filter.noise.addNoise", "params": {"amount": 2.5, "distribution": "gaussian", "monochromatic": True, "seed": 3}})
    return [mp, pmat(m["id"], w, h, st)]


def _sunset(m, sid, n, w, h, md):
    from craft.board_text import gradient
    sk = gradient(f"{m['id']}_s", w, h, m.get("stops") or [(0, "#2c2140"), (42, "#a2412f"), (68, "#ee9345"), (100, "#ffd089")])
    v = VC()
    if m.get("moon") and m.get("ridge", True):          # 그린 배경(figure set)을 얹을 때는 하늘만 — 달 · 능선은 그 그림이 그린다
        import math as _m
        mx, my, mr = m["moon"]
        v.poly([(mx + mr * _m.cos(i / 40 * 6.283), my + mr * _m.sin(i / 40 * 6.283)) for i in range(40)], "#f2e6c4", "#d9c690", 4)
        for dx, dy, r in ((-30, -20, 18), (28, 14, 12), (-8, 34, 9)):
            v.poly([(mx + dx + r * _m.cos(i / 16 * 6.283), my + dy + r * _m.sin(i / 16 * 6.283)) for i in range(16)], "#e0d0a2")
    if m.get("ridge", True):
        v.poly([(0, 760), (240, 690), (520, 770), (840, 700), (1180, 780), (1500, 700), (w, 760), (w, h), (0, h)], "#3a1d24")
        v.poly([(0, 860), (w, 850), (w, h), (0, h)], "#120b10")
    else:
        v.poly([(0, h - 2), (w, h - 2), (w, h), (0, h)], "#120b10")
    rg = vmat(f"{m['id']}_r", w, h, v)
    return [sk, rg, pmat(m["id"], w, h, place(f"{md}/{sk['id']}.png", w, h) + place(f"{md}/{rg['id']}.png", w, h) + [{"id": "filter.noise.addNoise", "params": {"amount": 3, "distribution": "gaussian", "monochromatic": True, "seed": 7}}])]


def _halftone(m, sid, n, w, h, md):
    st = [{"id": "file.placeEmbedded", "params": {"path": m["image"], "center": [w / 2, h / 2 + float(m.get("dy", 0))], "smartObject": False, "scale": float(m.get("scale", 100))}}] + [{"id": "filter.noise.addNoise", "params": {"amount": 6, "distribution": "gaussian", "monochromatic": True, "seed": 4}},
          {"id": "filter.gallery.halftonePattern", "params": {"size": int(m.get("dot", 3)), "contrast": 8, "patternType": "dot", "foreground": "#141414", "background": "#e9e5da"}}]
    return [pmat(m["id"], w, h, st)]


FORMS = {"parchment": _parchment, "atlas": _atlas, "gridchart": _gridchart, "comic": _comic, "sunset": _sunset, "halftone": _halftone}


def _archive(m, sb, w, h):
    """실제 자료: 받아서 화면을 덮게 놓고 출처를 콘티에 남긴다"""
    from commons import fetch
    from PIL import Image
    f = ROOT / "data" / "public" / "archive" / sb["id"] / f"{m['id']}.jpg"
    mf = f.with_suffix(".json")
    if not f.exists() or not mf.exists():
        mf.parent.mkdir(parents=True, exist_ok=True)
        mf.write_text(json.dumps(fetch(m["title"], f, int(m.get("width", 2400))), ensure_ascii=False), "utf-8")
    meta = json.loads(mf.read_text("utf-8"))
    src = sb.setdefault("sources", [])
    if meta.get("page") and meta["page"] not in src:
        src.append(meta["page"])
    sb.setdefault("credits", {})[m["id"]] = f"{meta.get('artist') or ''} · {meta.get('license')}".strip(" ·")
    cf = f.parent / "credits.txt"                     # 설명란 '사용한 자료' — CC BY · BY-SA 는 저작자 표시가 조건이다
    line = f"{meta.get('title')} — {meta.get('artist') or '저작자 미상'} · {meta.get('license')} · {meta.get('page')}"
    old = cf.read_text("utf-8").splitlines() if cf.exists() else []
    if line not in old:
        cf.write_text("\n".join(old + [line]) + "\n", "utf-8")
    with Image.open(f) as im:
        iw, ih = im.size
    fit = m.get("fit", "cover")
    s = (max if fit == "cover" else min)(w / iw, h / ih) * 100
    st = []
    if fit != "cover":                               # 세로 사진: 같은 사진을 흐리게 깔고 가운데에 놓는다
        s2 = max(w / iw, h / ih) * 100
        st += [{"id": "file.placeEmbedded", "params": {"path": str(f.relative_to(ROOT)), "center": [w / 2, h / 2], "smartObject": False, "scale": round(s2, 3)}}, {"id": "filter.blur.gaussianBlur", "params": {"radius": 42}}, {"id": "layer.newAdjustmentLayer.hueSaturation", "params": {"saturation": -25, "lightness": -46}}]
    st.append({"id": "file.placeEmbedded", "params": {"path": str(f.relative_to(ROOT)), "center": [w / 2, h / 2 + float(m.get("dy", 0))], "smartObject": False, "scale": round(s, 3)}})
    return [pmat(m["id"], w, h, st, show=m.get("show", True) is not False)]


def _silhouette(m: dict) -> list[dict]:
    from craft import silhouette as sh
    out = []
    for k in range(8):
        st: list = []
        p, l = sh.pose(k / 8, cx=246, ground=496, s=.96)
        sh.steps(p, l, st)
        out.append({"id": f"{m['id']}_run{k}", "type": "craft", "app": "vectorcraft", "show": False, "new": {"width": 512, "height": 512, "units": "Pixels"}, "steps": st, "export": {"format": "png", "size": [512, 512]}})
    return out


def expand_sb(sb: dict) -> dict:
    """콘티의 form · archive · cast 재료를 앱 재료로 펼친다(읽을 때만, 파일은 그대로)"""
    from craft import cast
    w, h = _size(sb)
    for n, sc in enumerate(sb.get("scenes") or [], 1):
        out = []
        md = f"data/compositions/{sb['id']}/craft/materials/s{n:02d}"
        for m in sc.get("materials") or []:
            t = m.get("type")
            if t == "form":
                if m.get("form") not in FORMS:
                    raise RuntimeError(f"모르는 형식: {m.get('form')} ({' · '.join(FORMS)})")
                out += FORMS[m["form"]](m, sb["id"], n, w, h, md)
            elif t == "archive":
                out += _archive(m, sb, w, h)
            elif t == "cast":
                out += cast.materials(m)
            elif t == "silhouette":                  # 작은 전신 달리기 — 도기풍 검은 실루엣 8칸
                out += _silhouette(m)
            else:
                out.append(m)
        sc["materials"] = out
        sc["refine"] = [_recipe(p) for p in sc.get("refine") or []]
    return sb


def _recipe(p: dict) -> dict:
    """콘티에 {"recipe": 이름, "vars": {…}} 만 적으면 펼친다 — 영상마다 코드를 쓰지 않는다"""
    if p.get("steps") or not p.get("recipe"):
        return p
    from craft import recipes
    r = json.loads((ROOT / ".claude" / "skills" / "refine" / "recipes" / f"{p['recipe']}.json").read_text("utf-8"))
    q = recipes.expand(r, {"COMP": "$COMP", **{k: str(v) for k, v in (p.get("vars") or {}).items()}})
    return {**q, "target": r.get("target", "motion"), "why": p.get("why") or q.get("why")}
